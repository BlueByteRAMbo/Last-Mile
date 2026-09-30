import datetime as dt
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db import Base
from app.models import DarkStore, InventoryItem, Rider, Order

pytestmark = pytest.mark.asyncio


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as s:
        yield s
    await engine.dispose()


def make_store(id="DS-1", lat=19.10, lng=72.85, packing_capacity=6, packing_seconds=60):
    return DarkStore(id=id, name=id, lat=lat, lng=lng, packing_capacity=packing_capacity, packing_seconds_per_order=packing_seconds)


def make_rider(id="RX-1", lat=19.10, lng=72.85, capacity_kg=15.0, load=0.0, status="AVAILABLE", speed=30.0):
    return Rider(id=id, name=id, lat=lat, lng=lng, home_store_id="DS-1", capacity_kg=capacity_kg,
                 current_load_kg=load, speed_kmh=speed, battery_pct=100, status=status,
                 shift_end=utcnow() + dt.timedelta(hours=8))


def make_order(id="ORD-1", lat=19.11, lng=72.86, weight=1.0, priority=False, promise_min=20, items=None):
    return Order(id=id, customer_lat=lat, customer_lng=lng, items=items or [{"sku": "SKU-A", "name": "A", "qty": 1, "weight_kg": weight}],
                 weight_kg=weight, priority=priority, created_at=utcnow(),
                 promised_at=utcnow() + dt.timedelta(minutes=promise_min), status="created")


def make_inventory(store_id="DS-1", sku="SKU-A", qty=10):
    return InventoryItem(store_id=store_id, sku=sku, name=sku, qty=qty, reserved_qty=0)
