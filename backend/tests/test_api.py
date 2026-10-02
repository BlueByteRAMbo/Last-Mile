import datetime as dt
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app import simulator as simulator_module
from app import world as world_module
from app.world import world
from app.db import Base
from app.models import Order

pytestmark = pytest.mark.asyncio


async def intervention_order(client):
    response = await client.post('/orders', json={
        'customer_lat': 19.10, 'customer_lng': 72.85,
        'items': [{'sku': 'SKU-MILK', 'name': 'Milk', 'qty': 1, 'weight_kg': 0.5}],
    })
    return world.orders[response.json()['id']]


async def test_priority_boost_is_idempotent_and_persisted(client):
    order = await intervention_order(client)
    await world_module.persist_once()
    for _ in range(2):
        response = await client.post(f'/orders/{order.id}/intervene/boost')
        assert response.status_code == 200
    assert sum(e.type == 'PRIORITY_BOOSTED' for e in world.pending_events) == 1
    await world_module.persist_once()
    async with client.session_factory() as session:
        saved = await session.get(Order, order.id)
        assert saved.priority is True


async def test_reassign_keeps_packing_and_stock_and_changes_only_one_order(client):
    order = await intervention_order(client)
    store = world.stores[0]
    first, second = world.riders[:2]
    for rider in world.riders:
        rider.status = 'OFFLINE'
    for rider in (first, second):
        rider.status = 'AVAILABLE'
        rider.lat, rider.lng = store.lat, store.lng
    order.customer_lat, order.customer_lng = store.lat, store.lng
    order.status, order.store_id, order.rider_id = 'packing', store.id, first.id
    order.assigned_at = dt.datetime.now(dt.timezone.utc)
    first.current_load_kg = order.weight_kg
    world.inventory[(store.id, 'SKU-MILK')].qty = 10
    world.reserve_stock(store.id, order.items)
    reserved = world.inventory[(store.id, 'SKU-MILK')].reserved_qty
    response = await client.post(f'/orders/{order.id}/intervene/reassign')
    assert response.status_code == 200, response.text
    assert order.rider_id == second.id
    assert order.status == 'packing' and order.store_id == store.id
    assert first.current_load_kg == 0
    assert second.current_load_kg == order.weight_kg
    assert world.inventory[(store.id, 'SKU-MILK')].reserved_qty == reserved
    assert any(e.type == 'REASSIGNED' for e in world.pending_events)


async def test_reassign_without_alternative_preserves_assignment(client):
    order = await intervention_order(client)
    order.status, order.store_id, order.rider_id = 'packed', world.stores[0].id, world.riders[0].id
    for rider in world.riders:
        rider.status = 'OFFLINE'
    before = (order.status, order.rider_id, order.store_id)
    response = await client.post(f'/orders/{order.id}/intervene/reassign')
    assert response.status_code == 409
    assert (order.status, order.rider_id, order.store_id) == before


async def test_intervention_errors_and_cancel(client):
    assert (await client.post('/orders/missing/intervene/boost')).status_code == 404
    order = await intervention_order(client)
    assert (await client.post(f'/orders/{order.id}/intervene/invalid')).status_code == 400
    order.status = 'out_for_delivery'
    assert (await client.post(f'/orders/{order.id}/intervene/reassign')).status_code == 409
    assert (await client.post(f'/orders/{order.id}/intervene/cancel')).status_code == 200
    assert order.status == 'cancelled'
    assert (await client.post(f'/orders/{order.id}/intervene/boost')).status_code == 409


async def test_queue_score_in_rest_and_snapshot_but_not_customer_response(client):
    order = await intervention_order(client)
    before = (await client.get('/orders')).json()[0]['priority_score']
    await client.post(f'/orders/{order.id}/intervene/boost')
    after = (await client.get('/orders')).json()[0]['priority_score']
    assert after >= before + 5
    assert 'priority_score' in simulator_module.build_snapshot()['orders'][0]
    assert 'priority_score' not in (await client.get(f'/track/{order.id}')).json()


async def test_analytics_includes_unflushed_events_and_survives_reload(client):
    from app.analytics import record_rider_time
    order = await intervention_order(client)
    rider = world.riders[0]
    order.status, order.rider_id = 'assigned', rider.id
    world.log_event(order.id, 'RIDER_OFFLINE', {'rider_id': rider.id})
    timestamp = world.events[-1].ts
    record_rider_time(2)
    before = (await client.get('/analytics')).json()
    assert next(r for r in before['delay_reasons'] if r['reason'] == 'Rider offline')['count'] == 1
    assert next(r for r in before['rider_stats'] if r['id'] == rider.id)['busy_seconds'] == 2
    await world_module.persist_once()
    await world_module.load_world()
    after = (await client.get('/analytics')).json()
    assert after['rider_stats'] == before['rider_stats']
    assert after['delay_reasons'] == before['delay_reasons']
    assert world.events[-1].ts.replace(tzinfo=dt.timezone.utc) == timestamp
    await client.post('/reset')
    reset = (await client.get('/analytics')).json()
    assert all(r['count'] == 0 for r in reset['delay_reasons'])
    assert all(r['observed_shift_seconds'] == 0 for r in reset['rider_stats'])


async def test_dispatch_mode_validation_and_reset(client):
    assert (await client.post('/dispatch/mode', json={'mode': 'nearest'})).json()['mode'] == 'nearest'
    assert (await client.get('/dispatch/mode')).json()['mode'] == 'nearest'
    assert (await client.post('/dispatch/mode', json={'mode': 'invalid'})).status_code == 422
    await client.post('/reset')
    assert (await client.get('/dispatch/mode')).json()['mode'] == 'optimized'


async def test_comparison_endpoint_does_not_touch_live_orders(client, monkeypatch):
    from app import comparison
    order = await intervention_order(client)
    async def replay():
        return {'seed': 42, 'results': {'nearest': {}, 'optimized': {}}}
    monkeypatch.setattr(comparison, 'comparison', replay)
    response = await client.get('/analytics/comparison')
    assert response.status_code == 200
    assert response.json()['seed'] == 42
    assert world.orders[order.id] is order


async def test_journey_preserves_quantity_aware_stock_check_and_customer_timeline(client):
    order = await intervention_order(client)
    store = world.stores[0]
    world.inventory[(store.id, 'SKU-MILK')].qty = 1
    world.inventory[(store.id, 'SKU-MILK')].reserved_qty = 0
    order.items[0]['qty'] = 2
    simulator_module.try_allocate(order, world.active_orders())
    journey = (await client.get(f'/orders/{order.id}/journey')).json()
    unavailable = next(s for s in journey['stock_check'] if s['store_id'] == store.id)
    assert unavailable['has_all_items'] is False
    assert unavailable['missing'] == ['SKU-MILK']
    track = (await client.get(f'/track/{order.id}')).json()
    assert track['stages'][0]['ts']
    assert 'cost' not in str(track)
    assert 'decision' not in track
    assert 'priority_score' not in track
    assert (await client.get('/orders/missing/journey')).status_code == 404


async def test_customer_tracking_broadcast_contains_delivery_and_no_internal_scores(client):
    from app.ws import manager
    order = await intervention_order(client)
    messages = []
    class Socket:
        async def send_json(self, message):
            messages.append(message)
    socket = Socket()
    manager.tracking[socket] = order.id
    try:
        order.status = 'delivered'
        order.delivered_at = dt.datetime.now(dt.timezone.utc)
        world.log_event(order.id, 'DELIVERED')
        await manager.broadcast_tracking()
        assert messages[-1]['status'] == 'delivered'
        assert messages[-1]['eta_seconds'] == 0
        assert messages[-1]['stages'][-1]['done']
        assert 'priority_score' not in messages[-1]
        world.orders.pop(order.id)
        await manager.broadcast_tracking()
        assert messages[-1]['type'] == 'not_found'
    finally:
        manager.disconnect(socket)


async def test_checkout_validates_quantity_and_uses_catalog_weight(client):
    body = {'customer_lat': 19.1, 'customer_lng': 72.85,
            'items': [{'sku': 'SKU-MILK', 'name': 'Spoofed', 'qty': 0, 'weight_kg': .01}]}
    assert (await client.post('/orders', json=body)).status_code == 422
    body['items'][0]['qty'] = 1
    response = await client.post('/orders', json=body)
    from app.catalog import CATALOG_BY_SKU
    order = world.orders[response.json()['id']]
    assert order.weight_kg == CATALOG_BY_SKU['SKU-MILK']['weight_kg']
    assert order.items[0]['name'] == CATALOG_BY_SKU['SKU-MILK']['name']
    body['items'][0]['sku'] = 'missing'
    assert (await client.post('/orders', json=body)).status_code == 422


async def test_reroute_uses_remaining_leg_and_rejects_stale_fetch(client, monkeypatch):
    from app import routing
    rider = world.riders[0]
    rider.nav_origin_lat, rider.nav_origin_lng = 19, 72.8
    rider.nav_target_lat, rider.nav_target_lng = 19, 72.9
    rider.route_progress_km = 9
    rider.lat, rider.lng = routing.polyline_progress_point([[72.8, 19], [72.9, 19]], 9)
    async def alternatives(*args):
        rider.nav_target_lng = 72.95
        return [{'polyline': [[72.8, 19], [72.9, 19]], 'approximate': False}]
    monkeypatch.setattr(routing, 'fetch_alternatives', alternatives)
    response = await main_module.evaluate_reroute(rider, {'lat': 19, 'lng': 72.81, 'radius_km': .1, 'multiplier': .1})
    assert response['switched'] is False
    assert 'moved' in response['reason']
    assert rider.nav_target_lng == 72.95


async def test_reroute_does_not_count_already_travelled_distance_as_a_gain(client, monkeypatch):
    from app import routing
    from app.tracking import rider_route
    rider = world.riders[0]
    rider.nav_origin_lat, rider.nav_origin_lng = 19, 72.8
    rider.nav_target_lat, rider.nav_target_lng = 19, 72.9
    rider.route_progress_km = 9
    points = [[72.8, 19], [72.9, 19]]
    rider.lat, rider.lng = routing.polyline_progress_point(points, 9)
    routing._store(routing._key(19, 72.8, 19, 72.9), {'polyline': points, 'approximate': False})
    remaining = rider_route(rider)['polyline_remaining']
    async def same_remaining_route(*args):
        return [{'polyline': remaining, 'approximate': False}]
    monkeypatch.setattr(routing, 'fetch_alternatives', same_remaining_route)
    result = await main_module.evaluate_reroute(rider, {'lat': 20, 'lng': 74, 'radius_km': .1, 'multiplier': .1})
    assert result['switched'] is False
    assert result['gain_seconds'] == 0
    assert result['old_polyline'][0] == remaining[0]


async def test_stock_evidence_survives_persistence(client):
    order = await intervention_order(client)
    expected = order.stock_check
    assert expected
    await world_module.persist_once()
    await world_module.load_world()
    assert world.orders[order.id].stock_check == expected
    assert all(r.vehicle == 'Delivery bike' for r in world.riders)


@pytest_asyncio.fixture
async def client(monkeypatch):
    """Spin up the real FastAPI app against an isolated in-memory DB, with the background
    tick loop and persist loop disabled so tests control state deterministically instead of
    racing them. State lives in the in-memory `world` (see app/world.py) — the DB here only
    backs the initial seed and whatever /reset or an explicit persist_once() call writes."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(main_module, "engine", engine)
    monkeypatch.setattr(main_module, "SessionLocal", SessionLocal)
    monkeypatch.setattr(world_module, "SessionLocal", SessionLocal)

    async def noop():
        return
    monkeypatch.setattr(simulator_module, "run_forever", noop)
    monkeypatch.setattr(simulator_module, "persist_loop", noop)

    async with main_module.app.router.lifespan_context(main_module.app):
        transport = ASGITransport(app=main_module.app)
        async with AsyncClient(transport=transport, base_url="http://test", headers={"X-Ops-Request": "1"}) as ac:
            ac.session_factory = SessionLocal  # smuggle it through for tests that need raw DB access
            yield ac
    await engine.dispose()


async def test_seed_populates_five_dark_stores_and_fifteen_riders(client):
    stores = (await client.get("/dark_stores")).json()
    riders = (await client.get("/riders")).json()
    assert len(stores) == 5
    assert len(riders) == 15


async def test_catalog_lists_skus(client):
    r = await client.get("/catalog")
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 20  # "about 20 SKUs" with categories/price/emoji
    skus = {c["sku"] for c in body}
    assert "SKU-MILK" in skus
    assert all({"category", "price", "emoji", "weight_kg"} <= c.keys() for c in body)


async def test_inventory_is_genuinely_uneven_across_stores(client):
    stores = (await client.get("/dark_stores")).json()
    availabilities = []
    for s in stores:
        inv = (await client.get(f"/dark_stores/{s['id']}/inventory")).json()
        stocked_skus = {row["sku"] for row in inv if row["available"] > 0}
        availabilities.append(stocked_skus)
    # not every store should stock the exact same set — that's the whole point of uneven seeding
    assert len(set(frozenset(a) for a in availabilities)) > 1


async def test_catalog_availability_ranks_stores_with_full_stock_first(client):
    stores = (await client.get("/dark_stores")).json()
    inv = (await client.get(f"/dark_stores/{stores[0]['id']}/inventory")).json()
    stocked_sku = next(row["sku"] for row in inv if row["available"] > 0)

    r = await client.get(f"/catalog/availability?skus={stocked_sku}&customer_lat=19.05&customer_lng=72.84")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 5
    assert all("has_all_items" in e and "distance_km" in e for e in body)
    # results sorted so has_all_items stores come before partial ones
    flags = [e["has_all_items"] for e in body]
    assert flags == sorted(flags, reverse=True)


async def test_restock_increases_available_quantity(client):
    stores = (await client.get("/dark_stores")).json()
    store_id = stores[0]["id"]
    inv_before = (await client.get(f"/dark_stores/{store_id}/inventory")).json()
    row = inv_before[0]

    r = await client.post(f"/dark_stores/{store_id}/restock", json={"sku": row["sku"], "qty": 50})
    assert r.status_code == 200
    assert r.json()["qty"] == row["qty"] + 50

    inv_after = (await client.get(f"/dark_stores/{store_id}/inventory")).json()
    updated = next(x for x in inv_after if x["sku"] == row["sku"])
    assert updated["available"] == row["available"] + 50


async def test_create_order_carries_customer_name_and_address(client):
    body = {
        "customer_lat": 19.05, "customer_lng": 72.84,
        "items": [{"sku": "SKU-MILK", "name": "Milk 1L", "qty": 1, "weight_kg": 0.5}],
        "customer_name": "Test Customer", "address_label": "Flat 101, Test Society",
    }
    created = (await client.post("/orders", json=body)).json()
    orders = (await client.get("/orders")).json()
    match = next(o for o in orders if o["id"] == created["id"])
    assert match["customer_name"] == "Test Customer"
    assert match["address_label"] == "Flat 101, Test Society"


async def test_create_order_appears_in_order_list(client):
    body = {
        "customer_lat": 19.05, "customer_lng": 72.84,
        "items": [{"sku": "SKU-MILK", "name": "Milk 1L", "qty": 1, "weight_kg": 0.5}],
        "priority": True, "promise_minutes": 15,
    }
    created = (await client.post("/orders", json=body)).json()
    assert created["status"] == "created"

    orders = (await client.get("/orders")).json()
    match = next(o for o in orders if o["id"] == created["id"])
    assert match["priority"] is True
    assert match["items"][0]["sku"] == "SKU-MILK"


async def test_create_order_rejects_invalid_promise_window(client):
    body = {
        "customer_lat": 19.05, "customer_lng": 72.84,
        "items": [{"sku": "SKU-MILK", "name": "Milk 1L", "qty": 1, "weight_kg": 0.5}],
        "promise_minutes": 1,  # below the ge=5 floor
    }
    r = await client.post("/orders", json=body)
    assert r.status_code == 422


async def test_kpis_shape_and_defaults_on_empty_history(client):
    r = await client.get("/kpis")
    assert r.status_code == 200
    body = r.json()
    for key in ["avg_delivery_minutes", "on_time_rate_pct", "rider_utilization_pct",
                "sla_breach_rate_pct", "delivered_count", "active_orders", "zone_density"]:
        assert key in body
    assert body["on_time_rate_pct"] is None  # no deliveries yet -> no data, not a made-up 100%


async def test_rider_offline_disruption_frees_their_orders_via_http(client):
    riders = (await client.get("/riders")).json()
    stores = (await client.get("/dark_stores")).json()
    rider_id, store_id = riders[0]["id"], stores[0]["id"]

    order = Order(
        id="ORD-HTTPTEST", customer_lat=19.05, customer_lng=72.84,
        items=[{"sku": "SKU-MILK", "name": "Milk 1L", "qty": 1, "weight_kg": 0.5}],
        weight_kg=0.5, priority=False, created_at=dt.datetime.now(dt.timezone.utc),
        promised_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=20),
        status="packing", store_id=store_id, rider_id=rider_id,
    )
    world.orders[order.id] = order  # seed world state directly — world is the source of truth now

    r = await client.post(f"/disruptions/rider_offline?target={rider_id}")
    assert r.json()["ok"] is True

    orders = (await client.get("/orders")).json()
    freed = next(o for o in orders if o["id"] == "ORD-HTTPTEST")
    assert freed["status"] == "created"
    assert freed["rider_id"] is None

    riders_after = (await client.get("/riders")).json()
    assert next(r for r in riders_after if r["id"] == rider_id)["status"] == "OFFLINE"


async def test_cancel_disruption_releases_reserved_stock_via_http(client):
    stores = (await client.get("/dark_stores")).json()
    store_id = stores[0]["id"]

    inv = world.inventory[(store_id, "SKU-MILK")]
    inv.reserved_qty += 2
    order = Order(
        id="ORD-CANCELTEST", customer_lat=19.05, customer_lng=72.84,
        items=[{"sku": "SKU-MILK", "name": "Milk 1L", "qty": 2, "weight_kg": 0.5}],
        weight_kg=1.0, priority=False, created_at=dt.datetime.now(dt.timezone.utc),
        promised_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=20),
        status="packing", store_id=store_id,
    )
    world.orders[order.id] = order

    r = await client.post("/disruptions/cancel?target=ORD-CANCELTEST")
    assert r.json()["ok"] is True
    assert world.inventory[(store_id, "SKU-MILK")].reserved_qty == 0


async def test_evaluate_reroute_switches_when_alternative_avoids_the_zone(client, monkeypatch):
    from app import routing
    from app.main import evaluate_reroute
    from app.dispatch import add_traffic_zone, clear_traffic_zones

    clear_traffic_zones()
    riders = (await client.get("/riders")).json()
    rider_id = riders[0]["id"]
    rider = world.rider_by_id[rider_id]
    rider.lat, rider.lng = 19.00, 72.80
    rider.nav_origin_lat, rider.nav_origin_lng = 19.00, 72.80
    rider.nav_target_lat, rider.nav_target_lng = 19.00, 72.90  # due east

    # zone sits directly on the straight-line path, heavily slowing it
    zone = add_traffic_zone(19.00, 72.85, radius_km=3.0, multiplier=0.1, duration_minutes=10)
    # the cached "current" route is the straight line through the zone
    routing._store(routing._key(19.00, 72.80, 19.00, 72.90), {
        "polyline": [[72.80, 19.00], [72.90, 19.00]], "distance_m": 11000, "duration_s": 1000, "approximate": False,
    })

    async def fake_alternatives(lat1, lng1, lat2, lng2):
        # detours well north of the zone (radius 3km ~ 0.027 deg) — clear of it entirely
        return [{"polyline": [[lng1, lat1], [72.85, 19.10], [lng2, lat2]], "distance_m": 15000, "duration_s": 1800, "approximate": False}]
    monkeypatch.setattr(routing, "fetch_alternatives", fake_alternatives)

    decision = await evaluate_reroute(rider, zone)
    assert decision["switched"] is True
    assert decision["gain_seconds"] > 0
    clear_traffic_zones()


async def test_evaluate_reroute_keeps_current_route_when_alternative_is_worse(client, monkeypatch):
    from app import routing
    from app.main import evaluate_reroute
    from app.dispatch import add_traffic_zone, clear_traffic_zones

    clear_traffic_zones()
    riders = (await client.get("/riders")).json()
    rider_id = riders[0]["id"]
    rider = world.rider_by_id[rider_id]
    rider.lat, rider.lng = 19.00, 72.80
    rider.nav_origin_lat, rider.nav_origin_lng = 19.00, 72.80
    rider.nav_target_lat, rider.nav_target_lng = 19.00, 72.81  # a short hop, not even near the zone

    zone = add_traffic_zone(20.00, 73.50, radius_km=1.0, multiplier=0.1, duration_minutes=10)  # nowhere near this leg
    routing._store(routing._key(19.00, 72.80, 19.00, 72.81), {
        "polyline": [[72.80, 19.00], [72.81, 19.00]], "distance_m": 1000, "duration_s": 100, "approximate": False,
    })

    async def fake_alternatives(lat1, lng1, lat2, lng2):
        # a longer, slower detour with nothing to gain since the zone doesn't even touch this leg
        return [{"polyline": [[lng1, lat1], [72.85, 19.10], [lng2, lat2]], "distance_m": 20000, "duration_s": 3000, "approximate": False}]
    monkeypatch.setattr(routing, "fetch_alternatives", fake_alternatives)

    decision = await evaluate_reroute(rider, zone)
    assert decision["switched"] is False
    assert "kept current route" in decision["reason"]
    clear_traffic_zones()


async def test_traffic_disruption_creates_a_zone(client):
    r = await client.post("/disruptions/traffic")
    body = r.json()
    assert body["ok"] is True
    assert "zone" in body

    zones = (await client.get("/traffic_zones")).json()
    assert len(zones) == 1

    clear = await client.post("/disruptions/clear_traffic")
    assert clear.json()["ok"] is True
    zones_after = (await client.get("/traffic_zones")).json()
    assert zones_after == []


async def test_stockout_bounces_pre_pickup_orders_back_to_the_pool(client):
    stores = (await client.get("/dark_stores")).json()
    riders = (await client.get("/riders")).json()
    store_id, rider_id = stores[0]["id"], riders[0]["id"]
    rider = world.rider_by_id[rider_id]
    rider.current_load_kg = 2.0

    order = Order(
        id="ORD-STOCKOUT-TEST", customer_lat=19.05, customer_lng=72.84,
        items=[{"sku": "SKU-MILK", "name": "Milk 1L", "qty": 1, "weight_kg": 0.5}],
        weight_kg=0.5, priority=False, created_at=dt.datetime.now(dt.timezone.utc),
        promised_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=20),
        status="packing", store_id=store_id, rider_id=rider_id,
    )
    world.orders[order.id] = order

    r = await client.post(f"/disruptions/stockout?target={store_id}")
    assert r.json()["ok"] is True

    assert order.status == "created"
    assert order.store_id is None
    assert order.rider_id is None
    assert rider.current_load_kg == pytest.approx(1.5)  # released the 0.5kg this order was carrying


async def test_reset_reseeds_clean_state(client):
    await client.post("/orders", json={
        "customer_lat": 19.05, "customer_lng": 72.84,
        "items": [{"sku": "SKU-MILK", "name": "Milk 1L", "qty": 1, "weight_kg": 0.5}],
        "promise_minutes": 15,
    })
    assert len((await client.get("/orders")).json()) >= 1

    r = await client.post("/reset")
    assert r.json()["ok"] is True
    assert (await client.get("/orders")).json() == []
    assert len((await client.get("/dark_stores")).json()) == 5
