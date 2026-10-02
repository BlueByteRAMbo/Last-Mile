import datetime as dt
import pytest


async def test_traffic_on_road_detour_affects_rider_even_outside_direct_line():
    from app import routing
    from app.dispatch import riders_affected_by_zone_sync
    from .conftest import make_rider, make_order
    rider = make_rider(lat=19, lng=72.8)
    rider.nav_origin_lat, rider.nav_origin_lng = 19, 72.8
    rider.nav_target_lat, rider.nav_target_lng = 19, 72.82
    points = [[72.8, 19], [72.81, 19.02], [72.82, 19]]
    routing._store(routing._key(19, 72.8, 19, 72.82), {'polyline': points, 'approximate': False})
    order = make_order(lat=19, lng=72.82)
    order.rider_id, order.status = rider.id, 'out_for_delivery'
    try:
        affected = riders_affected_by_zone_sync({'lat': 19.02, 'lng': 72.81, 'radius_km': .1}, [rider], [order])
        assert affected == [rider.id]
    finally:
        routing.clear_cache()
from app.dispatch import (
    add_traffic_zone, clear_traffic_zones, traffic_multiplier_for_leg,
    travel_seconds,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _clean_zones():
    clear_traffic_zones()
    yield
    clear_traffic_zones()


async def test_zone_slows_a_leg_that_passes_through_it():
    # Andheri Hub (19.1136, 72.8697) -> a point ~5km south, straight line passes near the hub itself
    add_traffic_zone(19.1136, 72.8697, radius_km=2.0, multiplier=0.3, duration_minutes=5)
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
