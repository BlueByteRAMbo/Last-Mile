import pytest
from app import routing


@pytest.fixture(autouse=True)
def _clean_cache():
    routing.clear_cache()
    yield
    routing.clear_cache()


def test_polyline_progress_point_walks_multi_segment_path():
    # a right-angle path: (0,0) -> (0,1) -> (1,1) in [lng,lat] pairs
    polyline = [[0.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
    seg1_km = routing._haversine_km(0.0, 0.0, 1.0, 0.0)  # lat 0->1 at lng 0

    lat, lng = routing.polyline_progress_point(polyline, seg1_km / 2)
    assert lat == pytest.approx(0.5, abs=0.01)
    assert lng == pytest.approx(0.0, abs=0.01)


def test_polyline_progress_point_clamps_past_the_end():
    polyline = [[0.0, 0.0], [0.0, 1.0]]
    total = routing.polyline_total_km(polyline)
    lat, lng = routing.polyline_progress_point(polyline, total + 1000)
    assert lat == pytest.approx(1.0, abs=0.001)
    assert lng == pytest.approx(0.0, abs=0.001)


def test_fallback_route_is_marked_approximate():
    route = routing._fallback_route(19.10, 72.85, 19.11, 72.86)
    assert route["approximate"] is True
    assert route["distance_m"] > 0
    assert route["duration_s"] > 0
    assert len(route["polyline"]) == 2


def test_get_cached_route_returns_none_when_not_cached():
    assert routing.get_cached_route(19.10, 72.85, 19.11, 72.86) is None


async def test_ensure_route_caches_a_successful_fetch(monkeypatch):
    monkeypatch.setattr(routing, "MAPBOX_TOKEN", "fake-token-for-test")

    async def fake_fetch(lat1, lng1, lat2, lng2, alternatives=False):
        return [{"polyline": [[lng1, lat1], [lng2, lat2]], "distance_m": 1234.0, "duration_s": 99.0, "approximate": False}]

    monkeypatch.setattr(routing, "_fetch_from_mapbox", fake_fetch)

    await routing.ensure_route(19.10, 72.85, 19.11, 72.86)
    cached = routing.get_cached_route(19.10, 72.85, 19.11, 72.86)
    assert cached is not None
    assert cached["distance_m"] == 1234.0


async def test_ensure_route_falls_back_silently_on_fetch_failure(monkeypatch):
    monkeypatch.setattr(routing, "MAPBOX_TOKEN", "fake-token-for-test")

    async def failing_fetch(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(routing, "_fetch_from_mapbox", failing_fetch)

    await routing.ensure_route(19.10, 72.85, 19.11, 72.86)  # must not raise
    assert routing.get_cached_route(19.10, 72.85, 19.11, 72.86) is None  # nothing cached, caller keeps using haversine


async def test_ensure_route_is_a_noop_without_a_token(monkeypatch):
    monkeypatch.setattr(routing, "MAPBOX_TOKEN", None)
    called = False

    async def should_not_run(*a, **k):
        nonlocal called
        called = True
        return []
    monkeypatch.setattr(routing, "_fetch_from_mapbox", should_not_run)

    await routing.ensure_route(19.10, 72.85, 19.11, 72.86)
    assert called is False


async def test_fetch_alternatives_falls_back_to_haversine_on_failure(monkeypatch):
    async def failing_fetch(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(routing, "_fetch_from_mapbox", failing_fetch)

    routes = await routing.fetch_alternatives(19.10, 72.85, 19.11, 72.86)
    assert len(routes) == 1
    assert routes[0]["approximate"] is True
