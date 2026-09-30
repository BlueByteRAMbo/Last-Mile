/**
 * RouteEngine.js
 * Handles fetching real road-following routes via Mapbox Directions API.
 * Structured so the fetch call can later be replaced with a real backend.
 */

const DIRECTIONS_BASE = 'https://api.mapbox.com/directions/v5/mapbox/driving';

/**
 * Fetch a driving route between ordered waypoints.
 * Returns the full decoded GeoJSON coordinate array.
 * @param {Array<[number,number]>} waypoints - [[lng,lat], ...]
 * @param {string} token - Mapbox access token
 * @returns {Promise<{coordinates: Array<[number,number]>, distance: number, duration: number}>}
 */
export async function fetchRoute(waypoints, token) {
  const coords = waypoints.map(([lng, lat]) => `${lng},${lat}`).join(';');
  const url =
    `${DIRECTIONS_BASE}/${coords}` +
    `?access_token=${token}` +
    `&geometries=geojson` +
    `&overview=full` +
    `&steps=false`;

  const res = await fetch(url);
  if (!res.ok) throw new Error(`Directions API error: ${res.status}`);

  const data = await res.json();
  if (!data.routes || data.routes.length === 0) {
    throw new Error('No routes returned by Directions API');
  }

  const route = data.routes[0];
  return {
    coordinates: route.geometry.coordinates, // [[lng,lat], ...]
    distance: route.distance, // metres
    duration: route.duration, // seconds
  };
}

/**
 * Calculate bearing in degrees (0-360) from one coordinate to another.
 */
export function getBearing(from, to) {
  const [lon1, lat1] = from.map(d => (d * Math.PI) / 180);
  const [lon2, lat2] = to.map(d => (d * Math.PI) / 180);
  const dLon = lon2 - lon1;
  const y = Math.sin(dLon) * Math.cos(lat2);
  const x =
    Math.cos(lat1) * Math.sin(lat2) -
    Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
  const bearing = (Math.atan2(y, x) * 180) / Math.PI;
  return (bearing + 360) % 360;
}

/**
 * Calculate distance between two [lng,lat] coordinates in km.
 */
export function getDistance(coord1, coord2) {
  const [lon1, lat1] = coord1;
  const [lon2, lat2] = coord2;
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/**
 * Get cumulative arc-length array for a coordinate path.
 */
export function buildArcLength(coords) {
  const arcs = [0];
  for (let i = 1; i < coords.length; i++) {
    arcs.push(arcs[i - 1] + getDistance(coords[i - 1], coords[i]));
  }
  return arcs; // km
}

/**
 * Interpolate a position along a route given a normalised t [0,1].
 * Returns {position: [lng,lat], bearing, segmentIndex}
 */
export function interpolateRoute(coords, arcLengths, t) {
  const totalLen = arcLengths[arcLengths.length - 1];
  const target = Math.min(t, 1) * totalLen;

  let i = 0;
  while (i < arcLengths.length - 1 && arcLengths[i + 1] < target) i++;

  if (i >= coords.length - 1) {
    return {
      position: coords[coords.length - 1],
      bearing: getBearing(
        coords[coords.length - 2],
        coords[coords.length - 1]
      ),
      segmentIndex: coords.length - 1,
    };
  }

  const segStart = arcLengths[i];
  const segEnd = arcLengths[i + 1];
  const segLen = segEnd - segStart;
  const localT = segLen === 0 ? 0 : (target - segStart) / segLen;

  const a = coords[i];
  const b = coords[i + 1];
  const position = [
    a[0] + (b[0] - a[0]) * localT,
    a[1] + (b[1] - a[1]) * localT,
  ];

  return {
    position,
    bearing: getBearing(a, b),
    segmentIndex: i,
  };
}
