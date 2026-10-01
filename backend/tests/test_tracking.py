import datetime as dt

import pytest

from app import routing
from app.tracking import rider_route, delivery_etas, order_tracking
from app.simulator import build_snapshot
from app.world import world
from .conftest import make_order, make_rider, make_store, utcnow


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    rider = make_rider(lat=19, lng=72.8)
    store = make_store(lat=19, lng=72.8)
    monkeypatch.setattr(world, "riders", [rider])
    monkeypatch.setattr(world, "rider_by_id", {rider.id: rider})
    monkeypatch.setattr(world, "stores", [store])
    monkeypatch.setattr(world, "store_by_id", {store.id: store})
    monkeypatch.setattr(world, "orders", {})
    routing.clear_cache()
    yield
    routing.clear_cache()


def test_route_version_stable_during_movement_changes_with_geometry():
    rider = world.riders[0]
    rider.nav_origin_lat, rider.nav_origin_lng = 19, 72.8
    rider.nav_target_lat, rider.nav_target_lng = 19, 72.82
    before = rider_route(rider)
    rider.route_progress_km = 0.5
    after = rider_route(rider)
    assert before["route_version"] == after["route_version"]
    assert after["polyline_remaining"][0][0] > 72.8
    assert after["heading"] == pytest.approx(90, abs=0.01)
    routing._store(routing._key(19, 72.8, 19, 72.82), {
        "polyline": [[72.8, 19], [72.81, 19.01], [72.82, 19]], "approximate": False})
    road = rider_route(rider)
    assert road["route_version"] != before["route_version"]
    assert road["approximate_route"] is False


def test_eta_includes_packing_and_earlier_deliveries():
    now = utcnow()
    first = make_order(lat=19, lng=72.81)
    second = make_order(id="ORD-2", lat=19, lng=72.82)
    for i, order in enumerate([first, second]):
        order.rider_id = world.riders[0].id
        order.store_id = world.stores[0].id
        order.status = "packing"
        order.assigned_at = now.replace(tzinfo=None)
        order.route_seq = i
    etas = delivery_etas([second, first], now)
    assert etas[first.id] > 60
    assert etas[second.id] > etas[first.id]
    first.promised_at = (now + dt.timedelta(seconds=10)).replace(tzinfo=None)
    assert order_tracking(first, etas, now)["predicted_late"] is True


def test_snapshot_unknown_eta_and_idle_route():
    order = make_order()
    order.customer_name = "Test Customer"
    world.orders[order.id] = order
    snapshot = build_snapshot()
    assert snapshot["orders"][0]["eta_seconds"] is None
    assert snapshot["orders"][0]["customer_name"] == "Test Customer"
    assert snapshot["orders"][0]["predicted_late"] is False
    assert snapshot["riders"][0]["polyline_remaining"] == []
    assert snapshot["riders"][0]["assigned_order_ids"] == []


def test_delivered_eta_zero_and_actual_lateness():
    order = make_order()
    order.status = "delivered"
    order.delivered_at = order.promised_at + dt.timedelta(seconds=1)
    result = order_tracking(order, {}, utcnow())
    assert result["eta_seconds"] == 0
    assert result["predicted_late"] is True


def test_offline_rider_has_unknown_eta():
    order = make_order()
    order.status = "packed"
    order.rider_id = world.riders[0].id
    world.riders[0].status = "OFFLINE"
    assert delivery_etas([order]) == {}


@pytest.mark.asyncio
async def test_customer_endpoint_with_assigned_rider():
    from app.main import track_order
    order = make_order()
    order.status = "packed"
    order.rider_id = world.riders[0].id
    order.store_id = world.stores[0].id
    world.orders[order.id] = order
    response = await track_order(order.id)
    assert response["eta_seconds"] > 0
    assert response["polyline_remaining"] == []
    assert "assignment_reason" not in response
