import datetime as dt
import pytest
from app.dispatch import (
    score_candidates, score_candidates_sync, allocate, reserve_stock, release_stock,
    reassign_rider_orders, cancel_order, store_has_stock, cheapest_insertion_cost,
)
from .conftest import make_store, make_rider, make_order, make_inventory, utcnow


async def test_out_of_stock_store_rejected(session):
    store = make_store()
    session.add_all([store, make_inventory(qty=0), make_rider()])
    order = make_order()
    session.add(order)
    await session.flush()

    assert await store_has_stock(session, store, order.items) is False
    candidates = await score_candidates(session, order)
    assert candidates == []


async def test_overloaded_and_offline_riders_excluded(session):
    session.add_all([
        make_store(), make_inventory(qty=10),
        make_rider(id="RX-FULL", load=14.5, capacity_kg=15.0),  # 0.5kg spare, order needs 5kg
        make_rider(id="RX-OFF", status="OFFLINE"),
        make_rider(id="RX-OK"),
    ])
    order = make_order(weight=5.0, items=[{"sku": "SKU-A", "name": "A", "qty": 1, "weight_kg": 5.0}])
    session.add(order)
    await session.flush()

    candidates = await score_candidates(session, order)
    rider_ids = {c["rider_id"] for c in candidates}
    assert "RX-FULL" not in rider_ids
    assert "RX-OFF" not in rider_ids
    assert "RX-OK" in rider_ids


async def test_tight_deadline_marked_infeasible(session):
    far_store = make_store(id="DS-FAR", lat=20.5, lng=74.5)  # ~190km away
    session.add_all([far_store, make_inventory(store_id="DS-FAR", qty=10), make_rider(lat=20.5, lng=74.5)])
    order = make_order(promise_min=1)  # 1 minute promise, impossible over that distance
    session.add(order)
    await session.flush()

    candidates = await score_candidates(session, order)
    assert all(c["feasible"] is False for c in candidates if c["store_id"] == "DS-FAR") or candidates == []


async def test_priority_order_scores_lower_cost(session):
    session.add_all([make_store(), make_inventory(qty=10), make_rider()])
    normal = make_order(id="ORD-N", priority=False)
    urgent = make_order(id="ORD-P", priority=True)
    session.add_all([normal, urgent])
    await session.flush()

    normal_cost = (await score_candidates(session, normal))[0]["cost"]
    urgent_cost = (await score_candidates(session, urgent))[0]["cost"]
    assert urgent_cost < normal_cost


async def test_batching_benefit_favors_rider_already_at_store(session):
    store = make_store()
    session.add_all([store, make_inventory(qty=10)])
    busy_rider = make_rider(id="RX-BUSY")
    idle_rider = make_rider(id="RX-IDLE")
    session.add_all([busy_rider, idle_rider])
    existing = make_order(id="ORD-EXIST")
    session.add(existing)
    await session.flush()
    existing.rider_id = busy_rider.id
    existing.store_id = store.id
    existing.status = "packing"
    new_order = make_order(id="ORD-NEW")
    session.add(new_order)
    await session.flush()

    candidates = await score_candidates(session, new_order)
    busy_cost = next(c["cost"] for c in candidates if c["rider_id"] == "RX-BUSY" and c["store_id"] == store.id)
    idle_cost = next(c["cost"] for c in candidates if c["rider_id"] == "RX-IDLE" and c["store_id"] == store.id)
    # batching benefit (-W_BATCH) outweighs the +1 workload penalty for the busy rider
    assert busy_cost < idle_cost


async def test_allocate_reserves_stock_and_picks_best(session):
    session.add_all([make_store(), make_inventory(qty=1), make_rider()])
    order = make_order()
    session.add(order)
    await session.flush()

    decision = await allocate(session, order)
    assert decision is not None
    assert decision["chosen"]["store_id"] == "DS-1"
    await reserve_stock(session, "DS-1", order.items)

    from app.models import InventoryItem
    from sqlalchemy import select
    inv = (await session.execute(select(InventoryItem).where(InventoryItem.store_id == "DS-1"))).scalar_one()
    assert inv.reserved_qty == 1
    assert inv.qty - inv.reserved_qty == 0  # now out of stock for the next order


async def test_release_stock_reverses_reservation(session):
    session.add_all([make_store(), make_inventory(qty=5)])
    await session.flush()
    order = make_order()
    await reserve_stock(session, "DS-1", order.items)

    from app.models import InventoryItem
    from sqlalchemy import select
    inv = (await session.execute(select(InventoryItem).where(InventoryItem.store_id == "DS-1"))).scalar_one()
    assert inv.reserved_qty == 1

    await release_stock(session, "DS-1", order.items)
    inv = (await session.execute(select(InventoryItem).where(InventoryItem.store_id == "DS-1"))).scalar_one()
    assert inv.reserved_qty == 0


async def test_rider_dropout_frees_pre_pickup_orders(session):
    store = make_store()
    rider = make_rider(id="RX-DROP", load=2.0)
    session.add_all([store, make_inventory(qty=10), rider])
    o1 = make_order(id="ORD-1", weight=1.0)
    o2_out_for_delivery = make_order(id="ORD-2", weight=1.0)
    session.add_all([o1, o2_out_for_delivery])
    await session.flush()
    o1.rider_id = rider.id
    o1.store_id = store.id
    o1.status = "packing"
    o2_out_for_delivery.rider_id = rider.id
    o2_out_for_delivery.store_id = store.id
    o2_out_for_delivery.status = "out_for_delivery"  # already picked up -> stays with rider

    freed = await reassign_rider_orders(session, "RX-DROP")
    await session.flush()

    assert "ORD-1" in freed
    assert "ORD-2" not in freed
    assert o1.status == "created"
    assert o1.rider_id is None
    assert o1.store_id is None
    assert o2_out_for_delivery.status == "out_for_delivery"  # untouched


async def test_cancel_order_releases_stock_and_load(session):
    store = make_store()
    rider = make_rider(id="RX-C", load=3.0)
    session.add_all([store, make_inventory(qty=10), rider])
    order = make_order(weight=3.0)
    session.add(order)
    await session.flush()
    await reserve_stock(session, store.id, order.items)
    order.store_id = store.id
    order.rider_id = rider.id
    order.status = "packing"

    ok = await cancel_order(session, order)
    assert ok is True
    assert order.status == "cancelled"
    assert rider.current_load_kg == 0.0

    from app.models import InventoryItem
    from sqlalchemy import select
    inv = (await session.execute(select(InventoryItem).where(InventoryItem.store_id == store.id))).scalar_one()
    assert inv.reserved_qty == 0

    # cancelling twice is a no-op, not a double-release
    assert await cancel_order(session, order) is False


async def test_assignment_stability_keeps_incumbent_rider(session):
    store = make_store()
    session.add_all([store, make_inventory(qty=10)])
    incumbent = make_rider(id="RX-INC")
    contender = make_rider(id="RX-NEW")
    session.add_all([incumbent, contender])
    order = make_order()
    session.add(order)
    await session.flush()
    order.rider_id = incumbent.id  # already committed to this rider

    candidates = await score_candidates(session, order)
    incumbent_cost = next(c["cost"] for c in candidates if c["rider_id"] == "RX-INC")
    contender_cost = next(c["cost"] for c in candidates if c["rider_id"] == "RX-NEW")
    # identical physical situation otherwise -> stability penalty makes switching strictly worse
    assert incumbent_cost < contender_cost


def test_batch_rejected_when_detour_exceeds_threshold():
    store = make_store(lat=19.10, lng=72.85)
    rider = make_rider(lat=19.10, lng=72.85, speed=30.0)
    # existing stop a stone's throw from the store; new order ~15km away in an unrelated direction
    nearby = make_order(id="ORD-NEAR", lat=19.102, lng=72.852)
    far = make_order(id="ORD-FAR", lat=19.25, lng=73.05, promise_min=120)  # generous deadline — detour is the blocker, not the clock

    idx, added, feasible = cheapest_insertion_cost(rider, [nearby], far, store)
    assert added > 90.0  # well past the 90s batching threshold
    assert feasible is False


def test_batch_rejected_when_it_would_break_an_existing_promise():
    store = make_store(lat=19.10, lng=72.85)
    rider = make_rider(lat=19.10, lng=72.85, speed=30.0)
    # existing order's promise has already passed; any added travel time only makes it worse
    tight = make_order(id="ORD-TIGHT", lat=19.102, lng=72.852, promise_min=-5)
    new = make_order(id="ORD-NEW", lat=19.103, lng=72.853, promise_min=60)

    idx, added, feasible = cheapest_insertion_cost(rider, [tight], new, store)
    assert feasible is False


def test_batch_accepted_within_threshold_and_promise():
    store = make_store(lat=19.10, lng=72.85)
    rider = make_rider(lat=19.10, lng=72.85, speed=30.0)
    first = make_order(id="ORD-1", lat=19.102, lng=72.852, promise_min=30)
    second = make_order(id="ORD-2", lat=19.103, lng=72.853, promise_min=30)  # a couple hundred metres further, same direction

    idx, added, feasible = cheapest_insertion_cost(rider, [first], second, store)
    assert feasible is True
    assert added <= 90.0


def test_packing_wait_reflects_real_queue_depth():
    store = make_store(packing_capacity=2, packing_seconds=100)
    rider = make_rider()
    order = make_order()
    # 4 orders already queued/packing at this store, across any rider
    queued = [make_order(id=f"ORD-Q{i}", lat=19.10, lng=72.85) for i in range(4)]
    for o in queued:
        o.store_id = store.id
        o.status = "assigned"

    candidates = score_candidates_sync(order, [store], [rider], {rider.id: queued}, {("DS-1", "SKU-A"): make_inventory(qty=10)})
    reason = next(c["reason"] for c in candidates if c["store_id"] == store.id)
    assert reason["packing_wait_seconds"] == pytest.approx(4 * 100 / 2)  # queue_depth * packing_seconds / capacity


from app.dispatch import rolling_reoptimize_sync, HAS_ORTOOLS

pytestmark_ortools = pytest.mark.skipif(not HAS_ORTOOLS, reason="ortools not installed")


@pytestmark_ortools
def test_reoptimize_applies_a_sequence_with_gain_above_threshold():
    rider = make_rider(lat=19.00, lng=72.80, speed=30.0)
    # a deliberately zigzag starting order: far, then near, then far again — OR-Tools should find
    # the obviously-shorter "near then far then far" ordering, saving well over 60s
    far1 = make_order(id="ORD-FAR1", lat=19.30, lng=73.10, promise_min=120)
    near = make_order(id="ORD-NEAR", lat=19.01, lng=72.81, promise_min=120)
    far2 = make_order(id="ORD-FAR2", lat=19.32, lng=73.12, promise_min=120)
    for seq, o in enumerate([far1, near, far2]):
        o.route_seq = seq

    decision = rolling_reoptimize_sync(rider, [far1, near, far2])
    assert decision is not None
    assert decision["applied"] is True
    assert decision["gain_seconds"] >= 60.0


@pytestmark_ortools
def test_reoptimize_keeps_current_route_when_gain_is_small():
    rider = make_rider(lat=19.00, lng=72.80, speed=30.0)
    # already close to optimal (strictly increasing distance along one direction) — OR-Tools has
    # little to nothing to gain by reshuffling
    a = make_order(id="ORD-A", lat=19.01, lng=72.81, promise_min=120)
    b = make_order(id="ORD-B", lat=19.02, lng=72.82, promise_min=120)
    c = make_order(id="ORD-C", lat=19.03, lng=72.83, promise_min=120)
    for seq, o in enumerate([a, b, c]):
        o.route_seq = seq

    decision = rolling_reoptimize_sync(rider, [a, b, c])
    if decision is not None:
        assert decision["applied"] is False
        assert decision["gain_seconds"] < 60.0
    # route_seq unchanged either way
    assert [o.route_seq for o in (a, b, c)] == [0, 1, 2]


@pytestmark_ortools
def test_reoptimize_applies_when_it_fixes_a_missed_deadline():
    rider = make_rider(lat=19.00, lng=72.80, speed=30.0)
    # tight sits right where the rider already is (visiting it first costs ~nothing); the current
    # sequence visits the far stop first and backtracks to tight, blowing its 1-minute promise
    tight = make_order(id="ORD-TIGHT", lat=19.0001, lng=72.8001, promise_min=1)
    far = make_order(id="ORD-FAR", lat=19.02, lng=72.82, promise_min=120)
    far.route_seq, tight.route_seq = 0, 1  # far visited first -> tight misses its promise

    assert _misses_a_deadline_for_test(rider, [far, tight])

    decision = rolling_reoptimize_sync(rider, [far, tight])
    assert decision is not None
    assert decision["applied"] is True


def _misses_a_deadline_for_test(rider, ordered):
    from app.dispatch import _misses_a_deadline
    return _misses_a_deadline(rider, ordered)


from app.dispatch import suggest_split_fulfillment


def test_split_fulfillment_suggests_best_single_store_and_two_store_split():
    store_a = make_store(id="DS-A")
    store_b = make_store(id="DS-B")
    order = make_order(items=[
        {"sku": "SKU-MILK", "name": "Milk", "qty": 1, "weight_kg": 0.5},
        {"sku": "SKU-RICE", "name": "Rice", "qty": 1, "weight_kg": 5.0},
    ])
    # store A has milk but not rice; store B has rice (covers what A is missing)
    inventory_map = {
        ("DS-A", "SKU-MILK"): make_inventory(store_id="DS-A", sku="SKU-MILK", qty=10),
        ("DS-A", "SKU-RICE"): make_inventory(store_id="DS-A", sku="SKU-RICE", qty=0),
        ("DS-B", "SKU-MILK"): make_inventory(store_id="DS-B", sku="SKU-MILK", qty=0),
        ("DS-B", "SKU-RICE"): make_inventory(store_id="DS-B", sku="SKU-RICE", qty=10),
    }

    suggestion = suggest_split_fulfillment(order, [store_a, store_b], inventory_map)
    assert suggestion is not None
    assert suggestion["best_single_store"]["store_id"] == "DS-A"
    assert suggestion["best_single_store"]["missing"] == ["SKU-RICE"]
    assert suggestion["two_store_split"] is not None
    assert suggestion["two_store_split"]["secondary_store_id"] == "DS-B"
    assert suggestion["two_store_split"]["secondary_covers"] == ["SKU-RICE"]


def test_split_fulfillment_returns_none_when_a_store_has_everything():
    store = make_store()
    order = make_order()
    suggestion = suggest_split_fulfillment(order, [store], {("DS-1", "SKU-A"): make_inventory(qty=10)})
    assert suggestion is None
