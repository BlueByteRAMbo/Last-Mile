import datetime as dt
import pytest
from app.simulator import advance_packing, move_riders
from app.world import world
from app import routing
from .conftest import make_store, make_rider, make_order, utcnow


@pytest.fixture(autouse=True)
def _clean_world():
    world.stores = []
    world.store_by_id = {}
    routing.clear_cache()
    yield
    world.stores = []
    world.store_by_id = {}
    routing.clear_cache()


def test_packing_queue_prioritizes_priority_then_risk_over_fifo():
    store = make_store(packing_capacity=1, packing_seconds=9999)  # only 1 slot, nothing completes mid-test
    world.stores = [store]

    old_fifo = make_order(id="ORD-OLD", promise_min=30)
    risky = make_order(id="ORD-RISKY", promise_min=30)
    urgent = make_order(id="ORD-URGENT", priority=True, promise_min=30)

    now = utcnow()
    for i, o in enumerate([old_fifo, risky, urgent]):
        o.store_id = store.id
        o.status = "assigned"
        o.assigned_at = now - dt.timedelta(seconds=30 - i)  # old_fifo assigned first
    risky.risk = "SEVERE"

    advance_packing([old_fifo, risky, urgent])

    packing = [o for o in [old_fifo, risky, urgent] if o.status == "packing"]
    assert len(packing) == 1
    # priority beats an older FIFO order and a merely-at-risk one, even though it was assigned last
    assert packing[0].id == "ORD-URGENT"


def test_packing_queue_falls_back_to_risk_then_fifo_without_priority():
    store = make_store(packing_capacity=1, packing_seconds=9999)
    world.stores = [store]

    old_fifo = make_order(id="ORD-OLD2", promise_min=30)
    risky = make_order(id="ORD-RISKY2", promise_min=30)

    now = utcnow()
    old_fifo.store_id = store.id
    old_fifo.status = "assigned"
    old_fifo.assigned_at = now - dt.timedelta(seconds=30)
    risky.store_id = store.id
    risky.status = "assigned"
    risky.assigned_at = now - dt.timedelta(seconds=5)  # assigned later than old_fifo
    risky.risk = "DELAYED"

    advance_packing([old_fifo, risky])

    packing = [o for o in [old_fifo, risky] if o.status == "packing"]
    assert len(packing) == 1
    # no priority orders here -> worse risk still jumps the older FIFO order
    assert packing[0].id == "ORD-RISKY2"


def test_move_riders_falls_back_to_straight_line_without_a_cached_route():
    rider = make_rider(lat=19.00, lng=72.80, speed=2000.0)  # fast enough to arrive this one tick
    world.riders = [rider]
    order = make_order(lat=19.00, lng=72.81)  # ~1km east
    order.rider_id = rider.id
    order.status = "out_for_delivery"
    order.route_seq = 0

    assert rider.nav_target_lat is None  # no leg started yet

    move_riders([order])

    assert rider.nav_origin_lat == pytest.approx(19.00)
    assert order.status == "delivered"  # fast rider covers the ~1km fallback straight line in one tick


def test_move_riders_follows_a_cached_real_polyline_not_a_straight_line():
    rider = make_rider(lat=19.00, lng=72.80, speed=18.0)  # slow — only covers part of the leg this tick
    world.riders = [rider]
    order = make_order(lat=19.02, lng=72.80)  # straight-line would go due north
    order.rider_id = rider.id
    order.status = "out_for_delivery"
    order.route_seq = 0

    # the "real" route detours east first, unlike the straight-line fallback
    routing._store(routing._key(19.00, 72.80, 19.02, 72.80), {
        "polyline": [[72.80, 19.00], [72.83, 19.01], [72.80, 19.02]],
        "distance_m": routing.polyline_total_km([[72.80, 19.00], [72.83, 19.01], [72.80, 19.02]]) * 1000,
        "duration_s": 999, "approximate": False,
    })

    move_riders([order])

    # after one (slow) tick the rider should have drifted east along the detour; a straight-line
    # path to a due-north destination would keep lng essentially unchanged
    assert rider.lng > 72.80 + 0.00001
    assert order.status == "out_for_delivery"  # hasn't arrived yet


def test_move_riders_resets_nav_state_on_arrival():
    rider = make_rider(lat=19.00, lng=72.80, speed=360.0)
    world.riders = [rider]
    order = make_order(lat=19.001, lng=72.801)
    order.rider_id = rider.id
    order.status = "out_for_delivery"
    order.route_seq = 0

    move_riders([order])

    assert order.status == "delivered"
    assert rider.nav_target_lat is None  # cleared so the next assignment starts a fresh leg
