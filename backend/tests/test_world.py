import datetime as dt
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app import world as world_module
from app.world import world
from app.dispatch import score_candidates_sync
from .conftest import make_store, make_rider, make_order, make_inventory, utcnow


def test_low_battery_rider_excluded_from_candidates():
    store = make_store()
    dead = make_rider(id="RX-DEAD")
    dead.battery_pct = 5.0
    alive = make_rider(id="RX-ALIVE")
    order = make_order()

    candidates = score_candidates_sync(order, [store], [dead, alive], {}, {(store.id, "SKU-A"): make_inventory(qty=10)})
    rider_ids = {c["rider_id"] for c in candidates}
    assert "RX-DEAD" not in rider_ids
    assert "RX-ALIVE" in rider_ids


def test_rider_past_shift_end_excluded_from_candidates():
    store = make_store()
    tired = make_rider(id="RX-TIRED")
    tired.shift_end = utcnow() - dt.timedelta(minutes=1)  # shift already over
    fresh = make_rider(id="RX-FRESH")
    order = make_order()

    candidates = score_candidates_sync(order, [store], [tired, fresh], {}, {(store.id, "SKU-A"): make_inventory(qty=10)})
    rider_ids = {c["rider_id"] for c in candidates}
    assert "RX-TIRED" not in rider_ids
    assert "RX-FRESH" in rider_ids


def test_shift_end_comparison_tolerates_naive_datetime():
    """Sqlite round-trips drop tzinfo; this must not crash the comparison."""
    store = make_store()
    rider = make_rider(id="RX-NAIVE")
    rider.shift_end = dt.datetime.now() + dt.timedelta(hours=8)  # naive, far in the future
    order = make_order()

    candidates = score_candidates_sync(order, [store], [rider], {}, {(store.id, "SKU-A"): make_inventory(qty=10)})
    assert any(c["rider_id"] == "RX-NAIVE" for c in candidates)


@pytest_asyncio.fixture
async def world_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(world_module, "SessionLocal", SessionLocal)
    yield SessionLocal
    await engine.dispose()


async def test_persist_once_writes_dirty_rider_and_order_and_inventory(world_db):
    from app.models import DarkStore, Rider, Order, InventoryItem

    store = DarkStore(id="DS-1", name="DS-1", lat=19.1, lng=72.8, packing_capacity=6, packing_seconds_per_order=60)
    rider = Rider(id="RX-1", name="RX-1", lat=19.1, lng=72.8, home_store_id="DS-1", capacity_kg=15,
                  current_load_kg=0, speed_kmh=30, battery_pct=100, status="AVAILABLE",
                  shift_end=utcnow() + dt.timedelta(hours=8))
    order = Order(id="ORD-1", customer_lat=19.1, customer_lng=72.8, items=[], weight_kg=1.0,
                  priority=False, created_at=utcnow(), promised_at=utcnow() + dt.timedelta(minutes=20),
                  status="created", risk="LOW")
    inv = InventoryItem(store_id="DS-1", sku="SKU-A", name="A", qty=10, reserved_qty=0)

    async with world_db() as session:
        session.add_all([store, rider, order, inv])
        await session.commit()
        await session.refresh(inv)

    world.stores = [store]
    world.store_by_id = {"DS-1": store}
    world.riders = [rider]
    world.rider_by_id = {"RX-1": rider}
    world.orders = {"ORD-1": order}
    world.inventory = {("DS-1", "SKU-A"): inv}
    world.dirty_rider_ids = set()
    world.dirty_order_ids = set()
    world.dirty_inventory_keys = set()
    world.pending_events = []
    world.pending_new_orders = []

    rider.lat, rider.status = 19.2, "ON_DELIVERY"
    world.mark_rider_dirty("RX-1")
    order.status = "assigned"
    world.mark_order_dirty("ORD-1")
    inv.reserved_qty = 3
    world.mark_inventory_dirty(("DS-1", "SKU-A"))
    world.log_event("ORD-1", "ASSIGNED")

    await world_module.persist_once()

    async with world_db() as session:
        r = (await session.execute(select(Rider).where(Rider.id == "RX-1"))).scalar_one()
        o = (await session.execute(select(Order).where(Order.id == "ORD-1"))).scalar_one()
        i = (await session.execute(select(InventoryItem).where(InventoryItem.store_id == "DS-1"))).scalar_one()
        assert r.status == "ON_DELIVERY" and round(r.lat, 1) == 19.2
        assert o.status == "assigned"
        assert i.reserved_qty == 3
        from app.models import OrderEvent
        events = (await session.execute(select(OrderEvent))).scalars().all()
        assert any(e.type == "ASSIGNED" for e in events)

    # dirty sets and pending buffers are drained after a successful persist
    assert world.dirty_rider_ids == set()
    assert world.dirty_order_ids == set()
    assert world.dirty_inventory_keys == set()
    assert world.pending_events == []


async def test_persist_once_inserts_pending_new_order(world_db):
    from app.models import Order

    new_order = Order(id="ORD-NEW", customer_lat=19.1, customer_lng=72.8, items=[], weight_kg=1.0,
                       priority=False, created_at=utcnow(), promised_at=utcnow() + dt.timedelta(minutes=20),
                       status="created", risk="LOW")
    world.orders = {"ORD-NEW": new_order}
    world.pending_new_orders = [new_order]
    world.dirty_rider_ids = set()
    world.dirty_order_ids = set()
    world.dirty_inventory_keys = set()
    world.pending_events = []

    await world_module.persist_once()

    async with world_db() as session:
        o = (await session.execute(select(Order).where(Order.id == "ORD-NEW"))).scalar_one()
        assert o.status == "created"
    assert world.pending_new_orders == []
