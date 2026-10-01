"""Deterministic live tick engine. Seed 42 -> same demo every run.

Each tick: spawn demand, reserve stock + allocate, advance packing, move riders,
recompute delay risk, and broadcast a diff over WebSocket.

Architecture: the tick loop operates ENTIRELY on the in-memory `world` state (backend/app/world.py)
— zero DB round trips per tick. A separate, independent persist_loop() flushes dirty state to
Postgres every PERSIST_INTERVAL_SECONDS in the background. This is what gets tick time from the
~3s we measured with a batched-but-still-DB-backed tick down to low single-digit milliseconds:
there is no network call anywhere in the hot path at all now.
"""
import asyncio
import random
import datetime as dt
import json
import uuid
from . import world as world_module
from .world import world, NON_TERMINAL_STATUSES, ACTIVE_STATUSES
from .catalog import CATALOG
from .dispatch import (
    allocate_sync, cheapest_insertion_cost, rolling_reoptimize_sync,
    traffic_multiplier_for_leg, active_traffic_zones,
)
from .ws import manager

TICK_SECONDS = 2.0
PERSIST_INTERVAL_SECONDS = 3.0
SEED = 42

# scenario knobs, toggled by /disruptions endpoints
state = {
    "order_spawn_rate": 0.35,  # probability per tick of a new order
    "blocked_store_ids": set(),
}

_rng = random.Random(SEED)
DEMO_CUSTOMER_NAMES = [
    "Aarav Shah", "Priya Nair", "Rohan Mehta", "Isha Kapoor", "Karan Singh",
    "Ananya Rao", "Vikram Joshi", "Sneha Iyer", "Arjun Desai", "Meera Pillai",
]
AREA_NAMES = ["Andheri West", "Bandra East", "Powai", "Lower Parel", "Dadar", "Kurla", "Vile Parle"]


def reset_rng():
    global _rng
    _rng = random.Random(SEED)


def _jitter_point(lat, lng, km=3.0):
    dlat = (_rng.random() - 0.5) * (km / 111.0) * 2
    dlng = (_rng.random() - 0.5) * (km / 111.0) * 2
    return lat + dlat, lng + dlng


def _group_by(orders, statuses, key_attr):
    out: dict = {}
    for o in orders:
        if o.status in statuses:
            k = getattr(o, key_attr)
            out.setdefault(k, []).append(o)
    return out


def spawn_order():
    from .models import Order
    if not world.stores:
        return
    anchor = _rng.choice(world.stores)
    lat, lng = _jitter_point(anchor.lat, anchor.lng, km=4.0)
    n_items = _rng.randint(1, 3)
    items = []
    weight = 0.0
    for product in _rng.sample(CATALOG, n_items):
        qty = _rng.randint(1, 2)
        items.append({"sku": product["sku"], "name": product["name"], "qty": qty, "weight_kg": product["weight_kg"]})
        weight += product["weight_kg"] * qty
    priority = _rng.random() < 0.2
    now = dt.datetime.now(dt.timezone.utc)
    promise_minutes = 12 if priority else _rng.choice([15, 20, 25, 30])
    order = Order(
        id=f"ORD-{uuid.uuid4().hex[:8].upper()}",
        customer_lat=lat, customer_lng=lng,
        items=items, weight_kg=round(weight, 2),
        priority=priority,
        customer_name=_rng.choice(DEMO_CUSTOMER_NAMES),
        address_label=f"Flat {_rng.randint(1,12)}0{_rng.randint(1,9)}, {_rng.choice(AREA_NAMES)}",
        created_at=now,
        promised_at=now + dt.timedelta(minutes=promise_minutes),
        status="created", risk="LOW",
    )
    world.add_new_order(order)
    world.log_event(order.id, "ORDER_CREATED", {"priority": priority, "promise_minutes": promise_minutes})
    return order


def try_allocate(order, active_orders):
    active_by_rider = _group_by(active_orders, ACTIVE_STATUSES, "rider_id")
    decision = allocate_sync(order, world.stores, world.riders, active_by_rider, world.inventory)
    if decision is None:
        order.risk = "AT_RISK"
        world.mark_order_dirty(order.id)
        world.log_event(order.id, "DELAY_RISK", {"reason": "no_feasible_store_or_rider"})
        return
    chosen = decision["chosen"]
    store_id, rider_id = chosen["store_id"], chosen["rider_id"]

    world.reserve_stock(store_id, order.items)
    world.log_event(order.id, "STOCK_RESERVED", {"store_id": store_id})

    rider = world.rider_by_id[rider_id]
    existing = active_by_rider.get(rider_id, [])
    store = world.store_by_id[store_id]
    idx, _added, _feasible = cheapest_insertion_cost(rider, existing, order, store)

    order.store_id = store_id
    order.rider_id = rider_id
    order.route_seq = idx
    order.status = "assigned"
    order.assigned_at = dt.datetime.now(dt.timezone.utc)
    order.assignment_reason = json.dumps(decision, default=str)
    rider.current_load_kg += order.weight_kg
    world.mark_order_dirty(order.id)
    world.mark_rider_dirty(rider.id)
    world.log_event(order.id, "ASSIGNED", {"store_id": store_id, "rider_id": rider_id, "cost": chosen["cost"]})


def advance_packing(active_orders):
    by_store_packing = _group_by(active_orders, ["packing"], "store_id")
    by_store_assigned = _group_by(active_orders, ["assigned"], "store_id")
    risk_rank = {"SEVERE": 0, "DELAYED": 1, "AT_RISK": 2, "LOW": 3}
    now = dt.datetime.now(dt.timezone.utc)

    for store in world.stores:
        packing_now = by_store_packing.get(store.id, [])
        for o in packing_now:
            elapsed = (now - o.assigned_at).total_seconds()
            if elapsed >= store.packing_seconds_per_order:
                o.status = "packed"
                o.packed_at = now
                world.mark_order_dirty(o.id)
                world.log_event(o.id, "PACKED")

        free_slots = store.packing_capacity - sum(1 for o in packing_now if o.status == "packing")
        if free_slots <= 0:
            continue
        queued = by_store_assigned.get(store.id, [])
        queued.sort(key=lambda o: (0 if o.priority else 1, risk_rank.get(o.risk, 3), o.assigned_at))
        for o in queued[:free_slots]:
            o.status = "packing"
            world.mark_order_dirty(o.id)
            world.log_event(o.id, "PACKING_STARTED")


BATTERY_DRAIN_PCT_PER_KM = 0.4


def move_riders(active_orders):
    by_rider = _group_by(active_orders, ["packed", "out_for_delivery"], "rider_id")
    now = dt.datetime.now(dt.timezone.utc)

    for rider in world.riders:
        if rider.status == "OFFLINE":
            continue
        active = sorted(by_rider.get(rider.id, []), key=lambda o: o.route_seq or 0)
        if not active:
            if rider.status == "ON_DELIVERY":
                rider.status = "AVAILABLE"
                world.mark_rider_dirty(rider.id)
            continue

        awaiting_pickup = [o for o in active if o.status == "packed"]
        target_order = awaiting_pickup[0] if awaiting_pickup else active[0]
        if target_order.status == "packed":
            store = world.store_by_id[target_order.store_id]
            dest_lat, dest_lng = store.lat, store.lng
        else:
            dest_lat, dest_lng = target_order.customer_lat, target_order.customer_lng

        speed = rider.speed_kmh * traffic_multiplier_for_leg(rider.lat, rider.lng, dest_lat, dest_lng)
        dist_km = ((rider.lat - dest_lat) ** 2 + (rider.lng - dest_lng) ** 2) ** 0.5 * 111.0
        step_km = speed * (TICK_SECONDS / 3600.0)
        if dist_km <= step_km:
            rider.lat, rider.lng = dest_lat, dest_lng
            moved_km = dist_km
            if target_order.status == "packed":
                target_order.status = "out_for_delivery"
                target_order.picked_up_at = now
                world.mark_order_dirty(target_order.id)
                world.log_event(target_order.id, "PICKED_UP")
            else:
                target_order.status = "delivered"
                target_order.delivered_at = now
                rider.current_load_kg = max(0.0, rider.current_load_kg - target_order.weight_kg)
                world.mark_order_dirty(target_order.id)
                world.log_event(target_order.id, "DELIVERED")
        else:
            frac = step_km / dist_km
            moved_km = step_km
            rider.lat += (dest_lat - rider.lat) * frac
            rider.lng += (dest_lng - rider.lng) * frac
        rider.status = "ON_DELIVERY"
        rider.battery_pct = max(0, rider.battery_pct - moved_km * BATTERY_DRAIN_PCT_PER_KM)
        world.mark_rider_dirty(rider.id)


def recompute_risk(active_orders):
    # Only assign o.risk when it actually changes — an unconditional assignment would mark every
    # active order dirty every tick regardless of value.
    now = dt.datetime.now(dt.timezone.utc)
    for o in active_orders:
        slack_min = (o.promised_at - now).total_seconds() / 60.0
        if slack_min < 0:
            new_risk = "SEVERE"
        elif slack_min < 3:
            new_risk = "DELAYED"
        elif slack_min < 7:
            new_risk = "AT_RISK"
        else:
            new_risk = "LOW"
        if new_risk != o.risk:
            o.risk = new_risk
            world.mark_order_dirty(o.id)
            if new_risk in ("DELAYED", "SEVERE"):
                world.log_event(o.id, "DELAY_RISK", {"slack_minutes": round(slack_min, 1)})


FAIL_AFTER_MINUTES_LATE = 20


def fail_overdue_orders(active_orders):
    """An order that's been severely overdue with no feasible path for too long is marked failed
    instead of hanging in AT_RISK forever."""
    now = dt.datetime.now(dt.timezone.utc)
    for o in active_orders:
        late_min = (now - o.promised_at).total_seconds() / 60.0
        if o.status == "created" and late_min > FAIL_AFTER_MINUTES_LATE:
            world.fail_order(o, "no_feasible_rider_or_store_in_time")
            world.log_event(o.id, "FAILED", {"reason": "no_feasible_rider_or_store_in_time"})


def reoptimize_routes(active_orders):
    by_rider = _group_by(active_orders, ACTIVE_STATUSES, "rider_id")
    for rider in world.riders:
        pending = sorted(by_rider.get(rider.id, []), key=lambda o: o.route_seq or 0)
        rolling_reoptimize_sync(rider, pending)
        for o in pending:
            world.mark_order_dirty(o.id)  # route_seq may have changed


def build_snapshot() -> dict:
    visible_orders = [o for o in world.orders.values() if o.status not in ("delivered", "failed", "cancelled")]
    return {
        "type": "tick",
        "dark_stores": [{"id": s.id, "name": s.name, "lat": s.lat, "lng": s.lng} for s in world.stores],
        "traffic_zones": [
            {"id": z["id"], "lat": z["lat"], "lng": z["lng"], "radius_km": z["radius_km"]}
            for z in active_traffic_zones()
        ],
        "riders": [
            {"id": r.id, "name": r.name, "lat": r.lat, "lng": r.lng, "status": r.status,
             "current_load_kg": r.current_load_kg, "capacity_kg": r.capacity_kg,
             "utilization": round(100 * r.current_load_kg / r.capacity_kg) if r.capacity_kg else 0,
             "battery_pct": round(r.battery_pct, 1)}
            for r in world.riders
        ],
        "orders": [
            {"id": o.id, "lat": o.customer_lat, "lng": o.customer_lng, "status": o.status,
             "priority": o.priority, "risk": o.risk, "rider_id": o.rider_id, "store_id": o.store_id,
             "promised_at": o.promised_at.isoformat()}
            for o in visible_orders
        ],
    }


def tick_sync():
    """Pure in-memory tick — no awaits, no DB, nothing network-bound. Called from the async tick()
    wrapper below so it stays easy to call directly (and time) from tests."""
    if _rng.random() < state["order_spawn_rate"]:
        spawn_order()

    active_orders = world.active_orders()
    for o in [o for o in active_orders if o.status == "created"]:
        try_allocate(o, active_orders)

    advance_packing(active_orders)
    move_riders(active_orders)
    recompute_risk(active_orders)
    fail_overdue_orders(active_orders)
    reoptimize_routes(active_orders)


async def tick():
    tick_sync()
    await manager.broadcast(build_snapshot())


async def run_forever():
    while True:
        try:
            await tick()
        except Exception as e:  # ponytail: log-and-continue keeps the demo alive; add alerting if this ever fires in prod
            print(f"[simulator] tick error: {e}")
        await asyncio.sleep(TICK_SECONDS)


async def persist_loop():
    while True:
        await asyncio.sleep(PERSIST_INTERVAL_SECONDS)
        try:
            await world_module.persist_once()
        except Exception as e:
            print(f"[simulator] persist error: {e}")
