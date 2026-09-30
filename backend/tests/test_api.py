import datetime as dt
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app import simulator as simulator_module
from app.db import Base
from app.models import Order

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def client(monkeypatch):
    """Spin up the real FastAPI app against an isolated in-memory DB, with the background
    tick loop disabled so tests control state deterministically instead of racing it."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(main_module, "engine", engine)
    monkeypatch.setattr(main_module, "SessionLocal", SessionLocal)
    monkeypatch.setattr(simulator_module, "SessionLocal", SessionLocal)

    async def noop_forever():
        return
    monkeypatch.setattr(simulator_module, "run_forever", noop_forever)

    async with main_module.app.router.lifespan_context(main_module.app):
        transport = ASGITransport(app=main_module.app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
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
    skus = {c["sku"] for c in r.json()}
    assert "SKU-MILK" in skus


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
    assert body["on_time_rate_pct"] == 100.0  # no deliveries yet -> vacuously on-time


async def test_rider_offline_disruption_frees_their_orders_via_http(client):
    riders = (await client.get("/riders")).json()
    stores = (await client.get("/dark_stores")).json()
    rider_id, store_id = riders[0]["id"], stores[0]["id"]

    async with client.session_factory() as session:
        order = Order(
            id="ORD-HTTPTEST", customer_lat=19.05, customer_lng=72.84,
            items=[{"sku": "SKU-MILK", "name": "Milk 1L", "qty": 1, "weight_kg": 0.5}],
            weight_kg=0.5, priority=False, created_at=dt.datetime.now(dt.timezone.utc),
            promised_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=20),
            status="packing", store_id=store_id, rider_id=rider_id,
        )
        session.add(order)
        await session.commit()

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

    async with client.session_factory() as session:
        from app.models import InventoryItem
        inv = (await session.execute(select(InventoryItem).where(InventoryItem.store_id == store_id, InventoryItem.sku == "SKU-MILK"))).scalar_one()
        inv.reserved_qty += 2
        await session.commit()
        order = Order(
            id="ORD-CANCELTEST", customer_lat=19.05, customer_lng=72.84,
            items=[{"sku": "SKU-MILK", "name": "Milk 1L", "qty": 2, "weight_kg": 0.5}],
            weight_kg=1.0, priority=False, created_at=dt.datetime.now(dt.timezone.utc),
            promised_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=20),
            status="packing", store_id=store_id,
        )
        session.add(order)
        await session.commit()

    r = await client.post("/disruptions/cancel?target=ORD-CANCELTEST")
    assert r.json()["ok"] is True

    async with client.session_factory() as session:
        from app.models import InventoryItem
        inv = (await session.execute(select(InventoryItem).where(InventoryItem.store_id == store_id, InventoryItem.sku == "SKU-MILK"))).scalar_one()
        assert inv.reserved_qty == 0


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
