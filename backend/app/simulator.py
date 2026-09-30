"""Deterministic live tick engine. Seed 42 -> same demo every run.

Each tick: spawn demand, reserve stock + allocate, advance packing, move riders,
recompute delay risk, and broadcast a diff over WebSocket.

Performance note: every step below reads from ONE batch-fetched order/rider/store/inventory
snapshot per tick (fetch_tick_context) instead of querying per-entity. The original per-rider,
per-store query loops took 30-40s/tick against remote Neon once the fleet grew past a handful of
riders — this version does a fixed ~5 round trips per tick regardless of fleet size.
"""
import asyncio
import random
import datetime as dt
import json
import uuid
from sqlalchemy import select, update as sa_update
from sqlalchemy.orm.attributes import set_committed_value
from .db import SessionLocal
from .models import DarkStore, Rider, Order, OrderEvent, InventoryItem
from .dispatch import (
    allocate_sync, cheapest_insertion_cost, rolling_reoptimize_sync,
    traffic_multiplier_for_leg, active_traffic_zones, fetch_inventory_map,
)
from .ws import manager

TICK_SECONDS = 2.0
SEED = 42
ACTIVE_STATUSES = ["assigned", "packing", "packed", "out_for_delivery"]
NON_TERMINAL_STATUSES = ["created"] + ACTIVE_STATUSES

# scenario knobs, toggled by /disruptions endpoints
state = {
    "order_spawn_rate": 0.35,  # probability per tick of a new order
    "blocked_store_ids": set(),
}

_rng = random.Random(SEED)
SKU_CATALOG = [
    ("SKU-MILK", "Milk 1L", 0.5),
    ("SKU-BREAD", "Bread Loaf", 0.3),
    ("SKU-EGGS", "Eggs (12)", 0.6),
    ("SKU-RICE", "Rice 5kg", 5.0),
    ("SKU-SOAP", "Soap Bar", 0.15),
    ("SKU-SNACK", "Snack Pack", 0.2),
]


def _log_event(session, order_id: str, type_: str, payload: dict | None = None):
    session.add(OrderEvent(order_id=order_id, type=type_, payload=payload or {}))


def _jitter_point(lat, lng, km=3.0):
    dlat = (_rng.random() - 0.5) * (km / 111.0) * 2
    dlng = (_rng.random() - 0.5) * (km / 111.0) * 2
    return lat + dlat, lng + dlng


async def fetch_tick_context(session, stores):
    """The entire mutable world state for one tick, in three round trips."""
    riders = (await session.execute(select(Rider))).scalars().all()
    all_orders = (await session.execute(select(Order).where(Order.status.in_(NON_TERMINAL_STATUSES)))).scalars().all()
    inventory_map = await fetch_inventory_map(session, [s.id for s in stores])
    return {"riders": riders, "all_orders": all_orders, "inventory_map": inventory_map}


def _group_by(orders, statuses, key_attr):
    out: dict = {}
    for o in orders:
        if o.status in statuses:
            k = getattr(o, key_attr)
            out.setdefault(k, []).append(o)
    return out


def spawn_order(session, stores):
    if not stores:
        return
    anchor = _rng.choice(stores)
    lat, lng = _jitter_point(anchor.lat, anchor.lng, km=4.0)
    n_items = _rng.randint(1, 3)
    items = []
    weight = 0.0
    for sku, name, w in _rng.sample(SKU_CATALOG, n_items):
        qty = _rng.randint(1, 2)
        items.append({"sku": sku, "name": name, "qty": qty, "weight_kg": w})
        weight += w * qty
    priority = _rng.random() < 0.2
    now = dt.datetime.now(dt.timezone.utc)
    promise_minutes = 12 if priority else _rng.choice([15, 20, 25, 30])
    order = Order(
        id=f"ORD-{uuid.uuid4().hex[:8].upper()}",
        customer_lat=lat, customer_lng=lng,
        items=items, weight_kg=round(weight, 2),
        priority=priority,
        created_at=now,
        promised_at=now + dt.timedelta(minutes=promise_minutes),
        status="created",
    )
    session.add(order)
    _log_event(session, order.id, "ORDER_CREATED", {"priority": priority, "promise_minutes": promise_minutes})
    return order


def try_allocate(session, order: Order, stores, store_by_id, ctx):
    """In-memory allocation against the tick's pre-fetched context; mutates ctx so later orders in
    the same tick see the effect of earlier ones (no per-order DB round trips)."""
    active_by_rider = _group_by(ctx["all_orders"], ACTIVE_STATUSES, "rider_id")
    decision = allocate_sync(order, stores, ctx["riders"], active_by_rider, ctx["inventory_map"])
    if decision is None:
        order.risk = "AT_RISK"
        _log_event(session, order.id, "DELAY_RISK", {"reason": "no_feasible_store_or_rider"})
        return
    chosen = decision["chosen"]
    store_id, rider_id = chosen["store_id"], chosen["rider_id"]

    for it in order.items:
        ctx["inventory_map"][(store_id, it["sku"])].reserved_qty += it["qty"]
    _log_event(session, order.id, "STOCK_RESERVED", {"store_id": store_id})

    rider = next(r for r in ctx["riders"] if r.id == rider_id)
    existing = active_by_rider.get(rider_id, [])
    store = store_by_id[store_id]
    idx, _added, _feasible = cheapest_insertion_cost(rider, existing, order, store)

    order.store_id = store_id
    order.rider_id = rider_id
    order.route_seq = idx
    order.status = "assigned"
    order.assigned_at = dt.datetime.now(dt.timezone.utc)
    order.assignment_reason = json.dumps(decision, default=str)
    rider.current_load_kg += order.weight_kg
    _log_event(session, order.id, "ASSIGNED", {"store_id": store_id, "rider_id": rider_id, "cost": chosen["cost"]})


def advance_packing(session, stores, ctx):
    by_store_packing = _group_by(ctx["all_orders"], ["packing"], "store_id")
    by_store_assigned = _group_by(ctx["all_orders"], ["assigned"], "store_id")
    risk_rank = {"SEVERE": 0, "DELAYED": 1, "AT_RISK": 2, "LOW": 3}
    now = dt.datetime.now(dt.timezone.utc)

    for store in stores:
        packing_now = by_store_packing.get(store.id, [])
        for o in packing_now:
            elapsed = (now - o.assigned_at).total_seconds()
            if elapsed >= store.packing_seconds_per_order:
                o.status = "packed"
                o.packed_at = now
                _log_event(session, o.id, "PACKED")

        free_slots = store.packing_capacity - sum(1 for o in packing_now if o.status == "packing")
        if free_slots <= 0:
            continue
        queued = by_store_assigned.get(store.id, [])
        queued.sort(key=lambda o: (0 if o.priority else 1, risk_rank.get(o.risk, 3), o.assigned_at))
        for o in queued[:free_slots]:
            o.status = "packing"
            _log_event(session, o.id, "PACKING_STARTED")


def move_riders(session, store_by_id, ctx):
    """Every actively-delivering rider's position changes every single tick — that's real, unavoidable
    write volume. What's avoidable is paying one network round trip per rider for it: this collects
    every rider's new (lat, lng, status, current_load_kg) into a list and the caller issues ONE bulk
    UPDATE (executemany) for the whole fleet instead of N individually-flushed ORM writes. Rider
    objects are synced via set_committed_value so they reflect the new state for the WS snapshot
    without the ORM ALSO queuing its own redundant per-row UPDATE at commit."""
    by_rider = _group_by(ctx["all_orders"], ["packed", "out_for_delivery"], "rider_id")
    now = dt.datetime.now(dt.timezone.utc)
    bulk_updates = []

    def sync(rider, lat, lng, status, load):
        set_committed_value(rider, "lat", lat)
        set_committed_value(rider, "lng", lng)
        set_committed_value(rider, "status", status)
        set_committed_value(rider, "current_load_kg", load)
        bulk_updates.append({"id": rider.id, "lat": lat, "lng": lng, "status": status, "current_load_kg": load})

    for rider in ctx["riders"]:
        if rider.status == "OFFLINE":
            continue
        active = sorted(by_rider.get(rider.id, []), key=lambda o: o.route_seq or 0)
        if not active:
            if rider.status == "ON_DELIVERY":
                sync(rider, rider.lat, rider.lng, "AVAILABLE", rider.current_load_kg)
            continue

        awaiting_pickup = [o for o in active if o.status == "packed"]
        target_order = awaiting_pickup[0] if awaiting_pickup else active[0]
        if target_order.status == "packed":
            store = store_by_id[target_order.store_id]
            dest_lat, dest_lng = store.lat, store.lng
        else:
            dest_lat, dest_lng = target_order.customer_lat, target_order.customer_lng

        speed = rider.speed_kmh * traffic_multiplier_for_leg(rider.lat, rider.lng, dest_lat, dest_lng)
        dist_km = ((rider.lat - dest_lat) ** 2 + (rider.lng - dest_lng) ** 2) ** 0.5 * 111.0
        step_km = speed * (TICK_SECONDS / 3600.0)
        new_load = rider.current_load_kg
        if dist_km <= step_km:
            new_lat, new_lng = dest_lat, dest_lng
            if target_order.status == "packed":
                target_order.status = "out_for_delivery"
                target_order.picked_up_at = now
                _log_event(session, target_order.id, "PICKED_UP")
            else:
                target_order.status = "delivered"
                target_order.delivered_at = now
                new_load = max(0.0, rider.current_load_kg - target_order.weight_kg)
                _log_event(session, target_order.id, "DELIVERED")
        else:
            frac = step_km / dist_km
            new_lat = rider.lat + (dest_lat - rider.lat) * frac
            new_lng = rider.lng + (dest_lng - rider.lng) * frac
        sync(rider, new_lat, new_lng, "ON_DELIVERY", new_load)

    return bulk_updates


def recompute_risk(session, ctx):
    # Only assign o.risk when it actually changes: an unconditional assignment marks every active
    # order dirty every tick regardless of value, turning one UPDATE-per-changed-row into one
    # UPDATE-per-active-order on every single commit — the dominant remaining per-tick DB cost,
    # measured directly (recompute_risk touching ~30 rows/tick was ~30 extra round trips at commit).
    now = dt.datetime.now(dt.timezone.utc)
    for o in ctx["all_orders"]:
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
            if new_risk in ("DELAYED", "SEVERE"):
                _log_event(session, o.id, "DELAY_RISK", {"slack_minutes": round(slack_min, 1)})


def reoptimize_routes(ctx):
    by_rider = _group_by(ctx["all_orders"], ACTIVE_STATUSES, "rider_id")
    for rider in ctx["riders"]:
        pending = sorted(by_rider.get(rider.id, []), key=lambda o: o.route_seq or 0)
        rolling_reoptimize_sync(rider, pending)


def build_snapshot(stores, riders, orders) -> dict:
    """Builds the WS payload from data already fetched this tick — zero extra round trips."""
    return {
        "type": "tick",
        "dark_stores": [{"id": s.id, "name": s.name, "lat": s.lat, "lng": s.lng} for s in stores],
        "traffic_zones": [
            {"id": z["id"], "lat": z["lat"], "lng": z["lng"], "radius_km": z["radius_km"]}
            for z in active_traffic_zones()
        ],
        "riders": [
            {"id": r.id, "name": r.name, "lat": r.lat, "lng": r.lng, "status": r.status,
             "current_load_kg": r.current_load_kg, "capacity_kg": r.capacity_kg,
             "utilization": round(100 * r.current_load_kg / r.capacity_kg) if r.capacity_kg else 0,
             "battery_pct": r.battery_pct}
            for r in riders
        ],
        "orders": [
            {"id": o.id, "lat": o.customer_lat, "lng": o.customer_lng, "status": o.status,
             "priority": o.priority, "risk": o.risk, "rider_id": o.rider_id, "store_id": o.store_id,
             "promised_at": o.promised_at.isoformat()}
            for o in orders
        ],
    }


ORDER_MUTABLE_COLUMNS = ["status", "risk", "store_id", "rider_id", "route_seq",
                          "assigned_at", "packed_at", "picked_up_at", "delivered_at", "assignment_reason"]
INVENTORY_MUTABLE_COLUMNS = ["reserved_qty"]


def _bulk_flush_dirty(session, model, columns):
    """Collect every dirty (already-persistent) instance of `model` in the session and write them
    back in ONE bulk UPDATE instead of letting autoflush issue one UPDATE per row. Orders and
    inventory rows each get touched a handful of times per tick (new assignments, packing/delivery
    transitions, stock reservation) — without this, every one of those was its own round trip."""
    dirty = [o for o in session.dirty if isinstance(o, model)]
    if not dirty:
        return []
    rows = []
    for obj in dirty:
        row = {"id": obj.id}
        for col in columns:
            row[col] = getattr(obj, col)
        rows.append(row)
        for col in columns:
            set_committed_value(obj, col, getattr(obj, col))
    return rows


async def tick(session):
    """Runs against a long-lived session (see run_forever) — opening a fresh connection every 2s
    was costing ~5-20s per tick in Neon connection/TLS/auth handshake alone, measured directly.
    Reusing one connection across ticks drops per-query cost from seconds to ~0.2s. The bulk
    UPDATEs below matter just as much: autoflush issues one UPDATE per dirty row, and with 15
    riders + dozens of orders changing every tick that was still dozens of extra round trips."""
    stores = (await session.execute(select(DarkStore))).scalars().all()
    store_by_id = {s.id: s for s in stores}
    ctx = await fetch_tick_context(session, stores)

    if _rng.random() < state["order_spawn_rate"]:
        new_order = spawn_order(session, stores)
        if new_order:
            ctx["all_orders"].append(new_order)

    for o in [o for o in ctx["all_orders"] if o.status == "created"]:
        try_allocate(session, o, stores, store_by_id, ctx)

    advance_packing(session, stores, ctx)
    rider_updates = move_riders(session, store_by_id, ctx)
    recompute_risk(session, ctx)
    reoptimize_routes(ctx)

    inventory_rows = _bulk_flush_dirty(session, InventoryItem, INVENTORY_MUTABLE_COLUMNS)
    order_rows = _bulk_flush_dirty(session, Order, ORDER_MUTABLE_COLUMNS)
    if rider_updates:
        await session.execute(sa_update(Rider), rider_updates)
    if inventory_rows:
        await session.execute(sa_update(InventoryItem), inventory_rows)
    if order_rows:
        await session.execute(sa_update(Order), order_rows)
    await session.commit()
    visible_orders = [o for o in ctx["all_orders"] if o.status not in ("delivered", "failed", "cancelled")]
    payload = build_snapshot(stores, ctx["riders"], visible_orders)
    await manager.broadcast(payload)


async def run_forever():
    session = SessionLocal()
    try:
        while True:
            try:
                await tick(session)
            except Exception as e:  # ponytail: log-and-continue keeps the demo alive; add alerting if this ever fires in prod
                print(f"[simulator] tick error: {e}")
                try:
                    await session.rollback()
                except Exception:
                    pass
                try:
                    await session.close()
                except Exception:
                    pass
                session = SessionLocal()  # dropped/stale connection -> reconnect and try again next tick
            await asyncio.sleep(TICK_SECONDS)
    finally:
        await session.close()
