import datetime as dt
import pytest
from app.dispatch import (
    add_traffic_zone, clear_traffic_zones, traffic_multiplier_for_leg,
    riders_affected_by_zone, travel_seconds,
)
from .conftest import make_store, make_rider, make_order

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _clean_zones():
    clear_traffic_zones()
    yield
    clear_traffic_zones()


async def test_zone_slows_a_leg_that_passes_through_it():
    # Andheri Hub (19.1136, 72.8697) -> a point ~5km south, straight line passes near the hub itself
    zone = add_traffic_zone(19.1136, 72.8697, radius_km=2.0, multiplier=0.3, duration_minutes=5)
    fast = travel_seconds(19.1136, 72.8697, 19.07, 72.8697, speed_kmh=30)
    clear_traffic_zones()
    normal = travel_seconds(19.1136, 72.8697, 19.07, 72.8697, speed_kmh=30)
    assert fast > normal  # slower (more seconds) while the zone is active


async def test_zone_does_not_affect_a_distant_leg():
    add_traffic_zone(19.1136, 72.8697, radius_km=1.0, multiplier=0.3, duration_minutes=5)
    mult = traffic_multiplier_for_leg(18.90, 72.70, 18.91, 72.71)  # far from the zone
    assert mult == 1.0


async def test_expired_zone_has_no_effect():
    zone = add_traffic_zone(19.1136, 72.8697, radius_km=5.0, multiplier=0.1, duration_minutes=5)
    zone["expires_at"] = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)  # force expiry
    mult = traffic_multiplier_for_leg(19.1136, 72.8697, 19.12, 72.87)
    assert mult == 1.0


async def test_riders_affected_by_zone_detects_route_intersection(session):
    store = make_store(lat=19.10, lng=72.85)
    rider_through = make_rider(id="RX-THROUGH", lat=19.10, lng=72.85)
    rider_away = make_rider(id="RX-AWAY", lat=10.0, lng=70.0)
    session.add_all([store, rider_through, rider_away])
    order_near = make_order(id="ORD-NEAR", lat=19.10, lng=72.87)  # just east of the rider, inside the zone path
    order_far = make_order(id="ORD-FAR", lat=10.01, lng=70.01)
    session.add_all([order_near, order_far])
    await session.flush()
    order_near.rider_id = "RX-THROUGH"
    order_near.status = "out_for_delivery"
    order_far.rider_id = "RX-AWAY"
    order_far.status = "out_for_delivery"

    zone = add_traffic_zone(19.10, 72.86, radius_km=2.0, multiplier=0.4, duration_minutes=5)
    affected = await riders_affected_by_zone(session, zone)

    assert "RX-THROUGH" in affected
    assert "RX-AWAY" not in affected
