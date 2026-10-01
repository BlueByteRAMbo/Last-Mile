import asyncio
import datetime as dt
import json
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from .db import engine, Base, SessionLocal
from .models import DarkStore, InventoryItem, Rider, Order, OrderEvent
from .seed_data import build_seed_entities
from .dispatch import (
    score_candidates_sync, cheapest_insertion_cost, travel_seconds,
    add_traffic_zone, clear_traffic_zones, riders_affected_by_zone_sync,
    rolling_reoptimize_sync, active_traffic_zones,
)
from . import simulator
from . import world as world_module
from .catalog import CATALOG, CATALOG_BY_SKU
from .world import world
from .ws import manager

_background_tasks: list[asyncio.Task] = []


async def seed_db_if_empty():
    async with SessionLocal() as session:
        count = (await session.execute(select(func.count()).select_from(DarkStore))).scalar_one()
        if count:
            return
        stores, inventory, riders = build_seed_entities()
        session.add_all(stores + inventory + riders)
        await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .db import auto_migrate
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await auto_migrate(conn)
    await seed_db_if_empty()
    await world_module.load_world()
    _background_tasks.append(asyncio.create_task(simulator.run_forever()))
    _background_tasks.append(asyncio.create_task(simulator.persist_loop()))
    yield
    for t in _background_tasks:
        t.cancel()


app = FastAPI(title="Last Mile Mission Control", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/dark_stores")
async def list_dark_stores():
    out = []
    for s in world.stores:
        packing = sum(1 for o in world.orders.values() if o.store_id == s.id and o.status == "packing")
        queued = sum(1 for o in world.orders.values() if o.store_id == s.id and o.status == "assigned")
        out.append({
            "id": s.id, "name": s.name, "lat": s.lat, "lng": s.lng,
            "packing_capacity": s.packing_capacity, "packing_now": packing, "queued": queued,
        })
    return out


STAGE_ORDER = ["created", "assigned", "packing", "packed", "out_for_delivery", "delivered"]
STAGE_LABELS = {
    "created": "Placed", "assigned": "Accepted", "packing": "Packing", "packed": "Packed",
    "out_for_delivery": "Out for delivery", "delivered": "Delivered",
    "cancelled": "Cancelled", "failed": "Failed",
}


@app.get("/track/{order_id}")
async def track_order(order_id: str):
    """Customer-safe view: no internal scoring/cost data, just lifecycle + live ETA + rider position."""
    order = world.orders.get(order_id)
    if order is None:
        raise HTTPException(404, "order not found")

    rider_pos = None
    eta_seconds = None
    rider_name = None
    if order.rider_id:
        rider = world.rider_by_id.get(order.rider_id)
        if rider:
            rider_pos = {"lat": rider.lat, "lng": rider.lng}
            eta_seconds = round(travel_seconds(rider.lat, rider.lng, order.customer_lat, order.customer_lng, rider.speed_kmh), 1)
            rider_name = rider.name

    store_name = world.store_by_id[order.store_id].name if order.store_id in world.store_by_id else None
    stage_index = STAGE_ORDER.index(order.status) if order.status in STAGE_ORDER else -1

    return {
        "order_id": order.id,
        "status": order.status,
        "status_label": STAGE_LABELS.get(order.status, order.status),
        "stages": [{"key": s, "label": STAGE_LABELS[s], "done": i <= stage_index} for i, s in enumerate(STAGE_ORDER)],
        "risk": order.risk,
        "priority": order.priority,
        "store_name": store_name,
        "items": order.items,
        "customer_name": order.customer_name,
        "address_label": order.address_label,
        "promised_at": order.promised_at.isoformat(),
        "created_at": order.created_at.isoformat(),
        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
        "rider_position": rider_pos,
        "rider_name": rider_name,
        "eta_seconds": eta_seconds,
        "customer_location": {"lat": order.customer_lat, "lng": order.customer_lng},
    }


@app.get("/traffic_zones")
async def traffic_zones():
    return [{"id": z["id"], "lat": z["lat"], "lng": z["lng"], "radius_km": z["radius_km"]} for z in active_traffic_zones()]


@app.get("/catalog")
async def catalog():
    return CATALOG


@app.get("/catalog/availability")
async def catalog_availability(skus: str, customer_lat: float | None = None, customer_lng: float | None = None):
    """Per store: can it fulfil every requested SKU, how much of each is available, and how far/how
    long to get there from the customer — the data the storefront's stock-check step highlights."""
    requested = [s for s in skus.split(",") if s]
    out = []
    for store in world.stores:
        per_item = {}
        has_all = True
        for sku in requested:
            row = world.inventory.get((store.id, sku))
            available = (row.qty - row.reserved_qty) if row else 0
            per_item[sku] = available
            if available <= 0:
                has_all = False
        entry = {"store_id": store.id, "store_name": store.name, "has_all_items": has_all, "available": per_item}
        if customer_lat is not None and customer_lng is not None:
            from .dispatch import haversine_km, travel_seconds as _travel
            entry["distance_km"] = round(haversine_km(customer_lat, customer_lng, store.lat, store.lng), 2)
            entry["eta_seconds"] = round(_travel(store.lat, store.lng, customer_lat, customer_lng, 28.0), 0)
        out.append(entry)
    out.sort(key=lambda e: (not e["has_all_items"], e.get("distance_km", 0)))
    return out


@app.get("/dark_stores/{store_id}/inventory")
async def store_inventory(store_id: str):
    rows = [v for (sid, _sku), v in world.inventory.items() if sid == store_id]
    return [{
        "sku": r.sku, "name": r.name, "qty": r.qty, "reserved_qty": r.reserved_qty,
        "available": r.qty - r.reserved_qty,
        "category": CATALOG_BY_SKU.get(r.sku, {}).get("category"),
        "emoji": CATALOG_BY_SKU.get(r.sku, {}).get("emoji"),
        "low_stock": 0 < (r.qty - r.reserved_qty) <= 10,
        "out_of_stock": (r.qty - r.reserved_qty) <= 0,
    } for r in rows]


class RestockBody(BaseModel):
    sku: str
    qty: int = Field(gt=0, le=500)


@app.post("/dark_stores/{store_id}/restock")
async def restock_store(store_id: str, body: RestockBody):
    key = (store_id, body.sku)
    row = world.inventory.get(key)
    if row is None:
        raise HTTPException(404, "store or sku not found")
    row.qty += body.qty
    world.mark_inventory_dirty(key)
    return {"ok": True, "store_id": store_id, "sku": body.sku, "qty": row.qty, "available": row.qty - row.reserved_qty}


@app.get("/riders")
async def list_riders():
    return [{
        "id": r.id, "name": r.name, "lat": r.lat, "lng": r.lng, "status": r.status,
        "capacity_kg": r.capacity_kg, "current_load_kg": r.current_load_kg,
        "utilization": round(100 * r.current_load_kg / r.capacity_kg) if r.capacity_kg else 0,
        "battery_pct": round(r.battery_pct, 1),
    } for r in world.riders]


@app.get("/orders")
async def list_orders(status: str | None = None):
    orders = list(world.orders.values())
    if status:
        orders = [o for o in orders if o.status == status]
    orders.sort(key=lambda o: o.created_at, reverse=True)
    return [{
        "id": o.id, "lat": o.customer_lat, "lng": o.customer_lng, "status": o.status,
        "priority": o.priority, "risk": o.risk, "store_id": o.store_id, "rider_id": o.rider_id,
        "items": o.items, "weight_kg": o.weight_kg,
        "customer_name": o.customer_name, "address_label": o.address_label,
        "promised_at": o.promised_at.isoformat(), "created_at": o.created_at.isoformat(),
    } for o in orders[:200]]


class OrderItemIn(BaseModel):
    sku: str
    name: str
    qty: int = 1
    weight_kg: float = 0.3


class OrderCreate(BaseModel):
    customer_lat: float
    customer_lng: float
    items: list[OrderItemIn]
    priority: bool = False
    promise_minutes: int = Field(default=20, ge=5, le=120)
    customer_name: str = "Customer"
    address_label: str = ""


@app.post("/orders")
async def create_order(body: OrderCreate):
    """Customer-facing order placement. Written straight into world state so the very next tick
    can allocate it — no DB round trip on the request path."""
    items = [it.model_dump() for it in body.items]
    weight = sum(it["qty"] * it["weight_kg"] for it in items)
    now = dt.datetime.now(dt.timezone.utc)
    order = Order(
        id=f"ORD-{uuid.uuid4().hex[:8].upper()}",
        customer_lat=body.customer_lat, customer_lng=body.customer_lng,
        customer_name=body.customer_name or "Customer", address_label=body.address_label,
        items=items, weight_kg=round(weight, 2), priority=body.priority,
        created_at=now, promised_at=now + dt.timedelta(minutes=body.promise_minutes),
        status="created", risk="LOW",
    )
    world.add_new_order(order)
    world.log_event(order.id, "ORDER_CREATED", {"priority": body.priority, "source": "api"})
    return {"id": order.id, "status": order.status}


@app.get("/riders/{rider_id}/route")
async def rider_route(rider_id: str):
    """Ordered stops for the Optimization tab: stop type, order id, ETA, cumulative load, deadline slack, route version."""
    rider = world.rider_by_id.get(rider_id)
    if rider is None:
        raise HTTPException(404, "rider not found")
    active = sorted(
        [o for o in world.orders.values() if o.rider_id == rider_id and o.status in
         ("assigned", "packing", "packed", "out_for_delivery")],
        key=lambda o: o.route_seq or 0,
    )

    now = dt.datetime.now(dt.timezone.utc)
    stops = []
    cursor_lat, cursor_lng = rider.lat, rider.lng
    cum_eta = 0.0
    cum_load = 0.0
    for o in active:
        if o.status in ("assigned", "packing") and o.store_id:
            store = world.store_by_id[o.store_id]
            leg = travel_seconds(cursor_lat, cursor_lng, store.lat, store.lng, rider.speed_kmh)
            cum_eta += leg
            cursor_lat, cursor_lng = store.lat, store.lng
            stops.append({
                "stop_type": "PICKUP", "order_id": o.id, "store_id": o.store_id,
                "eta_seconds": round(cum_eta, 1), "cumulative_load_kg": round(cum_load, 2),
            })
        leg = travel_seconds(cursor_lat, cursor_lng, o.customer_lat, o.customer_lng, rider.speed_kmh)
        cum_eta += leg
        cursor_lat, cursor_lng = o.customer_lat, o.customer_lng
        cum_load += o.weight_kg
        deadline_slack = (o.promised_at - now).total_seconds() - cum_eta
        stops.append({
            "stop_type": "DROPOFF", "order_id": o.id, "status": o.status,
            "eta_seconds": round(cum_eta, 1), "cumulative_load_kg": round(cum_load, 2),
            "deadline_slack_seconds": round(deadline_slack, 1),
        })
    return {"rider_id": rider_id, "route_version": len(active), "stops": stops}


@app.get("/orders/{order_id}/explain")
async def explain_order(order_id: str):
    """Inspector payload: chosen store/rider + ranked alternatives + reasons."""
    order = world.orders.get(order_id)
    if order is None:
        return {"error": "not_found"}
    decision = json.loads(order.assignment_reason) if order.assignment_reason else {"chosen": None, "alternatives": []}
    active_by_rider: dict[str, list] = {}
    for o in world.active_orders():
        if o.rider_id:
            active_by_rider.setdefault(o.rider_id, []).append(o)
    candidates = score_candidates_sync(order, world.stores, world.riders, active_by_rider, world.inventory)

    events = []
    async with SessionLocal() as session:
        rows = (await session.execute(select(OrderEvent).where(OrderEvent.order_id == order_id).order_by(OrderEvent.ts))).scalars().all()
        events = [{"type": e.type, "ts": e.ts.isoformat(), "payload": e.payload} for e in rows]

    return {
        "order_id": order_id,
        "status": order.status,
        "risk": order.risk,
        "decision": decision,
        "current_candidates": candidates[:6],
        "events": events,
    }


@app.get("/kpis")
async def kpis():
    orders = list(world.orders.values())
    delivered = [o for o in orders if o.status == "delivered"]
    failed_count = sum(1 for o in orders if o.status in ("failed", "cancelled"))
    terminal = len(delivered) + failed_count

    avg_delivery_min = 0.0
    on_time = 0
    if delivered:
        total_min = sum((o.delivered_at - o.created_at).total_seconds() / 60.0 for o in delivered)
        avg_delivery_min = round(total_min / len(delivered), 1)
        on_time = sum(1 for o in delivered if o.delivered_at <= o.promised_at)

    riders = [r for r in world.riders if r.status != "OFFLINE"]
    busy = sum(1 for r in riders if r.status == "ON_DELIVERY")
    utilization = round(100 * busy / len(riders), 1) if riders else 0.0

    zone_counts: dict[str, int] = {}
    active = world.active_orders()
    for o in active:
        key = f"{round(o.customer_lat, 2)},{round(o.customer_lng, 2)}"
        zone_counts[key] = zone_counts.get(key, 0) + 1

    return {
        "avg_delivery_minutes": avg_delivery_min,
        "on_time_rate_pct": round(100 * on_time / len(delivered), 1) if delivered else 100.0,
        "rider_utilization_pct": utilization,
        "sla_breach_rate_pct": round(100 * (len(delivered) - on_time + failed_count) / terminal, 1) if terminal else 0.0,
        "failed_count": failed_count,
        "delivered_count": len(delivered),
        "active_orders": len(active),
        "zone_density": [{"zone": k, "count": v} for k, v in sorted(zone_counts.items(), key=lambda x: -x[1])[:10]],
    }


@app.post("/disruptions/{kind}")
async def trigger_disruption(kind: str, target: str | None = None):
    if kind == "traffic":
        if len(world.stores) >= 2:
            import random
            a, b = random.sample(world.stores, 2)
            zone_lat, zone_lng = (a.lat + b.lat) / 2, (a.lng + b.lng) / 2
        elif world.stores:
            zone_lat, zone_lng = world.stores[0].lat, world.stores[0].lng
        else:
            zone_lat, zone_lng = 19.07, 72.87
        zone = add_traffic_zone(zone_lat, zone_lng, radius_km=2.5, multiplier=0.35, duration_minutes=6)
        affected_riders = riders_affected_by_zone_sync(zone, world.riders, world.active_orders())
        for rid in affected_riders:
            rider = world.rider_by_id[rid]
            pending = sorted([o for o in world.active_orders() if o.rider_id == rid], key=lambda o: o.route_seq or 0)
            rolling_reoptimize_sync(rider, pending)
            for o in pending:
                world.mark_order_dirty(o.id)
                world.log_event(o.id, "ROUTE_CHANGED", {"reason": "traffic_zone", "zone_id": zone["id"]})
        return {"ok": True, "kind": kind, "zone": {k: v for k, v in zone.items() if k != "expires_at"}, "affected_riders": affected_riders}
    elif kind == "clear_traffic":
        clear_traffic_zones()
    elif kind == "surge":
        simulator.state["order_spawn_rate"] = min(0.9, simulator.state["order_spawn_rate"] + 0.35)
    elif kind == "rider_offline" and target:
        rider = world.rider_by_id.get(target)
        if rider:
            rider.status = "OFFLINE"
            world.mark_rider_dirty(target)
            freed = world.reassign_rider_orders(target)
            for oid in freed:
                world.log_event(oid, "RIDER_OFFLINE", {"rider_id": target})
    elif kind == "stockout" and target:
        for (sid, _sku), row in world.inventory.items():
            if sid == target:
                row.qty = row.reserved_qty
                world.mark_inventory_dirty((sid, row.sku))
    elif kind == "cancel" and target:
        order = world.orders.get(target)
        if order and world.cancel_order(order):
            world.log_event(order.id, "CANCELLED", {})
    else:
        return {"ok": False, "error": "unknown kind"}
    return {"ok": True, "kind": kind, "state": {"order_spawn_rate": simulator.state["order_spawn_rate"]}}


@app.post("/reset")
async def reset():
    async with world_module.db_write_lock:  # hold through delete + reseed + reload so persist_loop can't interleave
        async with SessionLocal() as session:
            from sqlalchemy import delete
            await session.execute(delete(OrderEvent))
            await session.execute(delete(Order))
            await session.execute(delete(Rider))
            await session.execute(delete(InventoryItem))
            await session.execute(delete(DarkStore))
            await session.commit()
        simulator.state.update({"order_spawn_rate": 0.35, "blocked_store_ids": set()})
        simulator.reset_rng()
        clear_traffic_zones()
        await seed_db_if_empty()
        await world_module.load_world()
    return {"ok": True}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
