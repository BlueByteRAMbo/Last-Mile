import datetime as dt

import pytest

from app.analytics import build_analytics, gini, record_rider_time
from app.models import OrderEvent
from app.world import world
from .conftest import make_order, make_rider, make_store, utcnow


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    for key, value in {'orders': {}, 'riders': [], 'stores': [], 'events': [],
                       'dirty_rider_ids': set()}.items():
        monkeypatch.setattr(world, key, value)


def test_utilization_tracks_assignments_offline_time_and_shift_end():
    now = utcnow()
    busy, offline, ended = [make_rider(id=str(i)) for i in range(3)]
    offline.status = 'OFFLINE'
    ended.shift_end = (now - dt.timedelta(seconds=1)).replace(tzinfo=None)
    busy.shift_end = (now + dt.timedelta(seconds=1)).replace(tzinfo=None)
    world.riders = [busy, offline, ended]
    order = make_order()
    order.status, order.rider_id = 'packing', busy.id
    world.orders[order.id] = order
    record_rider_time(2, now)
    assert busy.busy_seconds == busy.observed_shift_seconds == 1
    assert offline.observed_shift_seconds == 2
    assert not offline.busy_seconds
    assert not ended.observed_shift_seconds
    assert build_analytics(now)['rider_utilization_pct'] == 33.3


def test_gini_empty_equal_and_unequal():
    assert gini([]) == gini([0, 0]) == gini([3, 3]) == 0
    assert gini([0, 4]) == 0.5


def test_delivery_buckets_use_delivery_time_and_preserve_empty_gaps():
    now = dt.datetime(2026, 10, 1, 12, 3, tzinfo=dt.timezone.utc)
    first, second = make_order(), make_order(id='ORD-2')
    for order in [first, second]:
        order.status = 'delivered'
        order.created_at = now - dt.timedelta(minutes=20)
        order.delivered_at = now - dt.timedelta(minutes=1)
        order.promised_at = now
        world.orders[order.id] = order
    second.promised_at = (now - dt.timedelta(minutes=2)).replace(tzinfo=None)
    result = build_analytics(now)
    assert result['on_time_rate_pct'] == 50
    assert result['avg_delivery_minutes'] == 19
    assert result['on_time_series'][-1]['on_time_rate_pct'] == 50
    assert result['on_time_series'][0]['on_time_rate_pct'] is None


def test_delay_signals_deduplicate_orders_and_ignore_plain_resequencing():
    now = utcnow()
    order = make_order()
    world.orders[order.id] = order
    world.events = [OrderEvent(order_id=order.id, type='DELAY_RISK', ts=now,
                   payload={'reason': 'no_feasible_store_or_rider'}) for _ in range(3)]
    world.events += [OrderEvent(order_id=order.id, type='ROUTE_CHANGED', ts=now, payload={'reason': 'shorter_sequence'}),
                     OrderEvent(order_id=order.id, type='ROUTE_KEPT', ts=now, payload={'zone_id': 'TRF-1'})]
    result = build_analytics(now)
    reasons = {r['reason']: r['count'] for r in result['delay_reasons']}
    assert reasons['Unallocated'] == 1
    assert reasons['Traffic'] == 1
    assert len(result['disruption_markers']) == 1
    assert result['on_time_series'][-1]['disruptions'] == 1


def test_zone_is_geographic_not_fulfillment_and_failure_counts_are_separate():
    near = make_store(id='NEAR', lat=19, lng=72)
    far = make_store(id='FAR', lat=20, lng=73)
    world.stores = [near, far]
    order = make_order(lat=19, lng=72)
    order.store_id, order.status = far.id, 'failed'
    other = make_order(id='CANCEL')
    other.status = 'cancelled'
    world.orders = {order.id: order, other.id: other}
    result = build_analytics()
    assert next(z for z in result['zone_density'] if z['store_id'] == near.id)['count'] == 2
    assert result['failure_count'] == result['cancelled_count'] == 1
    assert result['failed_count'] == 2
