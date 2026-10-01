import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.db import Base, auto_migrate
from app import models  # noqa: F401 — registers all tables on Base.metadata

pytestmark = pytest.mark.asyncio


async def test_auto_migrate_adds_missing_columns_to_an_existing_table():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        # simulate a table that existed before customer_name/address_label were added to the model
        await conn.execute(text(
            "CREATE TABLE orders (id VARCHAR PRIMARY KEY, customer_lat FLOAT, customer_lng FLOAT, "
            "items JSON, weight_kg FLOAT, priority BOOLEAN, status VARCHAR, risk VARCHAR, "
            "created_at DATETIME, promised_at DATETIME)"
        ))
        await conn.execute(text(
            "INSERT INTO orders (id, customer_lat, customer_lng, items, weight_kg, priority, status, risk, created_at, promised_at) "
            "VALUES ('ORD-1', 19.0, 72.8, '[]', 1.0, 0, 'created', 'LOW', '2026-01-01', '2026-01-01')"
        ))

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # creates only genuinely-new tables
        await auto_migrate(conn)  # should add customer_name/address_label (and anything else missing) to orders

    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT customer_name, address_label FROM orders WHERE id = 'ORD-1'"))
        row = result.fetchone()
        assert row is not None  # pre-existing row survived the ALTER, no data loss
        assert row[0] == "Customer"  # column default applied

    await engine.dispose()


async def test_rider_time_counters_migrate_with_zero_defaults():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE riders (id VARCHAR PRIMARY KEY)"))
        await conn.execute(text("INSERT INTO riders (id) VALUES ('OLD-RIDER')"))
        await auto_migrate(conn)
        row = (await conn.execute(text("SELECT busy_seconds, observed_shift_seconds FROM riders"))).one()
        assert tuple(row) == (0, 0)
    await engine.dispose()
