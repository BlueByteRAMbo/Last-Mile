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
             "heading": None, "approximate_route": True, "polyline": [], "distance_remaining_km": 0}
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
            "polyline": points, "distance_remaining_km": round(routing.polyline_total_km(remaining), 3),
            "heading": heading, "approximate_route": not cached or cached.get("approximate", False)}


def stock_check(order):
    requested = {}
    for item in order.items:
        requested[item['sku']] = requested.get(item['sku'], 0) + item['qty']
    result = []
    for store in world.stores:
        available = {sku: max(0, world.inventory[(store.id, sku)].qty - world.inventory[(store.id, sku)].reserved_qty)
                     if (store.id, sku) in world.inventory else 0 for sku in requested}
        cached = routing.get_cached_route(store.lat, store.lng, order.customer_lat, order.customer_lng)
        result.append({'store_id': store.id, 'store_name': store.name, 'lat': store.lat, 'lng': store.lng,
            'has_all_items': all(available[sku] >= qty for sku, qty in requested.items()),
            'available': available, 'requested': requested,
            'missing': [sku for sku, qty in requested.items() if available[sku] < qty],
            'distance_km': round((cached['distance_m'] / 1000) if cached else routing._haversine_km(store.lat, store.lng, order.customer_lat, order.customer_lng), 2),
            'eta_seconds': round(cached['duration_s'] if cached else travel_seconds(store.lat, store.lng, order.customer_lat, order.customer_lng, 28)),
            'approximate_route': not cached or cached.get('approximate', False)})
    return sorted(result, key=lambda s: (not s['has_all_items'], s['eta_seconds'], s['store_id']))


def customer_snapshot(order):
    now = dt.datetime.now(dt.timezone.utc)
    rider = world.rider_by_id.get(order.rider_id)
    store = world.store_by_id.get(order.store_id)
    terminal = order.status in ('delivered', 'failed', 'cancelled')
    route = rider_route(rider) if rider and not terminal else {
        'polyline_remaining': [], 'polyline': [], 'route_version': None, 'heading': None,
        'distance_remaining_km': 0, 'approximate_route': True}
    events = [e for e in world.events if e.order_id == order.id]
    event_types = [('created', 'Order placed', 'ORDER_CREATED', order.created_at),
                   ('store', 'Store allocated', 'ASSIGNED', order.assigned_at),
                   ('rider', 'Rider allocated', 'ASSIGNED', order.assigned_at),
                   ('packing', 'Packing', 'PACKING_STARTED', None),
                   ('packed', 'Packed', 'PACKED', order.packed_at),
                   ('picked_up', 'Picked up', 'PICKED_UP', order.picked_up_at),
                   ('out_for_delivery', 'On the way', 'PICKED_UP', order.picked_up_at),
                   ('delivered', 'Delivered', 'DELIVERED', order.delivered_at)]
    stages = []
    for key, label, event_type, fallback in event_types:
        timestamp = next((e.ts for e in reversed(events) if e.type == event_type), fallback)
        detail = store.name if key == 'store' and store else rider.name if key == 'rider' and rider else None
        stages.append({'key': key, 'label': label, 'done': timestamp is not None,
                       'ts': aware(timestamp).isoformat() if timestamp else None, 'detail': detail})
    route_events = []
    for event in events:
        if event.type not in ('ROUTE_CHANGED', 'ROUTE_KEPT', 'RIDER_OFFLINE', 'STOCK_OUT_REALLOCATE'):
            continue
        payload = event.payload or {}
        route_events.append({'type': event.type, 'ts': aware(event.ts).isoformat() if event.ts else None,
            'message': 'Your rider is taking a faster route.' if event.type == 'ROUTE_CHANGED' else
                       'Traffic ahead; your rider is keeping the current route.' if event.type == 'ROUTE_KEPT' else
                       'We are arranging a new rider.' if event.type == 'RIDER_OFFLINE' else 'We are finding another store for your items.',
            'new_eta_seconds': payload.get('new_eta_seconds')})
    prediction = order_tracking(order, delivery_etas(world.active_orders(), now), now)
    prediction.pop('priority_score', None)
    return {'type': 'tracking', 'order_id': order.id, 'status': order.status,
        'status_label': order.status.replace('_', ' ').title(), 'stages': stages,
        'customer_name': order.customer_name, 'address_label': order.address_label,
        'risk': order.risk, 'priority': order.priority, 'items': order.items,
        'promised_at': aware(order.promised_at).isoformat(), 'created_at': aware(order.created_at).isoformat(),
        'delivered_at': aware(order.delivered_at).isoformat() if order.delivered_at else None,
        'customer_location': {'lat': order.customer_lat, 'lng': order.customer_lng},
        'store_name': store.name if store else None,
        'store': {'id': store.id, 'name': store.name, 'lat': store.lat, 'lng': store.lng} if store else None,
        'rider_id': rider.id if rider else None, 'rider_name': rider.name if rider else None,
        'rider_vehicle': (rider.vehicle or 'Delivery bike') if rider else None,
        'rider_position': {'lat': rider.lat, 'lng': rider.lng} if rider else None,
        'route_events': route_events[-20:], **prediction, **route}


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
