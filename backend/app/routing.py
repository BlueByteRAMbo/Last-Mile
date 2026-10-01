"""Road routing via Mapbox Directions, with aggressive caching and a straight-line fallback.

Architecture constraint: the tick loop (simulator.py) must never await a network call — that's
the whole point of the Phase 0 world-state rewrite. So this module splits route-fetching into two
halves: a pure sync cache lookup (get_cached_route / get_cached_alternatives) safe to call from
tick_sync(), and an async fetch (ensure_route) that the async tick() wrapper fires as a background
task when a rider's destination changes. Until the real route lands, movement falls back to the
haversine straight line — same behavior as before this module existed, just upgraded in place
once the real polyline arrives.
"""
import os
import math
import asyncio
from collections import OrderedDict

import httpx

MAPBOX_TOKEN = os.environ.get("VITE_MAPBOX_TOKEN") or os.environ.get("MAPBOX_TOKEN")
DIRECTIONS_URL = "https://api.mapbox.com/directions/v5/mapbox/driving/{coords}"
REQUEST_TIMEOUT_SECONDS = 4.0
CACHE_MAX_SIZE = 500
COORD_PRECISION = 4  # ~11m — enough to dedupe repeated near-identical requests without big errors

_route_cache: "OrderedDict[tuple, dict]" = OrderedDict()
_in_flight: set[tuple] = set()


def _key(lat1, lng1, lat2, lng2):
    r = COORD_PRECISION
    return (round(lat1, r), round(lng1, r), round(lat2, r), round(lng2, r))


def _haversine_km(lat1, lng1, lat2, lng2):
    rad = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * rad * math.asin(math.sqrt(a))


def _fallback_route(lat1, lng1, lat2, lng2, speed_kmh=28.0) -> dict:
    distance_km = _haversine_km(lat1, lng1, lat2, lng2)
    return {
        "polyline": [[lng1, lat1], [lng2, lat2]],  # [lng, lat] pairs, matching GeoJSON/Mapbox convention
        "distance_m": round(distance_km * 1000, 1),
        "duration_s": round((distance_km / max(speed_kmh, 1)) * 3600, 1),
        "approximate": True,
    }


def get_cached_route(lat1, lng1, lat2, lng2) -> dict | None:
    """Pure sync lookup — safe to call from the tick loop. None means no real route cached yet
    (caller should use the haversine fallback for this tick and may call ensure_route to start
    fetching one in the background)."""
    return _route_cache.get(_key(lat1, lng1, lat2, lng2))


def _store(key, route):
    _route_cache[key] = route
    _route_cache.move_to_end(key)
    while len(_route_cache) > CACHE_MAX_SIZE:
        _route_cache.popitem(last=False)


async def _fetch_from_mapbox(lat1, lng1, lat2, lng2, alternatives=False) -> list[dict]:
    coords = f"{lng1},{lat1};{lng2},{lat2}"
    params = {
        "geometries": "geojson", "overview": "full", "alternatives": "true" if alternatives else "false",
        "access_token": MAPBOX_TOKEN,
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        resp = await client.get(DIRECTIONS_URL.format(coords=coords), params=params)
        resp.raise_for_status()
        data = resp.json()
    routes = data.get("routes") or []
    return [
        {"polyline": r["geometry"]["coordinates"], "distance_m": r["distance"], "duration_s": r["duration"], "approximate": False}
        for r in routes
    ]


async def ensure_route(lat1, lng1, lat2, lng2):
    """Fire-and-forget: fetch the real route for this leg if we don't already have one cached and
    aren't already fetching it. Call from the async tick() wrapper, never from tick_sync()."""
    key = _key(lat1, lng1, lat2, lng2)
    if key in _route_cache or key in _in_flight or not MAPBOX_TOKEN:
        return
    _in_flight.add(key)
    try:
        routes = await _fetch_from_mapbox(lat1, lng1, lat2, lng2)
        if routes:
            _store(key, routes[0])
    except Exception as e:
        print(f"[routing] directions fetch failed, staying on haversine fallback: {e}")
    finally:
        _in_flight.discard(key)


async def fetch_alternatives(lat1, lng1, lat2, lng2) -> list[dict]:
    """Used for the reroute-around-traffic decision (Phase 3D) — awaited directly (not fired as a
    background task) since it's only called from a disruption-response code path, not every tick."""
    try:
        routes = await _fetch_from_mapbox(lat1, lng1, lat2, lng2, alternatives=True)
        if routes:
            return routes
    except Exception as e:
        print(f"[routing] alternatives fetch failed: {e}")
    return [_fallback_route(lat1, lng1, lat2, lng2)]


def polyline_progress_point(polyline: list, progress_km: float) -> tuple[float, float]:
    """Walk a [lng, lat] polyline by cumulative distance and return the (lat, lng) at progress_km
    along it (clamped to the end). Used to move a rider along a real road path instead of a
    straight line."""
    if len(polyline) < 2:
        lng, lat = polyline[0] if polyline else (0, 0)
        return lat, lng
    remaining = progress_km
    for (lng1, lat1), (lng2, lat2) in zip(polyline, polyline[1:]):
        seg_km = _haversine_km(lat1, lng1, lat2, lng2)
        if remaining <= seg_km or seg_km == 0:
            frac = 0 if seg_km == 0 else remaining / seg_km
            frac = max(0.0, min(1.0, frac))
            return lat1 + (lat2 - lat1) * frac, lng1 + (lng2 - lng1) * frac
        remaining -= seg_km
    lng, lat = polyline[-1]
    return lat, lng


def polyline_total_km(polyline: list) -> float:
    return sum(_haversine_km(lat1, lng1, lat2, lng2)
               for (lng1, lat1), (lng2, lat2) in zip(polyline, polyline[1:]))


def clear_cache():
    _route_cache.clear()
    _in_flight.clear()
