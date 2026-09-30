import datetime as dt
import pytest
from sqlalchemy import select
from app.simulator import advance_packing
from app.models import Order
from .conftest import make_store, make_rider, make_order, make_inventory, utcnow

pytestmark = pytest.mark.asyncio


async def test_packing_queue_prioritizes_priority_then_risk_over_fifo(session):
    store = make_store(packing_capacity=1, packing_seconds=9999)  # only 1 slot, nothing completes mid-test
    session.add_all([store, make_inventory(qty=10)])
    await session.flush()

    old_fifo = make_order(id="ORD-OLD", promise_min=30)
    risky = make_order(id="ORD-RISKY", promise_min=30)
    urgent = make_order(id="ORD-URGENT", priority=True, promise_min=30)
    session.add_all([old_fifo, risky, urgent])
    await session.flush()

    now = utcnow()
    for i, o in enumerate([old_fifo, risky, urgent]):
        o.store_id = store.id
        o.status = "assigned"
        o.assigned_at = now - dt.timedelta(seconds=30 - i)  # old_fifo assigned first
    risky.risk = "SEVERE"

    ctx = {"all_orders": [old_fifo, risky, urgent]}
    advance_packing(session, [store], ctx)

    packing = (await session.execute(select(Order).where(Order.status == "packing"))).scalars().all()
    assert len(packing) == 1
    # priority beats an older FIFO order and a merely-at-risk one, even though it was assigned last
    assert packing[0].id == "ORD-URGENT"


async def test_packing_queue_falls_back_to_risk_then_fifo_without_priority(session):
    store = make_store(packing_capacity=1, packing_seconds=9999)
    session.add_all([store, make_inventory(qty=10)])
    await session.flush()

    old_fifo = make_order(id="ORD-OLD2", promise_min=30)
    risky = make_order(id="ORD-RISKY2", promise_min=30)
    session.add_all([old_fifo, risky])
    await session.flush()

    now = utcnow()
    old_fifo.store_id = store.id
    old_fifo.status = "assigned"
    old_fifo.assigned_at = now - dt.timedelta(seconds=30)
    risky.store_id = store.id
    risky.status = "assigned"
    risky.assigned_at = now - dt.timedelta(seconds=5)  # assigned later than old_fifo
    risky.risk = "DELAYED"

    ctx = {"all_orders": [old_fifo, risky]}
    advance_packing(session, [store], ctx)

    packing = (await session.execute(select(Order).where(Order.status == "packing"))).scalars().all()
    assert len(packing) == 1
    # no priority orders here -> worse risk still jumps the older FIFO order
    assert packing[0].id == "ORD-RISKY2"
