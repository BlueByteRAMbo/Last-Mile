/**
 * FollowCamera.js
 * Manages the cinematic third-person follow camera using Mapbox FreeCamera API.
 *
 * Camera sits behind and above the rider, looking forward along the road.
 * Uses smooth exponential interpolation to avoid snapping.
 */

import mapboxgl from 'mapbox-gl';

// ─── Camera mode constants ───────────────────────────────────────────────────
export const CAMERA_MODE = {
  OVERVIEW: 'OVERVIEW',
  FOLLOW: 'FOLLOW',
  DESTINATION: 'DESTINATION',
};

// ─── Tuneable constants ───────────────────────────────────────────────────────
const FOLLOW = {
  DISTANCE_M: 28,    // metres behind rider
  HEIGHT_M: 12,      // metres above ground
  LOOK_AHEAD_M: 40,  // metres ahead to look at
};

const LERP_FACTOR = 0.08; // lower → smoother but laggier

// State kept as a plain object (not React state – lives in a ref)
let _state = {
  mode: CAMERA_MODE.OVERVIEW,
  targetLng: 72.8777,
  targetLat: 19.076,
  targetBearing: -15,
  targetAlt: 0,
};

/**
 * Convert metres offset in world space to degrees offset at a given latitude.
 */
function metresToDeg(metres, lat) {
  const latDeg = metres / 111320;
  const lngDeg = metres / (111320 * Math.cos((lat * Math.PI) / 180));
  return { latDeg, lngDeg };
}

/**
 * Compute the camera world position behind the rider.
 * @param {[number,number]} riderPos - [lng, lat]
 * @param {number} riderBearing - degrees (0 = north, clockwise)
 */
function computeCameraPosition(riderPos, riderBearing) {
  const [lng, lat] = riderPos;
  // Direction BEHIND rider = riderBearing + 180
  const behindBearingRad = ((riderBearing + 180) * Math.PI) / 180;
  const { latDeg, lngDeg } = metresToDeg(FOLLOW.DISTANCE_M, lat);

  const camLng = lng + lngDeg * Math.sin(behindBearingRad);
  const camLat = lat + latDeg * Math.cos(behindBearingRad);
  const camAlt = FOLLOW.HEIGHT_M;

  return [camLng, camLat, camAlt];
}

/**
 * Compute the look-ahead target point in front of the rider.
 */
function computeLookAhead(riderPos, riderBearing) {
  const [lng, lat] = riderPos;
  const aheadBearingRad = (riderBearing * Math.PI) / 180;
  const { latDeg, lngDeg } = metresToDeg(FOLLOW.LOOK_AHEAD_M, lat);

  return [
    lng + lngDeg * Math.sin(aheadBearingRad),
    lat + latDeg * Math.cos(aheadBearingRad),
    0,
  ];
}

/**
 * One-shot smooth transition back to the standard overview camera.
 */
export function flyToOverview(map, callback) {
  map.easeTo({
    center: [72.8777, 19.076],
    zoom: 15,
    pitch: 60,
    bearing: -15,
    duration: 2000,
    easing: t => t * (2 - t),
  });
  if (callback) setTimeout(callback, 2200);
}

/**
 * Fly to destination view when a delivery is about to happen.
 */
export function flyToDestination(map, destCoord) {
  map.easeTo({
    center: destCoord,
    zoom: 17,
    pitch: 50,
    bearing: map.getBearing(),
    duration: 1500,
  });
}

/**
 * Called every animation frame in FOLLOW mode.
 * Uses Mapbox FreeCamera API for cinematic follow.
 *
 * @param {mapboxgl.Map} map
 * @param {[number,number]} riderPos  current [lng, lat]
 * @param {number}         bearing   current rider bearing (degrees)
 */
export function updateFollowCamera(map, riderPos, bearing) {
  try {
    const camPos = computeCameraPosition(riderPos, bearing);
    const lookAt = computeLookAhead(riderPos, bearing);

    const cameraOptions = map.getFreeCameraOptions();

    // Position
    cameraOptions.position = mapboxgl.MercatorCoordinate.fromLngLat(
      { lng: camPos[0], lat: camPos[1] },
      camPos[2]  // altitude in metres
    );

    // Look at target
    cameraOptions.lookAtPoint(
      { lng: lookAt[0], lat: lookAt[1] },
      [0, 0, 1]  // up vector
    );

    map.setFreeCameraOptions(cameraOptions);
  } catch {
    // FreeCamera may not be available in all map states – fail silently
  }
}
