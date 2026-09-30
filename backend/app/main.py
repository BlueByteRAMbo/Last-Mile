import asyncio
import datetime as dt
import json
import uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete

from .db import engine, Base, SessionLocal
from .models import DarkStore, InventoryItem, Rider, Order, OrderEvent
from .seed_data import build_seed_entities
from .dispatch import (
    score_candidates, cheapest_insertion_cost, reassign_rider_orders, cancel_order, travel_seconds,
    add_traffic_zone, clear_traffic_zones, riders_affected_by_zone, rolling_reoptimize, active_traffic_zones,
)
from . import simulator
from .ws import manager

app = FastAPI(title="Last Mile Mission Control")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_sim_task: asyncio.Task | None = None


async def seed_if_empty():
    async with SessionLocal() as session:
        count = (await session.execute(select(func.count()).select_from(DarkStore))).scalar_one()
        if count:
            return
        stores, inventory, riders = build_seed_entities()
        session.add_all(stores + inventory + riders)
        await session.commit()


@app.on_event("startup")
async def startup():
    global _sim_task
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_if_empty()
    _sim_task = asyncio.create_task(simulator.run_forever())


@app.get("/dark_stores")
async def list_dark_stores():
    async with SessionLocal() as session:
        stores = (await session.execute(select(DarkStore))).scalars().all()
        out = []
        for s in stores:
            packing = (await session.execute(
                select(func.count()).select_from(Order).where(Order.store_id == s.id, Order.status == "packing")
            )).scalar_one()
            queued = (await session.execute(
                select(func.count()).select_from(Order).where(Order.store_id == s.id, Order.status == "assigned")
            )).scalar_one()
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
    async with SessionLocal() as session:
        order = (await session.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
        if order is None:
            raise HTTPException(404, "order not found")

        rider_pos = None
        eta_seconds = None
        if order.rider_id:
            rider = (await session.execute(select(Rider).where(Rider.id == order.rider_id))).scalar_one_or_none()
            if rider:
                rider_pos = {"lat": rider.lat, "lng": rider.lng}
                eta_seconds = round(travel_seconds(rider.lat, rider.lng, order.customer_lat, order.customer_lng, rider.speed_kmh), 1)

        store_name = None
        if order.store_id:
            store = (await session.execute(select(DarkStore).where(DarkStore.id == order.store_id))).scalar_one_or_none()
            store_name = store.name if store else None

        current_stage = order.status if order.status in STAGE_ORDER else (STAGE_ORDER[0] if order.status == "created" else None)
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
            "promised_at": order.promised_at.isoformat(),
            "created_at": order.created_at.isoformat(),
            "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
            "rider_position": rider_pos,
            "eta_seconds": eta_seconds,
            "customer_location": {"lat": order.customer_lat, "lng": order.customer_lng},
        }


@app.get("/traffic_zones")
async def traffic_zones():
    return [{"id": z["id"], "lat": z["lat"], "lng": z["lng"], "radius_km": z["radius_km"]} for z in active_traffic_zones()]


@app.get("/catalog")
async def catalog():
    return [{"sku": sku, "name": name, "weight_kg": w} for sku, name, w in simulator.SKU_CATALOG]


@app.get("/dark_stores/{store_id}/inventory")
async def store_inventory(store_id: str):
    async with SessionLocal() as session:
        rows = (await session.execute(select(InventoryItem).where(InventoryItem.store_id == store_id))).scalars().all()
        return [{"sku": r.sku, "name": r.name, "qty": r.qty, "reserved_qty": r.reserved_qty, "available": r.qty - r.reserved_qty} for r in rows]


@app.get("/riders")
async def list_riders():
    async with SessionLocal() as session:
        riders = (await session.execute(select(Rider))).scalars().all()
        return [{
            "id": r.id, "name": r.name, "lat": r.lat, "lng": r.lng, "status": r.status,
            "capacity_kg": r.capacity_kg, "current_load_kg": r.current_load_kg,
            "utilization": round(100 * r.current_load_kg / r.capacity_kg) if r.capacity_kg else 0,
            "battery_pct": r.battery_pct,
        } for r in riders]


@app.get("/orders")
async def list_orders(status: str | None = None):
    async with SessionLocal() as session:
        q = select(Order)
        if status:
            q = q.where(Order.status == status)
        orders = (await session.execute(q.order_by(Order.created_at.desc()).limit(200))).scalars().all()
        return [{
            "id": o.id, "lat": o.customer_lat, "lng": o.customer_lng, "status": o.status,
            "priority": o.priority, "risk": o.risk, "store_id": o.store_id, "rider_id": o.rider_id,
            "items": o.items, "weight_kg": o.weight_kg,
            "promised_at": o.promised_at.isoformat(), "created_at": o.created_at.isoformat(),
        } for o in orders]


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


@app.post("/orders")
async def create_order(body: OrderCreate):
    """Customer-facing order placement. Picked up by the next simulator tick for allocation."""
    async with SessionLocal() as session:
        items = [it.model_dump() for it in body.items]
        weight = sum(it["qty"] * it["weight_kg"] for it in items)
        now = dt.datetime.now(dt.timezone.utc)
        order = Order(
            id=f"ORD-{uuid.uuid4().hex[:8].upper()}",
            customer_lat=body.customer_lat, customer_lng=body.customer_lng,
            items=items, weight_kg=round(weight, 2), priority=body.priority,
            created_at=now, promised_at=now + dt.timedelta(minutes=body.promise_minutes),
            status="created",
        )
        session.add(order)
        await session.flush()
        session.add(OrderEvent(order_id=order.id, type="ORDER_CREATED", payload={"priority": body.priority, "source": "api"}))
        await session.commit()
        return {"id": order.id, "status": order.status}


@app.get("/riders/{rider_id}/route")
async def rider_route(rider_id: str):
    """Ordered stops for the Optimization tab: stop type, order id, ETA, cumulative load, deadline slack, route version."""
    async with SessionLocal() as session:
        rider = (await session.execute(select(Rider).where(Rider.id == rider_id))).scalar_one_or_none()
        if rider is None:
            raise HTTPException(404, "rider not found")
        active = (await session.execute(
            select(Order).where(Order.rider_id == rider_id, Order.status.in_(["assigned", "packing", "packed", "out_for_delivery"]))
            .order_by(Order.route_seq)
        )).scalars().all()

        now = dt.datetime.now(dt.timezone.utc)
        stops = []
        cursor_lat, cursor_lng = rider.lat, rider.lng
        cum_eta = 0.0
        cum_load = 0.0
        for o in active:
            if o.status in ("assigned", "packing") and o.store_id:
                store = (await session.execute(select(DarkStore).where(DarkStore.id == o.store_id))).scalar_one()
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
    async with SessionLocal() as session:
        order = (await session.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
        if order is None:
            return {"error": "not_found"}
        if order.assignment_reason:
            decision = json.loads(order.assignment_reason)
        else:
            decision = {"chosen": None, "alternatives": []}
        candidates = await score_candidates(session, order)
        events = (await session.execute(
            select(OrderEvent).where(OrderEvent.order_id == order_id).order_by(OrderEvent.ts)
        )).scalars().all()
        return {
            "order_id": order_id,
            "status": order.status,
            "risk": order.risk,
            "decision": decision,
            "current_candidates": candidates[:6],
            "events": [{"type": e.type, "ts": e.ts.isoformat(), "payload": e.payload} for e in events],
        }


@app.get("/kpis")
async def kpis():
    async with SessionLocal() as session:
        delivered = (await session.execute(select(Order).where(Order.status == "delivered"))).scalars().all()
        failed_count = (await session.execute(
            select(func.count()).select_from(Order).where(Order.status.in_(["failed", "cancelled"]))
        )).scalar_one()
        terminal = len(delivered) + failed_count

        avg_delivery_min = 0.0
        on_time = 0
        if delivered:
            total_min = sum((o.delivered_at - o.created_at).total_seconds() / 60.0 for o in delivered)
            avg_delivery_min = round(total_min / len(delivered), 1)
            on_time = sum(1 for o in delivered if o.delivered_at <= o.promised_at)

        riders = (await session.execute(select(Rider).where(Rider.status != "OFFLINE"))).scalars().all()
        busy = sum(1 for r in riders if r.status == "ON_DELIVERY")
        utilization = round(100 * busy / len(riders), 1) if riders else 0.0

        zone_counts: dict[str, int] = {}
        active = (await session.execute(
            select(Order).where(Order.status.notin_(["delivered", "failed", "cancelled"]))
        )).scalars().all()
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
    async with SessionLocal() as session:
        if kind == "traffic":
            stores = (await session.execute(select(DarkStore))).scalars().all()
            if len(stores) >= 2:
                import random
                a, b = random.sample(stores, 2)
                zone_lat, zone_lng = (a.lat + b.lat) / 2, (a.lng + b.lng) / 2
            elif stores:
                zone_lat, zone_lng = stores[0].lat, stores[0].lng
            else:
                zone_lat, zone_lng = 19.07, 72.87
            zone = add_traffic_zone(zone_lat, zone_lng, radius_km=2.5, multiplier=0.35, duration_minutes=6)
            # react immediately instead of waiting for the next tick: resequence every route this zone touches
            affected_riders = await riders_affected_by_zone(session, zone)
            for rid in affected_riders:
                await rolling_reoptimize(session, rid)
            affected_orders = (await session.execute(
                select(Order).where(Order.rider_id.in_(affected_riders), Order.status.in_(
                    ["assigned", "packing", "packed", "out_for_delivery"]))
            )).scalars().all() if affected_riders else []
            for o in affected_orders:
                session.add(OrderEvent(order_id=o.id, type="ROUTE_CHANGED", payload={"reason": "traffic_zone", "zone_id": zone["id"]}))
            await session.commit()
            return {"ok": True, "kind": kind, "zone": {k: v for k, v in zone.items() if k != "expires_at"}, "affected_riders": affected_riders}
        elif kind == "clear_traffic":
            clear_traffic_zones()
        elif kind == "surge":
            simulator.state["order_spawn_rate"] = min(0.9, simulator.state["order_spawn_rate"] + 0.35)
        elif kind == "rider_offline" and target:
            rider = (await session.execute(select(Rider).where(Rider.id == target))).scalar_one_or_none()
            if rider:
                rider.status = "OFFLINE"
                freed = await reassign_rider_orders(session, target)
                for oid in freed:
                    session.add(OrderEvent(order_id=oid, type="RIDER_OFFLINE", payload={"rider_id": target}))
                await session.commit()
        elif kind == "stockout" and target:
            rows = (await session.execute(select(InventoryItem).where(InventoryItem.store_id == target))).scalars().all()
            for row in rows:
                row.qty = row.reserved_qty
            await session.commit()
        elif kind == "cancel" and target:
            order = (await session.execute(select(Order).where(Order.id == target))).scalar_one_or_none()
            if order and await cancel_order(session, order):
                session.add(OrderEvent(order_id=order.id, type="CANCELLED", payload={}))
                await session.commit()
        else:
            return {"ok": False, "error": "unknown kind"}
        return {"ok": True, "kind": kind, "state": simulator.state}


@app.post("/reset")
async def reset():
    async with SessionLocal() as session:
        await session.execute(delete(OrderEvent))
        await session.execute(delete(Order))
        await session.execute(delete(Rider))
        await session.execute(delete(InventoryItem))
        await session.execute(delete(DarkStore))
        await session.commit()
    simulator.state.update({"speed_multiplier": 1.0, "order_spawn_rate": 0.35, "blocked_store_ids": set()})
    simulator._rng.seed(simulator.SEED)
    await seed_if_empty()
    return {"ok": True}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
