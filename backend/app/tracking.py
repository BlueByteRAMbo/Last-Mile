"""Read-only live tracking projections. No database or network calls."""
import datetime as dt
import hashlib
import json
import math

from . import routing
from .dispatch import travel_seconds
from .world import world, ACTIVE_STATUSES


def aware(value):
    return value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None else value


def rider_route(rider):
    coords = (rider.nav_origin_lat, rider.nav_origin_lng,
              rider.nav_target_lat, rider.nav_target_lng)
    empty = {"polyline_remaining": [], "route_version": None,
             "heading": None, "approximate_route": True}
    if rider.status == "OFFLINE" or any(c is None for c in coords):
        return empty
    cached = routing.get_cached_route(*coords)
    points = cached["polyline"] if cached else [[coords[1], coords[0]], [coords[3], coords[2]]]
    version = hashlib.sha256(json.dumps(points, separators=(",", ":")).encode()).hexdigest()[:16]
    progress = max(0, rider.route_progress_km or 0)
    remaining = [points[-1]]
    for i, (a, b) in enumerate(zip(points, points[1:])):
        length = routing.polyline_total_km([a, b])
        if length > 0 and progress < length:
            lat, lng = routing.polyline_progress_point([a, b], progress)
            remaining = [[lng, lat]] + points[i + 1:]
            break
        progress -= length
    heading = None
    for a, b in zip(remaining, remaining[1:]):
        if a == b:
            continue
        p1, p2 = math.radians(a[1]), math.radians(b[1])
        dl = math.radians(b[0] - a[0])
        heading = (math.degrees(math.atan2(math.sin(dl) * math.cos(p2),
                   math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl))) + 360) % 360
        break
    return {"polyline_remaining": remaining, "route_version": version,
            "heading": heading, "approximate_route": not cached or cached.get("approximate", False)}


def delivery_etas(orders, now=None):
    """Project pickup-before-drop routes, including packing and earlier deliveries.

    Estimates use cached road geometry and the simulator's rider speed/traffic model.
    Unallocated orders have an unknown ETA rather than a misleading zero.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    result = {}
    grouped = {}
    for order in orders:
        if order.status in ACTIVE_STATUSES and order.rider_id:
            grouped.setdefault(order.rider_id, []).append(order)
    for rider_id, assigned in grouped.items():
        rider = world.rider_by_id.get(rider_id)
        if rider is None or rider.status == "OFFLINE":
            continue
        pending = sorted(assigned, key=lambda o: (o.route_seq or 0, o.id))
        lat, lng, elapsed = rider.lat, rider.lng, 0.0
        first_leg = True

        def travel(dest_lat, dest_lng):
            nonlocal lat, lng, elapsed, first_leg
            points = None
            if first_leg and (rider.nav_target_lat, rider.nav_target_lng) == (dest_lat, dest_lng):
                points = rider_route(rider)["polyline_remaining"]
            if not points:
                cached = routing.get_cached_route(lat, lng, dest_lat, dest_lng)
                points = cached["polyline"] if cached else [[lng, lat], [dest_lng, dest_lat]]
            elapsed += sum(travel_seconds(a[1], a[0], b[1], b[0], rider.speed_kmh)
                           for a, b in zip(points, points[1:]))
            lat, lng, first_leg = dest_lat, dest_lng, False

        for order in pending:
            if order.status == "out_for_delivery":
                continue
            store = world.store_by_id.get(order.store_id)
            if store is None:
                continue
            if order.status in ("assigned", "packing"):
                age = max(0, (now - aware(order.assigned_at)).total_seconds()) if order.assigned_at else 0
                elapsed = max(elapsed, max(0, store.packing_seconds_per_order - age))
            travel(store.lat, store.lng)
        for order in pending:
            travel(order.customer_lat, order.customer_lng)
            result[order.id] = round(elapsed, 1)
    return result


def order_tracking(order, etas, now):
    eta = 0 if order.status == "delivered" else etas.get(order.id)
    deadline = aware(order.promised_at)
    if order.status == "delivered":
        late = bool(order.delivered_at and aware(order.delivered_at) > deadline)
    elif order.status in ("failed", "cancelled"):
        late = False
    else:
        late = now + dt.timedelta(seconds=eta or 0) > deadline
    slack = (deadline - now).total_seconds() - (eta or 0)
    urgency = max(0, 10 - slack / 60)
    delay_age = max(0, (now - deadline).total_seconds() / 60)
    return {"eta_seconds": eta, "predicted_late": late,
            "priority_score": round(urgency + (5 if order.priority else 0) + delay_age, 2)}
