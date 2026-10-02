import datetime as dt
import pytest
from httpx import AsyncClient, ASGITransport

from app import main as main_module
from app import world as world_module
from app.simulator import move_riders, try_allocate
from app.models import InventoryItem
from app.world import world
from .conftest import make_store, make_rider, make_order, utcnow
from .test_api import client  # noqa: F401  (fixture)

pytestmark = pytest.mark.asyncio

_FIELDS = ["stores", "store_by_id", "riders", "rider_by_id", "orders", "inventory", "events",
           "pending_events", "pending_new_orders", "dirty_order_ids", "dirty_rider_ids", "dirty_inventory_keys"]


@pytest.fixture
def isolated_world():
    saved = {f: getattr(world, f) for f in _FIELDS}
    world.stores, world.store_by_id = [], {}
    world.riders, world.rider_by_id = [], {}
    world.orders, world.inventory = {}, {}
    world.events, world.pending_events, world.pending_new_orders = [], [], []
    world.dirty_order_ids, world.dirty_rider_ids, world.dirty_inventory_keys = set(), set(), set()
    yield world
    for f, v in saved.items():
        setattr(world, f, v)


def _inv(store_id, sku, qty, reserved):
    return InventoryItem(store_id=store_id, sku=sku, name=sku, qty=qty, reserved_qty=reserved)


async def test_delivery_consumes_stock_instead_of_leaking_the_reservation(isolated_world):
    store = make_store()
    world.stores, world.store_by_id = [store], {store.id: store}
    order = make_order(items=[{"sku": "SKU-A", "name": "A", "qty": 2, "weight_kg": 1.0}])
    rider = make_rider(lat=order.customer_lat, lng=order.customer_lng, status="ON_DELIVERY", load=1.0)
    order.status, order.store_id, order.rider_id = "out_for_delivery", store.id, rider.id
    world.riders, world.rider_by_id = [rider], {rider.id: rider}
    world.orders = {order.id: order}
    world.inventory = {(store.id, "SKU-A"): _inv(store.id, "SKU-A", 10, 2)}

    move_riders([order])  # rider is already at the customer, so this tick completes the drop-off

    row = world.inventory[(store.id, "SKU-A")]
    assert order.status == "delivered"
    assert (row.qty, row.reserved_qty) == (8, 0)


async def test_unallocated_order_is_logged_once_not_every_tick(isolated_world):
    order = make_order()
    world.orders = {order.id: order}
    for _ in range(25):
        try_allocate(order, [order])
    assert sum(e.type == "DELAY_RISK" for e in world.events) == 1


async def test_offline_rider_gives_back_orders_already_picked_up(isolated_world):
    rider = make_rider(load=2.0)
    world.riders, world.rider_by_id = [rider], {rider.id: rider}
    onboard = make_order(id="ORD-ON")
    onboard.status, onboard.rider_id, onboard.store_id = "out_for_delivery", rider.id, "DS-1"
    onboard.picked_up_at = utcnow()
    world.orders = {onboard.id: onboard}
    world.inventory = {("DS-1", "SKU-A"): _inv("DS-1", "SKU-A", 5, 1)}

    freed = world.reassign_rider_orders(rider.id)

    assert freed == ["ORD-ON"]
    assert (onboard.status, onboard.rider_id, onboard.picked_up_at) == ("created", None, None)
    assert world.inventory[("DS-1", "SKU-A")].reserved_qty == 0


async def test_event_history_in_memory_is_bounded(isolated_world, monkeypatch):
    monkeypatch.setattr(world_module, "MAX_EVENTS_IN_MEMORY", 100)
    for i in range(500):
        world.log_event("ORD-X", "TICK", {"i": i})
    assert len(world.events) <= 100


async def test_failed_flush_is_retried_not_lost(isolated_world):
    class BrokenSession:
        def add(self, _):
            pass

        async def execute(self, *a, **k):
            raise RuntimeError("neon unavailable")

        async def commit(self):
            pass

    order = make_order()
    world.orders = {order.id: order}
    world.dirty_order_ids = {order.id}
    world.log_event(order.id, "ORDER_CREATED")

    with pytest.raises(RuntimeError):
        await world_module.persist_once(session=BrokenSession())

    assert order.id in world.dirty_order_ids
    assert any(e.type == "ORDER_CREATED" for e in world.pending_events)


async def test_operator_endpoints_reject_requests_without_ops_header(client):  # noqa: F811
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon:
        assert (await anon.post("/reset")).status_code == 403
        assert (await anon.post("/disruptions/clear_traffic")).status_code == 403
        assert (await anon.post("/simulation/speed", json={"multiplier": 10})).status_code == 403
        assert (await anon.get("/riders")).status_code == 200  # reads and customer ordering stay open
    assert (await client.post("/disruptions/clear_traffic")).status_code == 200


async def test_stockout_releases_reservations_of_orders_it_bounces(client):  # noqa: F811
    store = world.stores[0]
    sku = next(k[1] for k in world.inventory if k[0] == store.id)
    order = make_order(id="ORD-SO", items=[{"sku": sku, "name": sku, "qty": 3, "weight_kg": 1.0}])
    order.status, order.store_id, order.rider_id = "assigned", store.id, world.riders[0].id
    order.assigned_at = utcnow()
    world.add_new_order(order)
    world.reserve_stock(store.id, order.items)

    r = await client.post(f"/disruptions/stockout?target={store.id}")

    assert r.status_code == 200
    assert order.status == "created" and order.store_id is None
    assert all(row.reserved_qty == 0 for (sid, _), row in world.inventory.items() if sid == store.id)


async def test_offline_rider_can_be_restored(client):  # noqa: F811
    rider = world.riders[0]
    await client.post(f"/disruptions/rider_offline?target={rider.id}")
    assert rider.status == "OFFLINE"
    await client.post(f"/disruptions/rider_online?target={rider.id}")
    assert rider.status == "AVAILABLE"


async def test_idle_rider_recharges_and_shift_rolls_forward(isolated_world):
    rider = make_rider(status="AVAILABLE")
    rider.battery_pct = 5.0
    rider.shift_end = utcnow() + dt.timedelta(minutes=10)
    world.riders, world.rider_by_id = [rider], {rider.id: rider}
    move_riders([])
    assert rider.battery_pct > 5.0
    assert rider.shift_end > utcnow() + dt.timedelta(hours=7)
