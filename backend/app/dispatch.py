"""Explainable allocation engine + cheapest-insertion routing.

Score = w_eta*ETA + w_pack*packing_wait + w_load*workload - w_batch*batching_benefit
        + w_deadline*deadline_risk + w_stability*reassignment_penalty
Lower score wins. Every decision returns ranked candidates + reasons for the UI inspector.
"""
import math
import uuid
import datetime as dt
from sqlalchemy import select
from .models import DarkStore, InventoryItem, Rider, Order

W_ETA = 1.0
W_PACK = 0.6
W_LOAD = 8.0
W_DEADLINE = 15.0
W_BATCH = 6.0
W_STABILITY = 4.0
W_PRIORITY = 5.0
LOW_BATTERY_PCT = 15.0

try:
    from ortools.constraint_solver import routing_enums_pb2, pywrapcp
    HAS_ORTOOLS = True
except ImportError:
    HAS_ORTOOLS = False


def haversine_km(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# Live traffic congestion zones: [{id, lat, lng, radius_km, multiplier, expires_at}]. A leg whose straight-line
# path passes within radius_km of a zone's center travels at speed_kmh * multiplier for its whole length.
# ponytail: whole-leg slowdown, not partial-distance-in-zone; good enough at Mumbai-hub scale, split the leg
# at the zone boundary if a later demo needs partial-leg accuracy.
TRAFFIC_ZONES: list[dict] = []


def _segment_intersects_zone(lat1, lng1, lat2, lng2, zone) -> bool:
    """Closest-distance-from-circle-center-to-segment test, in a local equirectangular km projection."""
    km_per_deg_lat = 111.0
    km_per_deg_lng = 111.0 * math.cos(math.radians(zone["lat"]))
    ax, ay = lng1 * km_per_deg_lng, lat1 * km_per_deg_lat
    bx, by = lng2 * km_per_deg_lng, lat2 * km_per_deg_lat
    cx, cy = zone["lng"] * km_per_deg_lng, zone["lat"] * km_per_deg_lat

    dx, dy = bx - ax, by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq == 0:
        t = 0.0
    else:
        t = max(0.0, min(1.0, ((cx - ax) * dx + (cy - ay) * dy) / seg_len_sq))
    closest_x, closest_y = ax + t * dx, ay + t * dy
    dist = math.hypot(cx - closest_x, cy - closest_y)
    return dist <= zone["radius_km"]


def active_traffic_zones():
    now = dt.datetime.now(dt.timezone.utc)
    return [z for z in TRAFFIC_ZONES if z["expires_at"] > now]


def traffic_multiplier_for_leg(lat1, lng1, lat2, lng2) -> float:
    mult = 1.0
    for zone in active_traffic_zones():
        if _segment_intersects_zone(lat1, lng1, lat2, lng2, zone):
            mult = min(mult, zone["multiplier"])
    return mult


def travel_seconds(lat1, lng1, lat2, lng2, speed_kmh):
    km = haversine_km(lat1, lng1, lat2, lng2)
    effective_speed = max(speed_kmh, 1) * traffic_multiplier_for_leg(lat1, lng1, lat2, lng2)
    return (km / max(effective_speed, 1)) * 3600


async def store_has_stock(session, store: DarkStore, items: list) -> bool:
    for it in items:
        row = (await session.execute(
            select(InventoryItem).where(InventoryItem.store_id == store.id, InventoryItem.sku == it["sku"])
        )).scalar_one_or_none()
        if row is None or (row.qty - row.reserved_qty) < it["qty"]:
            return False
    return True


def check_stock(inventory_map: dict, store_id: str, items: list) -> bool:
    """Pure in-memory version of store_has_stock, against a pre-fetched {(store_id, sku): InventoryItem} map."""
    for it in items:
        row = inventory_map.get((store_id, it["sku"]))
        if row is None or (row.qty - row.reserved_qty) < it["qty"]:
            return False
    return True


async def fetch_inventory_map(session, store_ids: list[str] | None = None) -> dict:
    """One round trip instead of one query per (store, sku) pair."""
    q = select(InventoryItem)
    if store_ids:
        q = q.where(InventoryItem.store_id.in_(store_ids))
    rows = (await session.execute(q)).scalars().all()
    return {(r.store_id, r.sku): r for r in rows}


async def fetch_scoring_context(session):
    """Everything score_candidates needs, in three round trips total instead of ~2 per rider/store.
    Callers should pass the SAME context to every order scored in one tick, and patch it in-memory
    (reserve_stock_in_map / active_by_rider bookkeeping) as orders get assigned so later orders in the
    same batch see the effect of earlier ones without re-querying."""
    stores = (await session.execute(select(DarkStore))).scalars().all()
    riders = (await session.execute(select(Rider))).scalars().all()
    active_orders = (await session.execute(
        select(Order).where(Order.rider_id.isnot(None), Order.status.in_(["assigned", "packing", "packed", "out_for_delivery"]))
    )).scalars().all()
    active_by_rider: dict[str, list[Order]] = {}
    for o in active_orders:
        active_by_rider.setdefault(o.rider_id, []).append(o)
    inventory_map = await fetch_inventory_map(session, [s.id for s in stores])
    return {"stores": stores, "riders": riders, "active_by_rider": active_by_rider, "inventory_map": inventory_map}


async def reserve_stock(session, store_id: str, items: list):
    for it in items:
        row = (await session.execute(
            select(InventoryItem).where(InventoryItem.store_id == store_id, InventoryItem.sku == it["sku"])
        )).scalar_one()
        row.reserved_qty += it["qty"]


async def release_stock(session, store_id: str, items: list):
    for it in items:
        row = (await session.execute(
            select(InventoryItem).where(InventoryItem.store_id == store_id, InventoryItem.sku == it["sku"])
        )).scalar_one_or_none()
        if row:
            row.reserved_qty = max(0, row.reserved_qty - it["qty"])


def score_candidates_sync(order: Order, stores, riders, active_by_rider: dict, inventory_map: dict) -> list[dict]:
    """Pure in-memory scoring against a pre-fetched context — no DB round trips. This is what actually
    runs inside the tick loop; score_candidates() below just fetches a fresh context and calls this,
    for one-off callers (the explain endpoint, tests) where the batching wouldn't help anyway."""
    now = dt.datetime.now(dt.timezone.utc)
    deadline_s = (order.promised_at - now).total_seconds()
    candidates = []

    for store in stores:
        if not check_stock(inventory_map, store.id, order.items):
            continue
        packing_wait = 0
        for rider in riders:
            if rider.status == "OFFLINE":
                continue
            if rider.current_load_kg + order.weight_kg > rider.capacity_kg:
                continue
            if rider.battery_pct < LOW_BATTERY_PCT:
                continue

            pickup_eta = travel_seconds(rider.lat, rider.lng, store.lat, store.lng, rider.speed_kmh)
            drop_eta = travel_seconds(store.lat, store.lng, order.customer_lat, order.customer_lng, rider.speed_kmh)
            total_eta = pickup_eta + packing_wait + drop_eta

            shift_end = rider.shift_end
            if shift_end and shift_end.tzinfo is None:  # sqlite round-trips drop tzinfo; Postgres doesn't
                shift_end = shift_end.replace(tzinfo=dt.timezone.utc)
            if shift_end and now + dt.timedelta(seconds=total_eta) > shift_end:
                continue  # wouldn't be back within shift even before packing/traffic delays

            deadline_risk = max(0.0, (total_eta - deadline_s) / 60.0)  # minutes over promise
            rider_active = active_by_rider.get(rider.id, [])
            same_store = sum(1 for o in rider_active if o.store_id == store.id)
            elsewhere = len(rider_active) - same_store
            workload_penalty = elsewhere  # genuine detour cost: busy on a different pickup
            batching_benefit = min(same_store, 1)  # already headed to this store -> shared trip
            # stability: penalize moving an order off the rider it's already committed to
            reassignment_penalty = 1.0 if (order.rider_id and order.rider_id != rider.id) else 0.0
            priority_bonus = 1.0 if order.priority else 0.0

            cost = (
                W_ETA * (total_eta / 60.0)
                + W_PACK * (packing_wait / 60.0)
                + W_LOAD * workload_penalty
                + W_DEADLINE * deadline_risk
                - W_BATCH * batching_benefit
                + W_STABILITY * reassignment_penalty
                - W_PRIORITY * priority_bonus
            )
            feasible = total_eta <= deadline_s + 600  # 10 min slack beyond promise still feasible to try

            candidates.append({
                "store_id": store.id,
                "store_name": store.name,
                "rider_id": rider.id,
                "rider_name": rider.name,
                "cost": round(cost, 2),
                "feasible": feasible,
                "reason": {
                    "eta_seconds": round(total_eta, 1),
                    "pickup_eta_seconds": round(pickup_eta, 1),
                    "drop_eta_seconds": round(drop_eta, 1),
                    "packing_wait_seconds": packing_wait,
                    "workload_penalty": workload_penalty,
                    "deadline_slack_seconds": round(deadline_s - total_eta, 1),
                    "deadline_risk_minutes": round(deadline_risk, 1),
                    "batching_benefit": batching_benefit,
                    "priority_bonus": priority_bonus,
                    "reassignment_penalty": reassignment_penalty,
                },
            })

    candidates.sort(key=lambda c: (not c["feasible"], c["cost"]))
    return candidates


async def score_candidates(session, order: Order) -> list[dict]:
    """One-off convenience wrapper: fetches its own context and scores a single order.
    Used by the /explain endpoint and tests; the tick loop uses score_candidates_sync directly
    against a context batch-fetched once per tick instead of once per order."""
    ctx = await fetch_scoring_context(session)
    return score_candidates_sync(order, ctx["stores"], ctx["riders"], ctx["active_by_rider"], ctx["inventory_map"])


async def allocate(session, order: Order) -> dict | None:
    """Pick the best feasible candidate. Returns the decision payload (also stored on the order) or None."""
    candidates = await score_candidates(session, order)
    feasible = [c for c in candidates if c["feasible"]]
    if not feasible:
        return None
    chosen = feasible[0]
    alternatives = feasible[1:5]
    return {"chosen": chosen, "alternatives": alternatives, "all_count": len(candidates)}


def allocate_sync(order: Order, stores, riders, active_by_rider, inventory_map) -> dict | None:
    candidates = score_candidates_sync(order, stores, riders, active_by_rider, inventory_map)
    feasible = [c for c in candidates if c["feasible"]]
    if not feasible:
        return None
    return {"chosen": feasible[0], "alternatives": feasible[1:5], "all_count": len(candidates)}


def cheapest_insertion_cost(rider: Rider, existing_orders: list[Order], new_order: Order, store: DarkStore):
    """Where in the rider's current stop sequence should the new pickup+drop slot in, at minimum added travel time.
    Returns (best_index, added_seconds, feasible)."""
    stops = [(rider.lat, rider.lng)]
    for o in sorted(existing_orders, key=lambda x: x.route_seq or 0):
        stops.append((o.customer_lat, o.customer_lng))

    best_idx, best_added = len(stops) - 1, None
    for i in range(1, len(stops) + 1):
        pre = stops[i - 1]
        post = stops[i] if i < len(stops) else None
        added = travel_seconds(pre[0], pre[1], new_order.customer_lat, new_order.customer_lng, rider.speed_kmh)
        if post:
            added += travel_seconds(new_order.customer_lat, new_order.customer_lng, post[0], post[1], rider.speed_kmh)
            added -= travel_seconds(pre[0], pre[1], post[0], post[1], rider.speed_kmh)
        if best_added is None or added < best_added:
            best_added, best_idx = added, i
    return best_idx, best_added, True


async def reassign_rider_orders(session, rider_id: str):
    """Free every order still sitting with a rider that just went offline so the next tick
    can re-run allocate() for them against a different rider/store.
    ponytail: orders already out_for_delivery keep their rider (the package is physically with
    them) and are just left to ride out their risk state; only pre-pickup orders get reset.
    """
    stuck = (await session.execute(
        select(Order).where(Order.rider_id == rider_id, Order.status.in_(["assigned", "packing", "packed"]))
    )).scalars().all()
    rider = (await session.execute(select(Rider).where(Rider.id == rider_id))).scalar_one_or_none()
    freed = []
    for o in stuck:
        if o.store_id:
            await release_stock(session, o.store_id, o.items)
        if rider:
            rider.current_load_kg = max(0.0, rider.current_load_kg - o.weight_kg)
        o.status = "created"
        o.store_id = None
        o.rider_id = None
        o.route_seq = None
        o.assigned_at = None
        o.packed_at = None
        freed.append(o.id)
    return freed


async def cancel_order(session, order: Order):
    if order.status in ("delivered", "failed", "cancelled"):
        return False
    if order.store_id:
        await release_stock(session, order.store_id, order.items)
    if order.rider_id:
        rider = (await session.execute(select(Rider).where(Rider.id == order.rider_id))).scalar_one_or_none()
        if rider:
            rider.current_load_kg = max(0.0, rider.current_load_kg - order.weight_kg)
    order.status = "cancelled"
    return True


def add_traffic_zone(lat: float, lng: float, radius_km: float = 2.5, multiplier: float = 0.4, duration_minutes: int = 6) -> dict:
    zone = {
        "id": f"TRF-{uuid.uuid4().hex[:6]}", "lat": lat, "lng": lng,
        "radius_km": radius_km, "multiplier": multiplier,
        "expires_at": dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=duration_minutes),
    }
    TRAFFIC_ZONES.append(zone)
    return zone


def clear_traffic_zones():
    TRAFFIC_ZONES.clear()


async def riders_on_active_route(session, rider_ids: list[str] | None = None) -> dict[str, list[Order]]:
    """Every rider's currently ordered pending stops, for checking which routes a new zone touches."""
    q = select(Order).where(Order.status.in_(["assigned", "packing", "packed", "out_for_delivery"]))
    if rider_ids:
        q = q.where(Order.rider_id.in_(rider_ids))
    orders = (await session.execute(q)).scalars().all()
    by_rider: dict[str, list[Order]] = {}
    for o in orders:
        if o.rider_id:
            by_rider.setdefault(o.rider_id, []).append(o)
    return by_rider


async def riders_affected_by_zone(session, zone: dict) -> list[str]:
    """Which riders have an active route leg (rider->stop or stop->stop) passing through this zone."""
    riders = (await session.execute(select(Rider))).scalars().all()
    by_rider = await riders_on_active_route(session)
    affected = []
    for rider in riders:
        stops = by_rider.get(rider.id)
        if not stops:
            continue
        points = [(rider.lat, rider.lng)] + [(o.customer_lat, o.customer_lng) for o in sorted(stops, key=lambda x: x.route_seq or 0)]
        for (lat1, lng1), (lat2, lng2) in zip(points, points[1:]):
            if _segment_intersects_zone(lat1, lng1, lat2, lng2, zone):
                affected.append(rider.id)
                break
    return affected


def riders_affected_by_zone_sync(zone: dict, riders: list[Rider], active_orders: list[Order]) -> list[str]:
    """Pure in-memory version for the world-state tick loop — no DB access."""
    by_rider: dict[str, list[Order]] = {}
    for o in active_orders:
        if o.rider_id:
            by_rider.setdefault(o.rider_id, []).append(o)
    affected = []
    for rider in riders:
        stops = by_rider.get(rider.id)
        if not stops:
            continue
        points = [(rider.lat, rider.lng)] + [(o.customer_lat, o.customer_lng) for o in sorted(stops, key=lambda x: x.route_seq or 0)]
        for (lat1, lng1), (lat2, lng2) in zip(points, points[1:]):
            if _segment_intersects_zone(lat1, lng1, lat2, lng2, zone):
                affected.append(rider.id)
                break
    return affected


def rolling_reoptimize_sync(rider: Rider, pending: list[Order]):
    """OR-Tools rolling-horizon resequencing for one rider's pending stops, given already-fetched data
    (pure CPU, no DB access — call once per rider per tick against a batch-fetched order list, not
    with a fresh query per rider). No-op when ortools isn't installed or there are too few stops to matter.
    ponytail: single-rider horizon only; multi-rider joint VRP would need a shared solve, add if demo needs cross-rider swaps.
    """
    if not HAS_ORTOOLS or len(pending) < 2:
        return

    points = [(rider.lat, rider.lng)] + [(o.customer_lat, o.customer_lng) for o in pending]
    n = len(points)

    def dist(i, j):
        return int(travel_seconds(points[i][0], points[i][1], points[j][0], points[j][1], rider.speed_kmh))

    manager = pywrapcp.RoutingIndexManager(n, 1, 0)
    routing = pywrapcp.RoutingModel(manager)
    transit_idx = routing.RegisterTransitCallback(lambda i, j: dist(manager.IndexToNode(i), manager.IndexToNode(j)))
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)
    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search.time_limit.FromSeconds(2)
    solution = routing.SolveWithParameters(search)
    if not solution:
        return

    order_seq = []
    idx = routing.Start(0)
    while not routing.IsEnd(idx):
        node = manager.IndexToNode(idx)
        if node != 0:
            order_seq.append(pending[node - 1])
        idx = solution.Value(routing.NextVar(idx))
    for seq, o in enumerate(order_seq):
        o.route_seq = seq


async def rolling_reoptimize(session, rider_id: str):
    """One-off convenience wrapper (two queries) for callers outside the tick loop, e.g. reacting
    immediately to a single disruption. The tick loop itself uses rolling_reoptimize_sync against a
    batch-fetched rider/order list instead of paying two queries per rider per tick."""
    pending = (await session.execute(
        select(Order).where(Order.rider_id == rider_id, Order.status.in_(["assigned", "packing", "packed", "out_for_delivery"]))
    )).scalars().all()
    rider = (await session.execute(select(Rider).where(Rider.id == rider_id))).scalar_one_or_none()
    if rider:
        rolling_reoptimize_sync(rider, pending)
