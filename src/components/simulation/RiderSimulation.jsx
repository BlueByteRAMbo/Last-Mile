import React, { useState, useEffect, useRef, useCallback } from 'react';
import mapboxgl from 'mapbox-gl';
import { Camera } from 'lucide-react';

import {
  simulationOrders,
  simulationRider,
  WAYPOINTS,
  BASE_SPEED_MPS,
} from '../../data/simulationData';

import {
  fetchRoute,
  buildArcLength,
  interpolateRoute,
  getBearing,
  getDistance,
} from './RouteEngine';

import {
  CAMERA_MODE,
  updateFollowCamera,
  flyToOverview,
  flyToDestination,
} from './FollowCamera';

import { initRiderModel, updateRiderPosition, removeRiderModel } from './RiderModel';

import SimulationHeader from './SimulationHeader';
import RiderStatusPanel from './RiderStatusPanel';
import DeliveryQueue from './DeliveryQueue';
import SimulationControls from './SimulationControls';
import SimulationTimeline from './SimulationTimeline';
import SimulationMetrics from './SimulationMetrics';
import SimulationEventToast from './SimulationEventToast';
import SimulationCompletion from './SimulationCompletion';
import FollowHUD from './FollowHUD';

// ─── Mapbox token ─────────────────────────────────────────────────────────────
const TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;

// ─── Layer IDs ───────────────────────────────────────────────────────────────
const SRC_REMAINING   = 'sim-route';
const SRC_COMPLETED   = 'sim-route-completed';
const LYR_REMAINING   = 'sim-route-remaining';
const LYR_COMPLETED_G = 'sim-route-completed-glow';
const LYR_COMPLETED   = 'sim-route-completed-line';

// ─── Initial UI state (route-independent) ────────────────────────────────────
const INIT_EVENTS = [
  { time: '00:00', label: 'Assigned',    active: true  },
  { time: '00:02', label: 'Picked Up',   active: true  },
  { time: '00:04', label: 'On Route',    active: true  },
  { time: '--:--', label: '#2841\nDelivered', active: false },
  { time: '--:--', label: '#2847\nDelivered', active: false },
  { time: '--:--', label: '#2853\nDelivered', active: false },
];

// ─────────────────────────────────────────────────────────────────────────────
const RiderSimulation = ({ map }) => {
  // ── Route state ────────────────────────────────────────────────────────────
  const [routeState, setRouteState] = useState({
    status: 'LOADING', // LOADING | READY | ERROR
    error: null,
    coords: [],         // full road-following coords [[lng,lat],...]
    arcLengths: [],     // cumulative arc-length km
    totalDistKm: 0,
    // Per-leg boundary t-values (0-1) where each delivery happens
    deliveryT: [],
  });

  // ── Simulation playback state ─────────────────────────────────────────────
  const [isPlaying, setIsPlaying]         = useState(false);
  const [speed, setSpeed]                 = useState(1);
  const [timeElapsed, setTimeElapsed]     = useState(0); // wall-clock seconds
  const [t, setT]                         = useState(0); // normalised route progress 0-1
  const [orders, setOrders]               = useState(JSON.parse(JSON.stringify(simulationOrders)));
  const [load, setLoad]                   = useState(3);
  const [events, setEvents]               = useState(INIT_EVENTS);
  const [toastEvent, setToastEvent]       = useState(null);
  const [completed, setCompleted]         = useState(false);
  const [statusLocation, setStatusLocation] = useState('Bandra Dark Store');
  const [etaMin, setEtaMin]               = useState('--');
  const [distKm, setDistKm]               = useState('--');

  // ── Camera state ──────────────────────────────────────────────────────────
  const [cameraMode, setCameraMode] = useState(CAMERA_MODE.OVERVIEW);

  // ── Delivery guard refs (prevent re-firing) ───────────────────────────────
  const deliveredRef   = useRef([false, false, false]);
  const trafficFiredRef = useRef(false);

  // ── Animation refs ────────────────────────────────────────────────────────
  const rafRef       = useRef();
  const lastTimeRef  = useRef();
  const tRef         = useRef(0);       // mirrors t state – accessible inside RAF
  const speedRef     = useRef(1);
  const playingRef   = useRef(false);
  const routeRef     = useRef(null);    // mirrors routeState for RAF access
  const cameraModeRef = useRef(CAMERA_MODE.OVERVIEW);

  // ── Order markers ─────────────────────────────────────────────────────────
  const orderMarkersRef = useRef([]);

  // ─────────────────────────────────────────────────────────────────────────
  // Keep refs in sync with state
  speedRef.current    = speed;
  playingRef.current  = isPlaying;
  cameraModeRef.current = cameraMode;

  // ─────────────────────────────────────────────────────────────────────────
  // 1. FETCH ROUTE ON MOUNT
  // ─────────────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!map) return;
    let cancelled = false;

    (async () => {
      try {
        const result = await fetchRoute(WAYPOINTS, TOKEN);
        if (cancelled) return;

        const coords = result.coordinates;
        const arcLengths = buildArcLength(coords);
        const totalDistKm = arcLengths[arcLengths.length - 1];

        // Find which t-value each delivery waypoint corresponds to
        // by finding the nearest coord index to each WAYPOINTS[1..3]
        const deliveryT = [1, 2, 3].map(wIdx => {
          const wp = WAYPOINTS[wIdx];
          let minDist = Infinity, minI = 0;
          coords.forEach((c, i) => {
            const d = getDistance(c, wp);
            if (d < minDist) { minDist = d; minI = i; }
          });
          return arcLengths[minI] / totalDistKm;
        });

        const rs = { status: 'READY', error: null, coords, arcLengths, totalDistKm, deliveryT };
        setRouteState(rs);
        routeRef.current = rs;

        setDistKm(totalDistKm.toFixed(1));
        setEtaMin(Math.round(result.duration / 60).toString());

        // Draw map layers
        setupMapLayers(map, coords);
        // Place order markers at real dest coords
        setupOrderMarkers(map);
        // Init rider model/marker
        await initRiderModel(map, coords[0]);

        // Fly camera to start
        map.flyTo({
          center: coords[0],
          zoom: 15,
          pitch: 60,
          bearing: -20,
          speed: 1.4,
          essential: true,
        });
      } catch (err) {
        if (!cancelled) {
          setRouteState({ status: 'ERROR', error: err.message, coords: [], arcLengths: [], totalDistKm: 0, deliveryT: [] });
        }
      }
    })();

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);

  // ─────────────────────────────────────────────────────────────────────────
  // 2. SETUP MAP LAYERS
  // ─────────────────────────────────────────────────────────────────────────
  function setupMapLayers(m, coords) {
    if (!m.getSource(SRC_REMAINING)) {
      m.addSource(SRC_REMAINING, {
        type: 'geojson',
        data: { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: coords } },
      });
      m.addLayer({
        id: LYR_REMAINING, type: 'line', source: SRC_REMAINING,
        paint: { 'line-color': '#2d3748', 'line-width': 4, 'line-dasharray': [2, 2] },
      });
    }

    if (!m.getSource(SRC_COMPLETED)) {
      m.addSource(SRC_COMPLETED, {
        type: 'geojson',
        data: { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: [coords[0]] } },
      });
      m.addLayer({
        id: LYR_COMPLETED_G, type: 'line', source: SRC_COMPLETED,
        paint: { 'line-color': '#38BDF8', 'line-width': 10, 'line-opacity': 0.25, 'line-blur': 4 },
      });
      m.addLayer({
        id: LYR_COMPLETED, type: 'line', source: SRC_COMPLETED,
        paint: { 'line-color': '#38BDF8', 'line-width': 3, 'line-opacity': 0.9 },
      });
    }
  }

  function setupOrderMarkers(m) {
    orderMarkersRef.current.forEach(o => o.marker.remove());
    orderMarkersRef.current = [];

    simulationOrders.forEach(order => {
      const el = document.createElement('div');
      el.style.cssText = `
        width:14px; height:14px; border-radius:2px; background:#1e293b;
        border:2px solid #64748b; transform:rotate(45deg);
        display:flex; align-items:center; justify-content:center; cursor:default;
      `;
      el.innerHTML = `<div style="width:5px;height:5px;background:#64748b;border-radius:50%"></div>`;

      const marker = new mapboxgl.Marker({ element: el }).setLngLat(order.dest).addTo(m);
      orderMarkersRef.current.push({ id: order.id, marker, el });
    });
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 3. ANIMATION LOOP
  // ─────────────────────────────────────────────────────────────────────────
  const animate = useCallback((now) => {
    if (!playingRef.current) return;
    if (!routeRef.current || routeRef.current.status !== 'READY') return;

    if (!lastTimeRef.current) lastTimeRef.current = now;
    const deltaS = (now - lastTimeRef.current) / 1000;
    lastTimeRef.current = now;

    const { coords, arcLengths, totalDistKm, deliveryT } = routeRef.current;
    const totalDistM = totalDistKm * 1000;
    // Advance rider by BASE_SPEED * speed * delta metres
    const advanceM = BASE_SPEED_MPS * speedRef.current * deltaS;
    const newT = Math.min(1, tRef.current + advanceM / totalDistM);
    tRef.current = newT;

    const { position, bearing, segmentIndex } = interpolateRoute(coords, arcLengths, newT);

    // ── Update rider model ──────────────────────────────────────────────
    updateRiderPosition(map, position, bearing);

    // ── Update completed route ──────────────────────────────────────────
    const completedCoords = [...coords.slice(0, segmentIndex + 1), position];
    if (map.getSource(SRC_COMPLETED)) {
      map.getSource(SRC_COMPLETED).setData({
        type: 'Feature', geometry: { type: 'LineString', coordinates: completedCoords },
      });
    }

    // ── Update follow camera ────────────────────────────────────────────
    if (cameraModeRef.current === CAMERA_MODE.FOLLOW) {
      updateFollowCamera(map, position, bearing);
    }

    // ── Update React state (throttled) ─────────────────────────────────
    const remainDistKm = totalDistKm * (1 - newT);
    const remainTimeMin = Math.max(0, Math.round((remainDistKm * 1000) / BASE_SPEED_MPS / 60));

    setT(newT);
    setTimeElapsed(prev => prev + deltaS);
    setDistKm(remainDistKm.toFixed(1));
    setEtaMin(remainTimeMin.toString());

    // ── Delivery events ─────────────────────────────────────────────────
    deliveryT.forEach((dT, idx) => {
      if (newT >= dT && !deliveredRef.current[idx]) {
        deliveredRef.current[idx] = true;
        handleDelivery(idx, now);
      }
    });

    // ── Traffic event at ~55% ─────────────────────────────────────────
    if (newT >= 0.55 && !trafficFiredRef.current) {
      trafficFiredRef.current = true;
      fireTrafficEvent(position);
    }

    // ── Completion ─────────────────────────────────────────────────────
    if (newT >= 1 && !deliveredRef.current[2]) {
      deliveredRef.current[2] = true;
      handleDelivery(2, now);
    }
    if (newT >= 1) {
      setCompleted(true);
      setIsPlaying(false);
      playingRef.current = false;
      if (cameraModeRef.current === CAMERA_MODE.FOLLOW) {
        flyToOverview(map, () => setCameraMode(CAMERA_MODE.OVERVIEW));
      }
      return;
    }

    rafRef.current = requestAnimationFrame(animate);
  }, [map]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (isPlaying) {
      lastTimeRef.current = null;
      rafRef.current = requestAnimationFrame(animate);
    } else {
      cancelAnimationFrame(rafRef.current);
    }
    return () => cancelAnimationFrame(rafRef.current);
  }, [isPlaying, animate]);

  // ─────────────────────────────────────────────────────────────────────────
  // 4. EVENT HANDLERS
  // ─────────────────────────────────────────────────────────────────────────
  const formatTime = secs => {
    const m = Math.floor(secs / 60).toString().padStart(2, '0');
    const s = Math.floor(secs % 60).toString().padStart(2, '0');
    return `00:${m}:${s}`;
  };

  function handleDelivery(idx, now) {
    const labels = ['Bandra West', 'Khar West', 'Santacruz West'];
    const names  = ['#2841', '#2847', '#2853'];

    setOrders(prev => {
      const next = [...prev];
      next[idx] = { ...next[idx], status: 'DELIVERED' };
      if (idx + 1 < next.length) next[idx + 1] = { ...next[idx + 1], status: 'CURRENT' };
      return next;
    });
    setLoad(prev => Math.max(0, prev - 1));
    setStatusLocation(labels[idx]);
    setEvents(prev => {
      const next = [...prev];
      next[idx + 3] = { time: formatTime(timeElapsed), label: `${names[idx]}\nDelivered`, active: true };
      return next;
    });

    // Marker style
    const m = orderMarkersRef.current[idx];
    if (m?.el) {
      m.el.style.background = '#34D399';
      m.el.style.borderColor = '#059669';
      m.el.innerHTML = `<div style="width:5px;height:5px;background:#fff;border-radius:50%"></div>`;
    }

    // Destination camera on last delivery
    if (idx === 2 && map) {
      flyToDestination(map, WAYPOINTS[3]);
    }
  }

  function fireTrafficEvent(currentPos) {
    setToastEvent({
      type: 'TRAFFIC',
      title: 'TRAFFIC DETECTED',
      message: 'Western Express Highway',
      detail: '+2 min predicted delay',
    });

    // After 4 seconds – show optimized route toast
    setTimeout(() => {
      setToastEvent({
        type: 'OPTIMIZE',
        title: 'ROUTE OPTIMIZED',
        message: 'Detour engaged via Linking Rd',
        detail: 'ETA SAVED 3 min',
      });
    }, 4000);
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 5. AUTO CLEAR TOAST
  // ─────────────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!toastEvent) return;
    const id = setTimeout(() => setToastEvent(null), 5500);
    return () => clearTimeout(id);
  }, [toastEvent]);

  // ─────────────────────────────────────────────────────────────────────────
  // 6. CAMERA MODE TOGGLE
  // ─────────────────────────────────────────────────────────────────────────
  const handleFollowRider = () => {
    if (cameraMode === CAMERA_MODE.FOLLOW) {
      setCameraMode(CAMERA_MODE.OVERVIEW);
      flyToOverview(map);
    } else {
      setCameraMode(CAMERA_MODE.FOLLOW);
      // Don't call flyTo here – the next animation frame will use FreeCamera
    }
  };

  const handleExitFollow = () => {
    setCameraMode(CAMERA_MODE.OVERVIEW);
    flyToOverview(map);
  };

  // ─────────────────────────────────────────────────────────────────────────
  // 7. RESTART
  // ─────────────────────────────────────────────────────────────────────────
  const handleRestart = () => {
    cancelAnimationFrame(rafRef.current);
    setIsPlaying(false);
    setT(0);
    tRef.current = 0;
    setTimeElapsed(0);
    setCompleted(false);
    setOrders(JSON.parse(JSON.stringify(simulationOrders)));
    setLoad(3);
    setEvents(INIT_EVENTS);
    setToastEvent(null);
    setStatusLocation('Bandra Dark Store');
    deliveredRef.current = [false, false, false];
    trafficFiredRef.current = false;
    lastTimeRef.current = null;
    setCameraMode(CAMERA_MODE.OVERVIEW);

    if (map && routeRef.current?.coords) {
      const c = routeRef.current.coords;
      updateRiderPosition(map, c[0], 0);
      if (map.getSource(SRC_COMPLETED)) {
        map.getSource(SRC_COMPLETED).setData({ type: 'Feature', geometry: { type: 'LineString', coordinates: [c[0]] } });
      }
      flyToOverview(map);
    }

    orderMarkersRef.current.forEach((m, idx) => {
      if (m?.el) {
        m.el.style.background = '#1e293b';
        m.el.style.borderColor = '#64748b';
        m.el.innerHTML = `<div style="width:5px;height:5px;background:#64748b;border-radius:50%"></div>`;
      }
    });
  };

  // ─────────────────────────────────────────────────────────────────────────
  // 8. CLEANUP ON UNMOUNT
  // ─────────────────────────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      cancelAnimationFrame(rafRef.current);
      if (map) {
        removeRiderModel(map);
        [LYR_COMPLETED, LYR_COMPLETED_G, LYR_REMAINING].forEach(l => { if (map.getLayer(l)) map.removeLayer(l); });
        [SRC_REMAINING, SRC_COMPLETED].forEach(s => { if (map.getSource(s)) map.removeSource(s); });
        orderMarkersRef.current.forEach(o => o?.marker?.remove());
      }
    };
  }, [map]);

  // ─────────────────────────────────────────────────────────────────────────
  // 9. RENDER
  // ─────────────────────────────────────────────────────────────────────────
  const isFollow = cameraMode === CAMERA_MODE.FOLLOW;

  if (routeState.status === 'LOADING') {
    return (
      <div className="absolute inset-0 z-20 flex items-center justify-center pointer-events-none">
        <div className="bg-route-panel/95 backdrop-blur-md border border-white/10 rounded-lg px-8 py-6 flex flex-col items-center gap-4">
          <div className="w-8 h-8 rounded-full border-2 border-route-cyan border-t-transparent animate-spin"></div>
          <div className="text-sm font-medium text-slate-300">Fetching road route…</div>
          <div className="text-xs text-slate-500">Connecting to Mapbox Directions API</div>
        </div>
      </div>
    );
  }

  if (routeState.status === 'ERROR') {
    return (
      <div className="absolute inset-0 z-20 flex items-center justify-center pointer-events-none">
        <div className="bg-route-panel/95 backdrop-blur-md border border-route-red/30 rounded-lg px-8 py-6 flex flex-col items-center gap-4 text-center max-w-sm pointer-events-auto">
          <div className="w-10 h-10 rounded-full bg-route-red/20 border border-route-red/40 flex items-center justify-center text-route-red text-xl font-bold">!</div>
          <div className="text-sm font-bold text-route-red">Route Fetch Failed</div>
          <div className="text-xs text-slate-400">{routeState.error}</div>
          <div className="text-xs text-slate-500">Check your Mapbox token and network connection.<br/>Simulation is paused.</div>
        </div>
      </div>
    );
  }

  const metrics = {
    eta: `${etaMin}m`,
    distanceRemaining: distKm,
    ordersCompleted: deliveredRef.current.filter(Boolean).length,
    totalOrders: 3,
    speed: Math.round(BASE_SPEED_MPS * speed * 3.6), // to km/h
  };

  return (
    <div className="absolute inset-0 pointer-events-none z-10">

      {/* ── Follow Camera HUD (shown only in follow mode) ── */}
      {isFollow ? (
        <>
          <FollowHUD
            rider={simulationRider}
            eta={etaMin}
            speed={metrics.speed}
            distKm={distKm}
          />
          <button
            onClick={handleExitFollow}
            className="absolute bottom-28 right-6 z-20 pointer-events-auto
              bg-route-panel/90 backdrop-blur-md border border-white/10
              text-slate-300 hover:text-white text-xs font-bold tracking-wider
              px-4 py-2.5 rounded-lg transition-colors"
          >
            EXIT FOLLOW
          </button>
        </>
      ) : (
        <>
          {/* ── Normal Dashboard UI ── */}
          <SimulationHeader
            rider={simulationRider}
            isPlaying={isPlaying && !completed}
            timeElapsed={timeElapsed}
          />

          <SimulationMetrics state={metrics} />

          <SimulationEventToast event={toastEvent} />

          <RiderStatusPanel
            rider={simulationRider}
            state={{
              currentLocation: statusLocation,
              speed: metrics.speed,
              currentLoad: load,
              eta: `${etaMin}m`,
              progress: Math.round(t * 100),
              distanceRemaining: `${distKm} km`,
            }}
          />

          <DeliveryQueue orders={orders} />

          <SimulationTimeline events={events} />
        </>
      )}

      {/* ── Controls (always visible) ── */}
      <div className="absolute bottom-6 right-[350px] z-10 pointer-events-auto flex items-center gap-3">
        {/* Follow Camera toggle button */}
        {!isFollow && (
          <button
            onClick={handleFollowRider}
            disabled={routeState.status !== 'READY'}
            className="flex items-center gap-2 bg-route-panel/95 backdrop-blur-md border border-white/10
              text-slate-300 hover:text-white text-xs font-bold tracking-wider
              px-4 py-3 rounded-full transition-colors disabled:opacity-40"
          >
            <Camera size={14} />
            FOLLOW RIDER
          </button>
        )}
      </div>

      <SimulationControls
        isPlaying={isPlaying}
        onTogglePlay={() => routeState.status === 'READY' && !completed && setIsPlaying(p => !p)}
        onRestart={handleRestart}
        speed={speed}
        onSpeedChange={s => setSpeed(s)}
        isComplete={completed}
      />

      {completed && (
        <SimulationCompletion
          stats={{
            time: formatTime(timeElapsed),
            distance: routeState.totalDistKm.toFixed(1),
          }}
          onRestart={handleRestart}
        />
      )}
    </div>
  );
};

export default RiderSimulation;
