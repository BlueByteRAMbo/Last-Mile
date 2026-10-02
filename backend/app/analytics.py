"""Analytics over live world state, including events not yet flushed to the DB."""
import datetime as dt
from collections import Counter

from .dispatch import haversine_km
from .tracking import aware
from .world import world, ACTIVE_STATUSES


def record_rider_time(seconds, now=None):
    """Sample simulated shift time; busy means holding an active assignment.

    Offline time within a shift is idle time. Server downtime is not observed and
    is not backfilled. Both counters survive restart through normal persistence.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    busy_ids = {o.rider_id for o in world.orders.values() if o.status in ACTIVE_STATUSES}
    for rider in world.riders:
        elapsed = max(0, seconds)
        if rider.shift_end:
            elapsed = min(elapsed, max(0, (aware(rider.shift_end) - now).total_seconds()))
        if not elapsed:
            continue
        rider.observed_shift_seconds = (rider.observed_shift_seconds or 0) + elapsed
        if rider.status != 'OFFLINE' and rider.id in busy_ids:
            rider.busy_seconds = (rider.busy_seconds or 0) + elapsed
        world.mark_rider_dirty(rider.id)


def gini(values):
    ordered = sorted(values)
    total = sum(ordered)
    if not total:
        return 0.0
    n = len(ordered)
    return round(sum((2 * i - n - 1) * value for i, value in enumerate(ordered, 1)) / (n * total), 4)


def build_analytics(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    orders = list(world.orders.values())
    delivered = [o for o in orders if o.status == 'delivered' and o.delivered_at]
    failed = sum(o.status == 'failed' for o in orders)
    cancelled = sum(o.status == 'cancelled' for o in orders)
    active = world.active_orders()
    on_time = sum(aware(o.delivered_at) <= aware(o.promised_at) for o in delivered)
    loads = Counter(o.rider_id for o in delivered)
    rider_stats = [{
        'id': r.id, 'name': r.name, 'delivered_count': loads[r.id],
        'busy_seconds': r.busy_seconds or 0,
        'observed_shift_seconds': r.observed_shift_seconds or 0,
        'utilization_pct': round(100 * (r.busy_seconds or 0) / r.observed_shift_seconds, 1)
            if r.observed_shift_seconds else 0.0,
    } for r in world.riders]
    observed = sum(r['observed_shift_seconds'] for r in rider_stats)
    busy = sum(r['busy_seconds'] for r in rider_stats)

    # Named catchments use the nearest hub, independent of fulfillment assignment.
    zones = {s.id: {'zone': s.name, 'store_id': s.id, 'lat': s.lat, 'lng': s.lng,
                    'count': 0, 'active_count': 0} for s in world.stores}
    for order in orders:
        if not world.stores:
            break
        nearest = min(world.stores, key=lambda s: haversine_km(order.customer_lat, order.customer_lng, s.lat, s.lng))
        zones[nearest.id]['count'] += 1
        zones[nearest.id]['active_count'] += order.status in ('created', *ACTIVE_STATUSES)

    reasons = {label: set() for label in ('Stock-out', 'Rider offline', 'Traffic', 'Packing wait', 'Unallocated', 'Deadline risk')}
    disruption_types = {'STOCK_OUT_REALLOCATE', 'RIDER_OFFLINE', 'ROUTE_CHANGED', 'ROUTE_KEPT'}
    # Fixed UTC five-minute intervals covering the current hour (including current bucket).
    end = now.replace(minute=now.minute // 5 * 5, second=0, microsecond=0)
    start = end - dt.timedelta(minutes=55)
    buckets = [{'ts': (start + dt.timedelta(minutes=5 * i)).isoformat(),
                'delivered': 0, 'on_time': 0, 'on_time_rate_pct': None,
                'disruptions': 0} for i in range(12)]

    def bucket_for(ts):
        index = int((aware(ts) - start).total_seconds() // 300)
        return buckets[index] if 0 <= index < len(buckets) else None

    for order in delivered:
        bucket = bucket_for(order.delivered_at)
        if bucket is not None:
            bucket['delivered'] += 1
            bucket['on_time'] += aware(order.delivered_at) <= aware(order.promised_at)
    markers = []
    for event in world.events:
        if event.order_id not in world.orders:
            continue
        payload = event.payload or {}
        reason = str(payload.get('reason', ''))
        category = None
        if event.type == 'STOCK_OUT_REALLOCATE':
            category = 'Stock-out'
        elif event.type == 'RIDER_OFFLINE':
            category = 'Rider offline'
        elif event.type in ('ROUTE_CHANGED', 'ROUTE_KEPT') and ('zone_id' in payload or 'traffic' in reason):
            category = 'Traffic'
        elif event.type == 'DELAY_RISK':
            category = 'Unallocated' if reason == 'no_feasible_store_or_rider' else 'Deadline risk'
        if category:
            reasons[category].add(event.order_id)
        # Route resequencing alone is not a disruption.
        if event.type in disruption_types and category in ('Stock-out', 'Rider offline', 'Traffic') and event.ts:
            bucket = bucket_for(event.ts)
            if bucket is not None:
                bucket['disruptions'] += 1
                markers.append({'ts': aware(event.ts).isoformat(), 'order_id': event.order_id, 'reason': category})
    for order in active:
        if order.status in ('assigned', 'packing') and order.risk in ('AT_RISK', 'DELAYED', 'SEVERE'):
            reasons['Packing wait'].add(order.id)
    for bucket in buckets:
        if bucket['delivered']:
            bucket['on_time_rate_pct'] = round(100 * bucket['on_time'] / bucket['delivered'], 1)
    # Operator cancellations are not delivery failures, so they neither count as SLA breaches nor dilute the rate.
    terminal = len(delivered) + failed
    return {
        'avg_delivery_minutes': round(sum((aware(o.delivered_at) - aware(o.created_at)).total_seconds() / 60
                                          for o in delivered) / len(delivered), 1) if delivered else None,  # None = no data yet, not 0 / 100
        'on_time_rate_pct': round(100 * on_time / len(delivered), 1) if delivered else None,
        'rider_utilization_pct': round(100 * busy / observed, 1) if observed else 0.0,
        'utilization_basis': 'Busy assignment time / observed simulated shift time; excludes server downtime',
        'sla_breach_rate_pct': round(100 * (len(delivered) - on_time + failed) / terminal, 1) if terminal else None,
        'failed_count': failed + cancelled,  # compatibility with existing KPI consumers
        'failure_count': failed, 'cancelled_count': cancelled,
        'delayed_count': sum(aware(o.promised_at) < now for o in active),
        'delivered_count': len(delivered), 'active_orders': len(active),
        'zone_density': sorted(zones.values(), key=lambda z: (-z['count'], z['zone'])),
        'rider_stats': rider_stats,
        'workload_gini': gini([r['delivered_count'] for r in rider_stats]),
        'delay_reasons': [{'reason': reason, 'count': len(ids)} for reason, ids in reasons.items()],
        'on_time_series': buckets, 'disruption_markers': markers,
    }
