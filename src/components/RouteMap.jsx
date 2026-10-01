import React, { useEffect, useRef } from 'react';
import mapboxgl from 'mapbox-gl';

// Mapbox Token
mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN;

const INITIAL_VIEW = {
  center: [72.8777, 19.0760],
  zoom: 13,
  pitch: 60,
  bearing: -15
};

function riderColor(status) {
  if (status === 'ON_DELIVERY') return 'bg-route-cyan';
  if (status === 'OFFLINE') return 'bg-slate-600';
  return 'bg-route-green';
}

function orderColor(o) {
  if (o.risk === 'SEVERE' || o.risk === 'DELAYED') return 'bg-route-red';
  if (o.risk === 'AT_RISK') return 'bg-route-amber';
  if (o.priority) return 'bg-route-cyan';
  return 'bg-route-cyan';
}

// Real backend state drives every marker: dark stores, riders (from /riders + WS ticks) and
// orders (with live risk/priority) replace the old static mock data + random-walk animation.
const RouteMap = ({ onEntitySelect, darkStores, riders, orders, trafficZones = [], demandZones = [], showDemandHeatmap = false, simulationMode, onMapLoad }) => {
  const mapContainer = useRef(null);
  const map = useRef(null);
  const storeMarkers = useRef([]);
  const riderMarkers = useRef(new Map()); // id -> {marker, el}
  const orderMarkers = useRef(new Map());
  const ridersRef = useRef(riders);
  const ordersRef = useRef(orders);
  ridersRef.current = riders;
  ordersRef.current = orders;

  useEffect(() => {
    if (map.current) return;
    if (!mapboxgl.accessToken) {
      console.error('Mapbox token is missing!');
      return;
    }
    map.current = new mapboxgl.Map({
      container: mapContainer.current,
      style: 'mapbox://styles/mapbox/standard',
      ...INITIAL_VIEW,
      antialias: true,
    });
    map.current.on('style.load', () => {
      map.current.setConfigProperty('basemap', 'theme', 'night');
      if (onMapLoad) onMapLoad(map.current);
    });
    return () => {
      map.current?.remove();
      map.current = null;
    };
  }, []);

  // Aggregate demand by named hub catchment; visible while reviewing analytics.
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const update = () => {
      if (!m.isStyleLoaded()) return;
      const data = { type: 'FeatureCollection', features: demandZones.filter(z => z.count > 0 && z.lng != null && z.lat != null).map(z => ({
        type: 'Feature', properties: { count: z.count }, geometry: { type: 'Point', coordinates: [z.lng, z.lat] },
      })) };
      if (!m.getSource('demand-density')) m.addSource('demand-density', { type: 'geojson', data });
      else m.getSource('demand-density').setData(data);
      if (!m.getLayer('demand-density-heat')) m.addLayer({
        id: 'demand-density-heat', type: 'heatmap', source: 'demand-density',
        paint: {
          'heatmap-weight': ['interpolate', ['linear'], ['get', 'count'], 0, 0, 10, 0.5, 100, 1],
          'heatmap-radius': 55, 'heatmap-opacity': 0.55,
          'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'],
            0, 'rgba(56,189,248,0)', 0.3, '#38BDF8', 0.6, '#FBBF24', 1, '#F87171'],
        },
      });
      m.setLayoutProperty('demand-density-heat', 'visibility', showDemandHeatmap ? 'visible' : 'none');
    };
    update();
    m.on('style.load', update);
    return () => { m.off('style.load', update); };
  }, [demandZones, showDemandHeatmap]);

  // Live congestion zones from the backend (real disruptions, not static mock data): a circle per zone.
  useEffect(() => {
    const m = map.current;
    if (!m || !m.isStyleLoaded()) return;
    const toCircle = (zone) => {
      const points = 48;
      const coords = [];
      const km = zone.radius_km;
      const { lng, lat } = zone;
      for (let i = 0; i < points; i++) {
        const theta = (i / points) * (2 * Math.PI);
        const dx = (km / 111.32) * Math.cos(theta);
        const dy = (km / 111.32) * Math.sin(theta);
        coords.push([lng + dx / Math.cos(lat * (Math.PI / 180)), lat + dy]);
      }
      coords.push(coords[0]);
      return { type: 'Feature', properties: { id: zone.id }, geometry: { type: 'Polygon', coordinates: [coords] } };
    };
    const data = { type: 'FeatureCollection', features: trafficZones.map(toCircle) };
    if (m.getSource('traffic-zones')) {
      m.getSource('traffic-zones').setData(data);
    } else {
      m.addSource('traffic-zones', { type: 'geojson', data });
      m.addLayer({
        id: 'traffic-zones-fill', type: 'fill', source: 'traffic-zones',
        paint: { 'fill-color': '#F87171', 'fill-opacity': 0.15 },
      });
      m.addLayer({
        id: 'traffic-zones-line', type: 'line', source: 'traffic-zones',
        paint: { 'line-color': '#F87171', 'line-width': 1.5, 'line-opacity': 0.5 },
      });
    }
  }, [trafficZones]);

  // Dark stores: rebuilt when the list changes (rare — stores don't move).
  // ponytail: tried real GLB warehouse models via mapbox-gl v3 'model' sources first — the installed
  // mapbox-gl 3.1.2 + Standard style's shadow renderer throws `getModels is not a function` on every
  // single render frame for any 'model'-type source, confirmed by direct testing (not a config issue).
  // That's an uncaught exception in the render loop every frame — unshippable. DOM markers below per
  // the project's own fail-safe-fallback rule; revisit if a later mapbox-gl release fixes it.
  useEffect(() => {
    const m = map.current;
    if (!m || !m.isStyleLoaded()) return;
    storeMarkers.current.forEach(mk => mk.remove());
    storeMarkers.current = [];
    if (simulationMode) return;
    darkStores.forEach(store => {
      const el = document.createElement('div');
      el.className = 'cursor-pointer';
      el.innerHTML = `<div class="w-4 h-4 bg-slate-200 border-2 border-route-base rounded-sm shadow-lg flex items-center justify-center transition-transform hover:scale-125 hover:bg-white"></div>`;
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        onEntitySelect({ type: 'DARK_STORE', id: store.id, name: store.name, data: store });
        m.flyTo({ center: [store.lng, store.lat], zoom: 15, pitch: 45, speed: 1.2, curve: 1.42 });
      });
      storeMarkers.current.push(new mapboxgl.Marker(el).setLngLat([store.lng, store.lat]).addTo(m));
    });
  }, [darkStores, simulationMode]);

  // Riders: move existing markers in place every tick instead of rebuilding the DOM.
  useEffect(() => {
    const m = map.current;
    if (!m || !m.isStyleLoaded() || simulationMode) return;
    const seen = new Set();
    riders.forEach(rider => {
      seen.add(rider.id);
      let entry = riderMarkers.current.get(rider.id);
      if (!entry) {
        const el = document.createElement('div');
        el.className = 'cursor-pointer z-10';
        el.addEventListener('click', (e) => {
          e.stopPropagation();
          const current = ridersRef.current.find(r => r.id === rider.id) || rider;
          onEntitySelect({ type: 'RIDER', id: current.id, name: current.name, data: current });
          m.flyTo({ center: [current.lng, current.lat], zoom: 16.5, pitch: 65, speed: 1.2, curve: 1.42 });
        });
        const marker = new mapboxgl.Marker(el).setLngLat([rider.lng, rider.lat]).addTo(m);
        entry = { marker, el };
        riderMarkers.current.set(rider.id, entry);
      }
      entry.marker.setLngLat([rider.lng, rider.lat]);
      entry.el.innerHTML = `<div class="w-4 h-4 rounded-full border-2 border-route-base shadow-lg ${riderColor(rider.status)} flex items-center justify-center transition-transform hover:scale-125"><div class="w-1 h-1 bg-white rounded-full opacity-50 pointer-events-none"></div></div>`;
      entry.el.style.display = rider.status === 'OFFLINE' ? 'none' : '';
    });
    for (const [id, entry] of riderMarkers.current) {
      if (!seen.has(id)) { entry.marker.remove(); riderMarkers.current.delete(id); }
    }
  }, [riders, simulationMode]);

  // Orders: same incremental-update pattern, colored by live risk state.
  useEffect(() => {
    const m = map.current;
    if (!m || !m.isStyleLoaded() || simulationMode) return;
    const seen = new Set();
    orders.forEach(order => {
      seen.add(order.id);
      let entry = orderMarkers.current.get(order.id);
      if (!entry) {
        const el = document.createElement('div');
        el.className = 'cursor-pointer';
        el.addEventListener('click', (e) => {
          e.stopPropagation();
          const current = ordersRef.current.find(o => o.id === order.id) || order;
          onEntitySelect({ type: 'ORDER', id: current.id, name: `Order ${current.id}`, data: current });
          m.flyTo({ center: [current.lng, current.lat], zoom: 16, pitch: 60, speed: 1.2, curve: 1.42 });
        });
        const marker = new mapboxgl.Marker(el).setLngLat([order.lng, order.lat]).addTo(m);
        entry = { marker, el };
        orderMarkers.current.set(order.id, entry);
      }
      const anim = order.risk === 'SEVERE' || order.risk === 'DELAYED' ? 'marker-pulse-red' : (order.priority ? 'marker-pulse' : '');
      entry.el.innerHTML = `<div class="w-3 h-3 rotate-45 border-2 border-route-base shadow-lg ${orderColor(order)} ${anim} transition-transform hover:scale-125"></div>`;
    });
    for (const [id, entry] of orderMarkers.current) {
      if (!seen.has(id)) { entry.marker.remove(); orderMarkers.current.delete(id); }
    }
  }, [orders, simulationMode]);

  useEffect(() => {
    if (map.current) {
      window.mapAPI = {
        resetView: () => map.current.flyTo({ ...INITIAL_VIEW, speed: 1.2, curve: 1.42, essential: true }),
        zoomIn: () => map.current.zoomIn({ duration: 500 }),
        zoomOut: () => map.current.zoomOut({ duration: 500 }),
      };
    }
  }, []);

  return <div ref={mapContainer} className="w-full h-full transition-opacity duration-1000" />;
};

export default RouteMap;
