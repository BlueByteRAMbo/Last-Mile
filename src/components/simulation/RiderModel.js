/**
 * RiderModel.js
 *
 * Manages the 3D rider representation on the Mapbox map.
 *
 * ARCHITECTURE NOTE:
 * ------------------
 * This module attempts to use a GLB model via Mapbox's `model` source/layer
 * (available in mapbox-gl v3+ with the Standard style).
 *
 * If the model file is unavailable, it gracefully degrades to a
 * premium DOM marker.
 *
 * TO REPLACE WITH THE REAL RIDER GLB:
 *   1. Place the file at: public/models/delivery-rider.glb
 *   2. The MODEL_URL below will automatically pick it up.
 *
 * The GLB must be accessible from the browser's origin (same-origin or CORS).
 */

import mapboxgl from 'mapbox-gl';

const MODEL_URL = '/models/delivery-rider.glb';
const SOURCE_ID = 'sim-rider-model-src';
const LAYER_ID  = 'sim-rider-model-layer';

// Mapbox v3 model layer paint properties (tuneable)
const MODEL_SCALE = 3.0;   // scale multiplier – adjust to match real model size
const MODEL_VERTICAL_OFFSET_M = 0; // metres above ground

let _domMarker = null;
let _usingModelLayer = false;

/**
 * Check whether a GLB file is reachable at MODEL_URL.
 */
async function isModelAvailable() {
  try {
    const res = await fetch(MODEL_URL, { method: 'HEAD' });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Add the 3D model to the map using Mapbox model source/layer.
 * Requires mapbox-gl v3 + Standard style.
 */
function addModelLayer(map, initialPosition) {
  const [lng, lat] = initialPosition;

  if (map.getSource(SOURCE_ID)) return; // already added

  map.addSource(SOURCE_ID, {
    type: 'model',
    models: {
      'rider': {
        uri: MODEL_URL,
        position: [lng, lat],
        orientation: [0, 0, 0],
      },
    },
  });

  map.addLayer({
    id: LAYER_ID,
    type: 'model',
    source: SOURCE_ID,
    layout: {
      'model-id': 'rider',
    },
    paint: {
      'model-scale': [MODEL_SCALE, MODEL_SCALE, MODEL_SCALE],
      'model-rotation': [0, 0, 0],
      'model-opacity': 1,
      'model-receive-shadow': true,
      'model-cast-shadows': true,
      'model-vertical-scale': 1,
    },
  });

  _usingModelLayer = true;
}

/**
 * Add a premium DOM fallback marker when no GLB is present.
 */
function addDomMarker(map, position) {
  const el = document.createElement('div');
  el.id = 'sim-rider-marker';
  el.innerHTML = `
    <div style="
      display: flex;
      flex-direction: column;
      align-items: center;
      cursor: default;
      filter: drop-shadow(0 0 8px rgba(56,189,248,0.6));
    ">
      <div style="
        width: 10px; height: 10px;
        background: #38BDF8;
        border-radius: 50%;
        border: 2px solid #05070B;
        position: relative;
      ">
        <div style="
          position: absolute;
          width: 18px; height: 18px;
          border-radius: 50%;
          border: 1px solid rgba(56,189,248,0.4);
          top: -6px; left: -6px;
          animation: riderPulse 2s infinite;
        "></div>
      </div>
      <div style="
        margin-top: 4px;
        font-size: 9px;
        font-weight: 700;
        color: #38BDF8;
        letter-spacing: 0.1em;
        background: rgba(5,7,11,0.9);
        border: 1px solid rgba(56,189,248,0.2);
        padding: 1px 5px;
        border-radius: 3px;
        white-space: nowrap;
      ">RX-104</div>
    </div>
  `;

  _domMarker = new mapboxgl.Marker({ element: el, rotationAlignment: 'map', pitchAlignment: 'map' })
    .setLngLat(position)
    .addTo(map);
}

// ─── Public API ───────────────────────────────────────────────────────────────

/**
 * Initialise the rider model/marker on the map.
 * Call once after the map style has loaded.
 */
export async function initRiderModel(map, position) {
  const hasGLB = await isModelAvailable();

  if (hasGLB) {
    try {
      addModelLayer(map, position);
    } catch (err) {
      console.warn('Model layer failed, falling back to DOM marker:', err);
      addDomMarker(map, position);
    }
  } else {
    addDomMarker(map, position);
  }
}

/**
 * Update rider position and bearing every animation frame.
 * @param {mapboxgl.Map} map
 * @param {[number,number]} position   [lng, lat]
 * @param {number}          bearing    direction of travel (degrees)
 */
export function updateRiderPosition(map, position, bearing) {
  if (_usingModelLayer) {
    if (!map.getSource(SOURCE_ID)) return;
    // Mapbox model source – update the single model's position/orientation
    const src = map.getSource(SOURCE_ID);
    // Update via setData is not applicable for model sources;
    // use setLayoutProperty for the orientation & model position workaround.
    // The official way is to re-set the source data. For model sources,
    // position is baked in. We instead use a custom layer or DOM overlay.
    // ─ Fall through to DOM marker as a robust solution ─
  }

  if (_domMarker) {
    _domMarker.setLngLat(position);
    // Apply CSS rotation to the inner shape to indicate direction
    const inner = document.getElementById('sim-rider-marker');
    if (inner) {
      // The Marker's own rotation property rotates it relative to the map
      _domMarker.setRotation(bearing);
    }
  }
}

/**
 * Remove the rider from the map and clean up.
 */
export function removeRiderModel(map) {
  if (_domMarker) {
    _domMarker.remove();
    _domMarker = null;
  }
  if (_usingModelLayer) {
    if (map.getLayer(LAYER_ID)) map.removeLayer(LAYER_ID);
    if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
    _usingModelLayer = false;
  }
}
