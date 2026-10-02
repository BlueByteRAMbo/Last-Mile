import asyncio
import datetime as dt
import json
import uuid
from contextlib import asynccontextmanager
from typing import Literal
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from .db import engine, Base, SessionLocal
from .models import DarkStore, InventoryItem, Rider, Order, OrderEvent
from .seed_data import build_seed_entities
from .dispatch import (
    score_candidates_sync, cheapest_insertion_cost, travel_seconds,
    add_traffic_zone, clear_traffic_zones, riders_affected_by_zone_sync,
    rolling_reoptimize_sync, active_traffic_zones, estimate_zone_adjusted_duration,
)
from . import simulator
from . import world as world_module
from . import routing
from .catalog import CATALOG, CATALOG_BY_SKU
from .world import world
from .tracking import delivery_etas, order_tracking, rider_route as tracking_rider_route
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
# Only the app's own front-end origins may call the API from a browser (override with CORS_ORIGINS).
CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])

OPS_TOKEN = os.environ.get("OPS_TOKEN")


async def require_ops(x_ops_request: str | None = Header(default=None), x_ops_token: str | None = Header(default=None)):
    """Guards state-changing operator endpoints (reset, disruptions, restock, interventions, sim controls).
    A custom header cannot be sent cross-site without a CORS preflight, which the origin allow-list above
    refuses, so a random web page can no longer fire these at a local server. Set OPS_TOKEN to also
    require a shared secret (sent as X-Ops-Token) when the API is exposed beyond localhost."""
    if x_ops_request is None:
        raise HTTPException(403, "Operator endpoint: missing X-Ops-Request header")
    if OPS_TOKEN and x_ops_token != OPS_TOKEN:
        raise HTTPException(403, "Operator endpoint: invalid token")


class DispatchMode(BaseModel):
    mode: Literal['nearest', 'optimized']


@app.get('/dispatch/mode')
async def dispatch_mode():
    return {'mode': simulator.state['dispatch_mode']}


@app.post('/dispatch/mode', dependencies=[Depends(require_ops)])
async def set_dispatch_mode(body: DispatchMode):
    simulator.state['dispatch_mode'] = body.mode
    return {'mode': body.mode}


class SimSpeedBody(BaseModel):
    multiplier: Literal[1, 10, 20, 40]


@app.get('/simulation/speed')
async def get_sim_speed():
    return {'multiplier': simulator.state['tick_speed_multiplier']}


@app.post('/simulation/speed', dependencies=[Depends(require_ops)])
async def set_sim_speed(body: SimSpeedBody):
    simulator.state['tick_speed_multiplier'] = body.multiplier
    return {'multiplier': body.multiplier}


@app.get('/analytics/comparison')
async def dispatch_comparison():
    from .comparison import comparison
    try:
        return await comparison()
    except (RuntimeError, OSError, asyncio.TimeoutError):
        raise HTTPException(503, 'Comparison could not finish; please retry')


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
    from .tracking import customer_snapshot
    order = world.orders.get(order_id)
    if order is None:
        raise HTTPException(404, 'order not found')
    return customer_snapshot(order)


@app.websocket('/ws/track/{order_id}')
async def tracking_socket(websocket: WebSocket, order_id: str):
    await websocket.accept()
    if order_id not in world.orders:
        await websocket.send_json({'type': 'not_found'})
        await websocket.close(code=1008)
        return
    manager.tracking[websocket] = order_id
    try:
        await websocket.send_json(await track_order(order_id))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)


@app.get('/orders/{order_id}/journey')
async def order_journey(order_id: str):
    from .tracking import stock_check
    order = world.orders.get(order_id)
    if order is None:
        raise HTTPException(404, 'order not found')
    decision = json.loads(order.assignment_reason) if order.assignment_reason else {}
    return {'stock_check': order.stock_check or stock_check(order),
            'decision': decision,
            'route_history': [{'type': e.type, 'ts': e.ts.isoformat(), **(e.payload or {})}
                              for e in world.events if e.order_id == order_id and e.type in ('ROUTE_CHANGED', 'ROUTE_KEPT')]}


@app.get("/traffic_zones")
async def traffic_zones():
    return [{"id": z["id"], "lat": z["lat"], "lng": z["lng"], "radius_km": z["radius_km"]} for z in active_traffic_zones()]


@app.get("/debug/routing")
async def debug_routing():
    """Not part of the product surface — just visibility into whether real Mapbox routes are
    actually landing in the cache vs. everything silently staying on the haversine fallback."""
    real = sum(1 for r in routing._route_cache.values() if not r.get("approximate"))
    return {"cache_size": len(routing._route_cache), "real_routes": real, "in_flight": len(routing._in_flight),
            "token_configured": bool(routing.MAPBOX_TOKEN)}


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


@app.post("/dark_stores/{store_id}/restock", dependencies=[Depends(require_ops)])
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
    now = dt.datetime.now(dt.timezone.utc)
    etas = delivery_etas(world.active_orders(), now)
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
        **order_tracking(o, etas, now),
    } for o in orders[:200]]


@app.post("/orders/{order_id}/intervene/{action}", dependencies=[Depends(require_ops)])
async def intervene_order(order_id: str, action: str):
    order = world.orders.get(order_id)
    if order is None:
        raise HTTPException(404, "order not found")
    if action not in ("boost", "reassign", "cancel"):
        raise HTTPException(400, "unknown intervention")
    if order.status in ("delivered", "failed", "cancelled"):
        raise HTTPException(409, "This order is already finished")
    if action == "boost":
        if not order.priority:
            order.priority = True
            world.mark_order_dirty(order.id)
            world.log_event(order.id, "PRIORITY_BOOSTED", {"source": "operator"})
    elif action == "cancel":
        world.cancel_order(order)
        world.log_event(order.id, "CANCELLED", {"source": "operator"})
    else:
        if order.status not in ("assigned", "packing", "packed"):
            raise HTTPException(409, "Only orders awaiting pickup can be reassigned")
        store = world.store_by_id.get(order.store_id)
        if store is None:
            raise HTTPException(409, "Assigned store is unavailable")
        # Keep packing and reserved stock at the same store. Score an alternative
        # rider against a projection that includes this order's own reservation.
        from types import SimpleNamespace
        inventory = dict(world.inventory)
        for item in order.items:
            key = (order.store_id, item["sku"])
            row = inventory.get(key)
            if row:
                inventory[key] = SimpleNamespace(qty=row.qty, reserved_qty=max(0, row.reserved_qty - item["qty"]))
        by_rider = simulator._group_by(world.active_orders(), world_module.ACTIVE_STATUSES, "rider_id")
        candidates = score_candidates_sync(order, [store],
            [r for r in world.riders if r.id != order.rider_id], by_rider, inventory)
        chosen = next((c for c in candidates if c["feasible"]), None)
        if chosen is None:
            raise HTTPException(409, "No alternative rider is currently feasible; assignment kept")
        old_id = order.rider_id
        old_rider = world.rider_by_id.get(old_id)
        new_rider = world.rider_by_id[chosen["rider_id"]]
        pending = by_rider.get(new_rider.id, [])
        idx, _, feasible = cheapest_insertion_cost(new_rider, pending, order, store)
        if not feasible:
            raise HTTPException(409, "Alternative route would break a delivery promise; assignment kept")
        for other in pending:
            if (other.route_seq or 0) >= idx:
                other.route_seq = (other.route_seq or 0) + 1
                world.mark_order_dirty(other.id)
        if old_rider:
            old_rider.current_load_kg = max(0, old_rider.current_load_kg - order.weight_kg)
            old_rider.nav_target_lat = old_rider.nav_target_lng = None
            world.mark_rider_dirty(old_id)
        new_rider.current_load_kg += order.weight_kg
        new_rider.nav_target_lat = new_rider.nav_target_lng = None
        order.rider_id, order.route_seq = new_rider.id, idx
        order.assignment_reason = json.dumps({"chosen": chosen, "alternatives": candidates[1:5], "source": "operator"})
        world.mark_order_dirty(order.id)
        world.mark_rider_dirty(new_rider.id)
        world.log_event(order.id, "REASSIGNED", {"old_rider_id": old_id, "rider_id": new_rider.id, "source": "operator"})
    return {"ok": True, "id": order.id, "status": order.status, "priority": order.priority, "rider_id": order.rider_id}


class OrderItemIn(BaseModel):
    sku: str
    name: str
    qty: int = Field(default=1, ge=1, le=20)
    weight_kg: float = Field(default=0.3, gt=0)


class OrderCreate(BaseModel):
    customer_lat: float = Field(ge=-90, le=90)
    customer_lng: float = Field(ge=-180, le=180)
    items: list[OrderItemIn] = Field(min_length=1, max_length=30)
    priority: bool = False
    promise_minutes: int = Field(default=20, ge=5, le=120)
    customer_name: str = Field(default="Customer", max_length=100)
    address_label: str = Field(default="", max_length=250)


@app.post("/orders")
async def create_order(body: OrderCreate):
    """Customer-facing order placement. Written straight into world state so the very next tick
    can allocate it — no DB round trip on the request path."""
    from .geo import is_on_land
    if not is_on_land(body.customer_lat, body.customer_lng):
        raise HTTPException(422, "That delivery location is in the water or outside our service area. Please pick a spot on land.")
    items = [it.model_dump() for it in body.items]
    for item in items:
        product = CATALOG_BY_SKU.get(item['sku'])
        if product is None:
            raise HTTPException(422, 'Unknown catalog item')
        item['name'], item['weight_kg'] = product['name'], product['weight_kg']
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
    from .tracking import stock_check
    order.stock_check = stock_check(order)
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


@app.get("/riders/{rider_id}/detail")
async def rider_detail(rider_id: str):
    """Everything the ops map needs to explain one rider: current leg (from -> to), the road polyline
    being followed, and each order on board / waiting with its pickup store and drop-off."""
    rider = world.rider_by_id.get(rider_id)
    if rider is None:
        raise HTTPException(404, "rider not found")
    mine = sorted([o for o in world.orders.values() if o.rider_id == rider_id and o.status in
                   ("assigned", "packing", "packed", "out_for_delivery")], key=lambda o: o.route_seq or 0)

    def stop(order, kind):
        if kind == "store":
            s = world.store_by_id[order.store_id]
            return {"kind": "store", "label": s.name, "lat": s.lat, "lng": s.lng, "order_id": order.id}
        return {"kind": "customer", "label": f"{order.customer_name} · {order.address_label}".strip(" ·"),
                "lat": order.customer_lat, "lng": order.customer_lng, "order_id": order.id}

    route = tracking_rider_route(rider)
    # same target choice as simulator.move_riders: a packed order waiting at its store first, else the
    # next drop-off. Derived from orders (not nav_target) so there is no "idle" blip on the tick a
    # pickup clears the navigation state.
    leg_to = leg_from = None
    phase = "idle"
    waiting = next((o for o in mine if o.status == "packed" and o.store_id), None)
    onboard = next((o for o in mine if o.status == "out_for_delivery"), None)
    committed = next((o for o in mine if o.status == "out_for_delivery" and rider.nav_target_lat is not None
                      and (o.customer_lat, o.customer_lng) == (rider.nav_target_lat, rider.nav_target_lng)), None)
    if committed:  # mid-delivery leg wins over a newly packed order, mirroring simulator.move_riders
        onboard, waiting = committed, None
    if waiting:
        phase, leg_to = "to_store", stop(waiting, "store")
        leg_from = {"kind": "point", "label": "Leg start (rider's last position)",
                    "lat": rider.nav_origin_lat if rider.nav_origin_lat is not None else rider.lat,
                    "lng": rider.nav_origin_lng if rider.nav_origin_lng is not None else rider.lng}
    elif onboard:
        phase, leg_to = "to_customer", stop(onboard, "customer")
        leg_from = stop(onboard, "store") if onboard.store_id else None
    eta = round(route["distance_remaining_km"] / rider.speed_kmh * 3600) if rider.speed_kmh else None
    return {
        "id": rider.id, "name": rider.name, "status": rider.status, "lat": rider.lat, "lng": rider.lng,
        "speed_kmh": rider.speed_kmh, "battery_pct": round(rider.battery_pct, 1),
        "current_load_kg": rider.current_load_kg, "capacity_kg": rider.capacity_kg,
        "utilization": round(100 * rider.current_load_kg / rider.capacity_kg) if rider.capacity_kg else 0,
        "phase": phase, "leg_from": leg_from, "leg_to": leg_to, "leg_eta_seconds": eta,
        "polyline": route["polyline"], "polyline_remaining": route["polyline_remaining"],
        "distance_remaining_km": route["distance_remaining_km"],
        "orders": [{
            "id": o.id, "status": o.status, "risk": o.risk, "customer_name": o.customer_name,
            "address_label": o.address_label, "promised_at": o.promised_at.isoformat(),
            "store": {"id": o.store_id, "name": world.store_by_id[o.store_id].name} if o.store_id else None,
            "picked_up_at": o.picked_up_at.isoformat() if o.picked_up_at else None,
            "items": o.items, "weight_kg": o.weight_kg,
            "dropoff": {"lat": o.customer_lat, "lng": o.customer_lng},
        } for o in mine],
    }


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

    # Nearest-feasible-store ranking, independent of which rider ends up assigned — "why this store"
    # as its own question from "why this rider", per the explain spec.
    from .dispatch import check_stock, haversine_km
    store_ranking = []
    for store in world.stores:
        has_stock = check_stock(world.inventory, store.id, order.items)
        store_ranking.append({
            "store_id": store.id, "store_name": store.name, "has_all_items": has_stock,
            "distance_km": round(haversine_km(order.customer_lat, order.customer_lng, store.lat, store.lng), 2),
            "eta_seconds": round(travel_seconds(store.lat, store.lng, order.customer_lat, order.customer_lng, 28.0), 0),
        })
    store_ranking.sort(key=lambda s: (not s["has_all_items"], s["distance_km"]))

    chosen_vs_runner_up = None
    if decision.get("chosen") and decision.get("alternatives"):
        chosen_vs_runner_up = round(decision["alternatives"][0]["cost"] - decision["chosen"]["cost"], 2)

    events = [{"type": e.type, "ts": e.ts.isoformat() if e.ts else None, "payload": e.payload}
              for e in world.events if e.order_id == order_id]

    return {
        "order_id": order_id,
        "status": order.status,
        "risk": order.risk,
        "decision": decision,
        "chosen_vs_runner_up_cost_delta": chosen_vs_runner_up,
        "store_ranking": store_ranking,
        "current_candidates": candidates[:6],
        "events": events,
    }


@app.get("/analytics")
@app.get("/kpis")
async def kpis():
    from .analytics import build_analytics
    return build_analytics()


REROUTE_GAIN_THRESHOLD_SECONDS = 45.0
REROUTE_GAIN_THRESHOLD_PCT = 0.10


async def evaluate_reroute(rider, zone) -> dict:
    """Does switching the rider's current leg to an alternative road path save enough to be worth
    it, given this zone? Fetches real Mapbox alternatives from the rider's LIVE position (not the
    original nav_origin — rerouting happens from where you are now) to the same target. Switches
    the cached route in place only if the gain clears the threshold; otherwise explicitly reports
    "kept current route" so that outcome is just as visible as a switch."""
    current_route = routing.get_cached_route(rider.nav_origin_lat, rider.nav_origin_lng, rider.nav_target_lat, rider.nav_target_lng)
    current_polyline = tracking_rider_route(rider)['polyline_remaining']
    current_duration = estimate_zone_adjusted_duration(current_polyline, rider.speed_kmh, zone)
    start_state = (rider.lat, rider.lng, rider.nav_target_lat, rider.nav_target_lng)
    alternatives = await routing.fetch_alternatives(rider.lat, rider.lng, rider.nav_target_lat, rider.nav_target_lng)
    if start_state != (rider.lat, rider.lng, rider.nav_target_lat, rider.nav_target_lng) or world.rider_by_id.get(rider.id) is not rider:
        return {'switched': False, 'gain_seconds': 0, 'reason': 'Rider moved while routes were fetched; keeping live route'}
    if current_route and not current_route.get('approximate', False):
        alternatives = [r for r in alternatives if not r.get('approximate', False)]
    if not alternatives:
        return {'switched': False, 'gain_seconds': 0, 'reason': 'Road routing unavailable; keeping current route'}
    scored = [(estimate_zone_adjusted_duration(r["polyline"], rider.speed_kmh, zone), r) for r in alternatives]
    best_duration, best_route = min(scored, key=lambda x: x[0])

    gain = current_duration - best_duration
    threshold = max(REROUTE_GAIN_THRESHOLD_SECONDS, REROUTE_GAIN_THRESHOLD_PCT * current_duration)
    details = {'gain_seconds': round(gain, 1), 'old_eta_seconds': round(current_duration, 1),
               'new_eta_seconds': round(best_duration, 1), 'old_polyline': current_polyline,
               'candidate_polyline': best_route['polyline'], 'threshold_seconds': round(threshold, 1)}
    if gain >= threshold:
        new_key = routing._key(rider.lat, rider.lng, rider.nav_target_lat, rider.nav_target_lng)
        routing._store(new_key, best_route)
        rider.nav_origin_lat, rider.nav_origin_lng = rider.lat, rider.lng  # new leg starts from here, not the old origin
        rider.route_progress_km = 0.0
        world.mark_rider_dirty(rider.id)
        return {"switched": True, **details}
    return {"switched": False, **details, "reason": "kept current route — gain below threshold"}


@app.post("/disruptions/{kind}", dependencies=[Depends(require_ops)])
async def trigger_disruption(
    kind: str, target: str | None = None,
    lat: float | None = None, lng: float | None = None,
    radius_km: float = 2.5, multiplier: float = 0.35, duration_minutes: int = 6,
):
    if kind == "traffic":
        if lat is not None and lng is not None:
            zone_lat, zone_lng = lat, lng  # UI click-to-place
        elif len(world.stores) >= 2:
            import random
            a, b = random.sample(world.stores, 2)
            zone_lat, zone_lng = (a.lat + b.lat) / 2, (a.lng + b.lng) / 2
        elif world.stores:
            zone_lat, zone_lng = world.stores[0].lat, world.stores[0].lng
        else:
            zone_lat, zone_lng = 19.07, 72.87
        zone = add_traffic_zone(zone_lat, zone_lng, radius_km=radius_km, multiplier=multiplier, duration_minutes=duration_minutes)
        affected_riders = riders_affected_by_zone_sync(zone, world.riders, world.active_orders())
        decisions = {}
        for rid in affected_riders:
            rider = world.rider_by_id[rid]
            pending = sorted([o for o in world.active_orders() if o.rider_id == rid], key=lambda o: o.route_seq or 0)
            decision = rolling_reoptimize_sync(rider, pending)
            decisions[rid] = {"sequence": decision}
            if decision and decision["applied"]:
                for o in pending:
                    world.mark_order_dirty(o.id)
                if pending:
                    world.log_event(pending[0].id, "ROUTE_CHANGED", {
                        "rider_id": rid, "reason": f"traffic_zone: {decision['reason']}", "zone_id": zone["id"],
                        "gain_seconds": decision["gain_seconds"],
                    })

            # route-level reroute: is there a better road path around THIS zone for the rider's
            # immediate leg? Only switch if it clears the threshold; otherwise explicitly keep the
            # current path and say so — both outcomes are logged, not just the "switched" one.
            if rider.nav_target_lat is not None:
                route_decision = await evaluate_reroute(rider, zone)
                decisions[rid]["route"] = route_decision
                if pending:
                    world.log_event(pending[0].id, "ROUTE_CHANGED" if route_decision["switched"] else "ROUTE_KEPT", {
                        "rider_id": rid, "zone_id": zone["id"], **route_decision,
                    })
        return {
            "ok": True, "kind": kind, "zone": {k: v for k, v in zone.items() if k != "expires_at"},
            "affected_riders": affected_riders, "reroute_decisions": decisions,
        }
    elif kind == "clear_traffic":
        clear_traffic_zones()
    elif kind == "surge":
        simulator.state["order_spawn_rate"] = min(0.9, simulator.state["order_spawn_rate"] + 0.35)
    elif kind == "rider_offline" and target:
        rider = world.rider_by_id.get(target)
        if rider:
            rider.status = "OFFLINE"
            rider.nav_target_lat = rider.nav_target_lng = None
            world.mark_rider_dirty(target)
            freed = world.reassign_rider_orders(target)
            for oid in freed:
                world.log_event(oid, "RIDER_OFFLINE", {"rider_id": target})
    elif kind == "rider_online" and target:
        rider = world.rider_by_id.get(target)
        if rider and rider.status == "OFFLINE":
            rider.status = "AVAILABLE"
            world.mark_rider_dirty(target)
    elif kind == "stockout" and target:
        # Bounce pre-pickup orders back to the pool FIRST, releasing their reservations, so the next tick
        # reallocates them to a store that still has stock. (Doing it after zeroing stock left those
        # reservations behind forever.) Packed / on-the-road orders keep theirs: the goods already exist.
        for o in world.orders.values():
            if o.store_id == target and o.status in ("assigned", "packing"):
                world.release_stock(target, o.items)
                if o.rider_id:
                    rider = world.rider_by_id.get(o.rider_id)
                    if rider:
                        rider.current_load_kg = max(0.0, rider.current_load_kg - o.weight_kg)
                        world.mark_rider_dirty(rider.id)
                o.status, o.store_id, o.rider_id, o.route_seq, o.assigned_at, o.packed_at = "created", None, None, None, None, None
                world.mark_order_dirty(o.id)
                world.log_event(o.id, "STOCK_OUT_REALLOCATE", {"store_id": target})
        for (sid, _sku), row in world.inventory.items():
            if sid == target:
                row.qty = row.reserved_qty  # only what's already committed to packed/on-road orders remains
                world.mark_inventory_dirty((sid, row.sku))
    elif kind == "cancel" and target:
        order = world.orders.get(target)
        if order and world.cancel_order(order):
            world.log_event(order.id, "CANCELLED", {})
    else:
        return {"ok": False, "error": "unknown kind"}
    return {"ok": True, "kind": kind, "state": {"order_spawn_rate": simulator.state["order_spawn_rate"]}}


@app.post("/reset", dependencies=[Depends(require_ops)])
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
        simulator.state.update({"order_spawn_rate": 0.12, "blocked_store_ids": set(), "dispatch_mode": "optimized", "tick_speed_multiplier": 1})
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
