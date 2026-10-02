import pytest


def test_naive_mode_chooses_nearest_eligible_rider_instead_of_weighted_cost(monkeypatch):
    from app import dispatch
    candidates = [
        {'feasible': True, 'cost': 1, 'store_id': 'S', 'rider_id': 'far', 'reason': {'pickup_eta_seconds': 100}},
        {'feasible': True, 'cost': 9, 'store_id': 'S', 'rider_id': 'near', 'reason': {'pickup_eta_seconds': 10}},
        {'feasible': False, 'cost': 0, 'store_id': 'S', 'rider_id': 'ineligible', 'reason': {'pickup_eta_seconds': 0}},
    ]
    monkeypatch.setattr(dispatch, 'score_candidates_sync', lambda *args: candidates)
    assert dispatch.allocate_sync(None, [], [], {}, {}, 'nearest')['chosen']['rider_id'] == 'near'
    assert dispatch.allocate_sync(None, [], [], {}, {}, 'optimized')['chosen']['rider_id'] == 'far'
from app.dispatch import score_candidates_sync, allocate_sync, check_stock, cheapest_insertion_cost
from app.world import world
from .conftest import make_store, make_rider, make_order, make_inventory
from .test_high_fixes import isolated_world  # noqa: F401  (fixture)


def inv_map(*rows):
    return {(r.store_id, r.sku): r for r in rows}


def test_out_of_stock_store_rejected():
    store, order = make_store(), make_order()
    inventory = inv_map(make_inventory(qty=0))
    assert check_stock(inventory, "DS-1", order.items) is False
    assert score_candidates_sync(order, [store], [make_rider()], {}, inventory) == []


def test_overloaded_and_offline_riders_excluded():
    order = make_order(weight=5.0, items=[{"sku": "SKU-A", "name": "A", "qty": 1, "weight_kg": 5.0}])
    riders = [make_rider(id="RX-FULL", load=14.5, capacity_kg=15.0),  # 0.5kg spare, order needs 5kg
              make_rider(id="RX-OFF", status="OFFLINE"), make_rider(id="RX-OK")]
    candidates = score_candidates_sync(order, [make_store()], riders, {}, inv_map(make_inventory(qty=10)))
    rider_ids = {c["rider_id"] for c in candidates}
    assert "RX-FULL" not in rider_ids and "RX-OFF" not in rider_ids
    assert "RX-OK" in rider_ids


def test_tight_deadline_marked_infeasible():
    far_store = make_store(id="DS-FAR", lat=20.5, lng=74.5)  # ~190km away
    order = make_order(promise_min=1)  # 1 minute promise, impossible over that distance
    candidates = score_candidates_sync(order, [far_store], [make_rider(lat=20.5, lng=74.5)], {},
                                       inv_map(make_inventory(store_id="DS-FAR", qty=10)))
    assert all(c["feasible"] is False for c in candidates if c["store_id"] == "DS-FAR") or candidates == []


def test_priority_order_scores_lower_cost():
    args = ([make_store()], [make_rider()], {}, inv_map(make_inventory(qty=10)))
    normal_cost = score_candidates_sync(make_order(id="ORD-N", priority=False), *args)[0]["cost"]
    urgent_cost = score_candidates_sync(make_order(id="ORD-P", priority=True), *args)[0]["cost"]
    assert urgent_cost < normal_cost


def test_batching_benefit_favors_rider_already_at_store(isolated_world):  # noqa: F811
    store = make_store()
    world.stores, world.store_by_id = [store], {store.id: store}
    busy, idle = make_rider(id="RX-BUSY"), make_rider(id="RX-IDLE")
    existing = make_order(id="ORD-EXIST")
    existing.rider_id, existing.store_id, existing.status = busy.id, store.id, "packing"
    candidates = score_candidates_sync(make_order(id="ORD-NEW"), [store], [busy, idle], {busy.id: [existing]},
                                       inv_map(make_inventory(qty=10)))
    busy_cost = next(c["cost"] for c in candidates if c["rider_id"] == "RX-BUSY")
    idle_cost = next(c["cost"] for c in candidates if c["rider_id"] == "RX-IDLE")
    # batching benefit (-W_BATCH) outweighs the +1 workload penalty for the busy rider
    assert busy_cost < idle_cost


def test_allocate_picks_best_and_reservation_exhausts_stock(isolated_world):  # noqa: F811
    store, order = make_store(), make_order()
    world.stores, world.store_by_id = [store], {store.id: store}
    world.inventory = inv_map(make_inventory(qty=1))
    decision = allocate_sync(order, world.stores, [make_rider()], {}, world.inventory)
    assert decision["chosen"]["store_id"] == "DS-1"
    world.reserve_stock("DS-1", order.items)
    assert world.inventory[("DS-1", "SKU-A")].reserved_qty == 1
    assert check_stock(world.inventory, "DS-1", order.items) is False  # nothing left for the next order


def test_release_stock_reverses_reservation(isolated_world):  # noqa: F811
    world.inventory = inv_map(make_inventory(qty=5))
    order = make_order()
    world.reserve_stock("DS-1", order.items)
    assert world.inventory[("DS-1", "SKU-A")].reserved_qty == 1
    world.release_stock("DS-1", order.items)
    assert world.inventory[("DS-1", "SKU-A")].reserved_qty == 0


def test_cancel_order_releases_stock_and_load(isolated_world):  # noqa: F811
    store, rider, order = make_store(), make_rider(id="RX-C", load=3.0), make_order(weight=3.0)
    world.stores, world.store_by_id = [store], {store.id: store}
    world.riders, world.rider_by_id = [rider], {rider.id: rider}
    world.inventory = inv_map(make_inventory(qty=10))
    world.orders = {order.id: order}
    world.reserve_stock(store.id, order.items)
    order.store_id, order.rider_id, order.status = store.id, rider.id, "packing"

    assert world.cancel_order(order) is True
    assert order.status == "cancelled" and rider.current_load_kg == 0.0
    assert world.inventory[(store.id, "SKU-A")].reserved_qty == 0
    assert world.cancel_order(order) is False  # cancelling twice is a no-op, not a double-release


def test_assignment_stability_keeps_incumbent_rider():
    order = make_order()
    order.rider_id = "RX-INC"  # already committed to this rider
    candidates = score_candidates_sync(order, [make_store()], [make_rider(id="RX-INC"), make_rider(id="RX-NEW")], {},
                                       inv_map(make_inventory(qty=10)))
    incumbent_cost = next(c["cost"] for c in candidates if c["rider_id"] == "RX-INC")
    contender_cost = next(c["cost"] for c in candidates if c["rider_id"] == "RX-NEW")
    # identical physical situation otherwise -> stability penalty makes switching strictly worse
    assert incumbent_cost < contender_cost


def test_batching_accounts_for_the_pickup_trip(isolated_world):  # noqa: F811
    """A rider far from the store used to look on time because only the drop legs were counted."""
    store = make_store(lat=19.10, lng=72.85)
    world.stores, world.store_by_id = [store], {store.id: store}
    far_rider = make_rider(lat=19.40, lng=72.85, speed=30.0)  # ~33 km from the store
    existing = make_order(id="ORD-1", lat=19.102, lng=72.852, promise_min=30)
    existing.store_id, existing.status = store.id, "packing"
    new = make_order(id="ORD-2", lat=19.103, lng=72.853, promise_min=30)
    _, _, feasible = cheapest_insertion_cost(far_rider, [existing], new, store)
    assert feasible is False  # an hour of riding to even reach the store
    near_rider = make_rider(lat=19.10, lng=72.85, speed=30.0)
    assert cheapest_insertion_cost(near_rider, [existing], new, store)[2] is True


def test_same_store_batching_adds_no_second_pickup_trip(isolated_world):  # noqa: F811
    store = make_store(lat=19.10, lng=72.85)
    world.stores, world.store_by_id = [store], {store.id: store}
    rider = make_rider(lat=19.10, lng=72.85, speed=30.0)
    existing = make_order(id="ORD-1", lat=19.102, lng=72.852, promise_min=30)
    existing.store_id, existing.status = store.id, "packed"
    new = make_order(id="ORD-2", lat=19.103, lng=72.853, promise_min=30)
    _, added, feasible = cheapest_insertion_cost(rider, [existing], new, store)
    assert feasible and added < 60  # just the extra drop, not a return to the store


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
