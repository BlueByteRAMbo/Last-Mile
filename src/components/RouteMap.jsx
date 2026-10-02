import React, { useEffect, useRef, useState } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';

// Mapbox Token
mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN;

const INITIAL_VIEW = {
  center: [72.8777, 19.0760],
  zoom: 13,
  pitch: 60,
  bearing: -15,
};

// ── Rider status config: bg color (Tailwind), label, emoji ──────────────────
const RIDER_STATUS = {
  AVAILABLE:   { bg: '#22c55e', label: 'Available',   emoji: '🟢' },
  PICKING_UP:  { bg: '#f59e0b', label: 'Picking Up',  emoji: '🏪' },
  ON_DELIVERY: { bg: '#38bdf8', label: 'On Delivery', emoji: '🛵' },
  OFFLINE:     { bg: '#64748b', label: 'Offline',     emoji: '⚫' },
};

// ── Order risk / status → order marker color ─────────────────────────────────
function orderBg(o) {
  if (o.risk === 'SEVERE' || o.risk === 'DELAYED') return '#ef4444';
  if (o.risk === 'AT_RISK') return '#f59e0b';
  if (o.priority) return '#a78bfa';
  return '#38bdf8';
}

function riderStatusCfg(status) {
  return RIDER_STATUS[status] || RIDER_STATUS.OFFLINE;
}

// Tooltips are built with innerHTML, and names come from user-submitted orders: escape everything interpolated.
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// Build a rider DOM marker element with: dot + status badge + hover tooltip
function buildRiderEl(rider, orders) {
  const cfg = riderStatusCfg(rider.status);
  const assignedOrders = orders.filter(o => o.rider_id === rider.id && !['delivered','failed','cancelled'].includes(o.status));

  const wrap = document.createElement('div');
  wrap.className = 'rider-marker-wrap';
  // no `position` here: this is the Mapbox marker root, which needs mapbox's position:absolute (it also anchors the tooltip)
  wrap.style.cssText = 'display:flex;flex-direction:column;align-items:center;gap:2px;cursor:pointer;width:max-content;';

  // Status badge (floats above the dot)
  const badge = document.createElement('div');
  badge.className = 'rider-badge';
  badge.style.cssText = `
    background:${cfg.bg};color:#000;font-size:9px;font-weight:700;
    padding:1px 5px;border-radius:999px;white-space:nowrap;
    box-shadow:0 1px 4px rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.3);
    pointer-events:none;line-height:1.4;
  `;
  badge.textContent = cfg.label.toUpperCase();

  // Dot
  const dot = document.createElement('div');
  dot.style.cssText = `
    width:14px;height:14px;border-radius:50%;background:${cfg.bg};
    border:2px solid rgba(255,255,255,0.8);box-shadow:0 0 0 2px ${cfg.bg}55,0 2px 8px rgba(0,0,0,0.5);
    transition:transform 0.15s;
  `;

  // Hover tooltip
  const tip = document.createElement('div');
  tip.dataset.riderTip = '1';
  tip.style.cssText = `
    display:none;position:absolute;bottom:calc(100% + 6px);left:50%;transform:translateX(-50%);
    background:rgba(15,23,42,0.97);color:#e2e8f0;font-size:11px;
    border-radius:8px;border:1px solid rgba(255,255,255,0.12);
    padding:8px 10px;min-width:160px;max-width:220px;
    box-shadow:0 8px 24px rgba(0,0,0,0.6);z-index:100;pointer-events:none;
    white-space:nowrap;
  `;

  const orderLines = assignedOrders.length
    ? assignedOrders.map(o => {
        const stIcon = { created:'⏳', assigned:'📋', packing:'📦', packed:'✅', out_for_delivery:'🛵', delivered:'🏁' }[o.status] || '•';
        return `<div style="margin-top:4px;color:#94a3b8;font-size:10px">${stIcon} ${esc(o.customer_name || o.id)} · <span style="color:${orderBg(o)}">${esc((o.status||'').replace('_',' '))}</span></div>`;
      }).join('')
    : '<div style="color:#64748b;margin-top:2px;font-size:10px">No active orders</div>';

  tip.innerHTML = `
    <div style="font-weight:700;color:#f1f5f9">${cfg.emoji} ${esc(rider.name)}</div>
    <div style="color:${cfg.bg};font-size:10px;margin-top:1px">${cfg.label}</div>
    <div style="margin-top:4px;color:#94a3b8;font-size:10px">🔋 ${rider.battery_pct}% · Load ${rider.current_load_kg?.toFixed(1)}/${rider.capacity_kg}kg</div>
    ${orderLines}
  `;

  wrap.addEventListener('mouseenter', () => { tip.style.display = 'block'; dot.style.transform = 'scale(1.4)'; });
  wrap.addEventListener('mouseleave', () => { tip.style.display = 'none'; dot.style.transform = ''; });

  wrap.append(tip, badge, dot);
  return wrap;
}

// Real backend state drives every marker: dark stores, riders (from /riders + WS ticks) and
// orders (with live risk/priority) replace the old static mock data + random-walk animation.
const RouteMap = ({ onEntitySelect, darkStores, riders, orders, trafficZones = [], riderDetail = null, demandZones = [], showDemandHeatmap = false, simulationMode, onMapLoad }) => {
  const mapContainer = useRef(null);
  const map = useRef(null);
  const [mapReady, setMapReady] = useState(false);
  const fittedStores = useRef(false);
  const storeMarkers = useRef([]);
  const riderMarkers = useRef(new Map()); // id -> {marker, el}
  const orderMarkers = useRef(new Map());
  const ridersRef = useRef(riders);
  const ordersRef = useRef(orders);
  ridersRef.current = riders;
  ordersRef.current = orders;

  useEffect(() => {
    if (map.current) return;
    if (!mapboxgl.accessToken) { console.error('Mapbox token is missing!'); return; }
    map.current = new mapboxgl.Map({
      container: mapContainer.current,
      style: 'mapbox://styles/mapbox/standard',
      ...INITIAL_VIEW,
      antialias: true,
    });
    map.current.on('style.load', () => {
      map.current.setConfigProperty('basemap', 'theme', 'night');
      setMapReady(true);
      if (onMapLoad) onMapLoad(map.current);
    });
    return () => {
      storeMarkers.current.forEach(m => m.remove());
      riderMarkers.current.forEach(e => e.marker.remove());
      orderMarkers.current.forEach(e => e.marker.remove());
      storeMarkers.current = [];
      riderMarkers.current.clear();
      orderMarkers.current.clear();
      fittedStores.current = false;
      setMapReady(false);
      map.current?.remove();
      map.current = null;
    };
  }, []);

  // Demand heatmap
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const update = () => {
      if (!m.isStyleLoaded()) return;
      try { applyHeatmap(); } catch { /* style still settling; the style.load listener retries */ }
    };
    const applyHeatmap = () => {
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

  // Live traffic zones
  useEffect(() => {
    const m = map.current;
    if (!m || !mapReady) return;
    const toCircle = (zone) => {
      const points = 48; const coords = [];
      const km = zone.radius_km; const { lng, lat } = zone;
      for (let i = 0; i < points; i++) {
        const theta = (i / points) * 2 * Math.PI;
        const dx = (km / 111.32) * Math.cos(theta);
        const dy = (km / 111.32) * Math.sin(theta);
        coords.push([lng + dx / Math.cos(lat * Math.PI / 180), lat + dy]);
      }
      coords.push(coords[0]);
      return { type: 'Feature', properties: { id: zone.id }, geometry: { type: 'Polygon', coordinates: [coords] } };
    };
    const data = { type: 'FeatureCollection', features: trafficZones.map(toCircle) };
    if (m.getSource('traffic-zones')) {
      m.getSource('traffic-zones').setData(data);
    } else {
      m.addSource('traffic-zones', { type: 'geojson', data });
      m.addLayer({ id: 'traffic-zones-fill', type: 'fill', source: 'traffic-zones', paint: { 'fill-color': '#F87171', 'fill-opacity': 0.15 } });
      m.addLayer({ id: 'traffic-zones-line', type: 'line', source: 'traffic-zones', paint: { 'line-color': '#F87171', 'line-width': 1.5, 'line-opacity': 0.5 } });
    }
  }, [trafficZones, mapReady]);

  // Selected rider's road route: full leg faint, remaining leg bright, plus from/to stop pins
  const routeStopMarkers = useRef([]);
  useEffect(() => {
    const m = map.current;
    if (!m || !mapReady) return;
    const line = (coords) => ({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: coords } });
    const fc = (features) => ({ type: 'FeatureCollection', features });
    const full = riderDetail?.polyline?.length > 1 ? [line(riderDetail.polyline)] : [];
    const rest = riderDetail?.polyline_remaining?.length > 1 ? [line(riderDetail.polyline_remaining)] : [];
    try {
      if (m.getSource('rider-route-full')) {
        m.getSource('rider-route-full').setData(fc(full));
        m.getSource('rider-route-rest').setData(fc(rest));
      } else {
        m.addSource('rider-route-full', { type: 'geojson', data: fc(full) });
        m.addSource('rider-route-rest', { type: 'geojson', data: fc(rest) });
        m.addLayer({ id: 'rider-route-full', type: 'line', source: 'rider-route-full', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#94a3b8', 'line-width': 4, 'line-opacity': 0.45 } });
        m.addLayer({ id: 'rider-route-rest', type: 'line', source: 'rider-route-rest', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#38bdf8', 'line-width': 5, 'line-opacity': 0.95 } });
      }
    } catch { /* style still settling; next detail poll retries */ }

    routeStopMarkers.current.forEach(mk => mk.remove());
    routeStopMarkers.current = [];
    if (!riderDetail) return;
    const pin = (stop, color, text) => {
      if (!stop) return;
      const el = document.createElement('div');
      el.style.cssText = `background:${color};color:#000;font-size:10px;font-weight:700;padding:2px 7px;border-radius:999px;border:2px solid #fff;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.5);pointer-events:none;`;
      el.textContent = `${text}: ${stop.label}`;
      routeStopMarkers.current.push(new mapboxgl.Marker({ element: el, anchor: 'bottom' }).setLngLat([stop.lng, stop.lat]).addTo(m));
    };
    pin(riderDetail.leg_from, '#fbbf24', 'FROM');
    pin(riderDetail.leg_to, '#22c55e', 'TO');
    return () => { routeStopMarkers.current.forEach(mk => mk.remove()); routeStopMarkers.current = []; };
  }, [riderDetail, mapReady]);

  // Dark store markers
  useEffect(() => {
    const m = map.current;
    if (!m || !mapReady) return;
    storeMarkers.current.forEach(mk => mk.remove());
    storeMarkers.current = [];
    if (simulationMode) return;
    darkStores.forEach(store => {
      const el = document.createElement('div');
      el.className = 'cursor-pointer ops-store-marker';
      el.style.cssText = 'display:flex;flex-direction:column;align-items:center;gap:2px;';
      const icon = document.createElement('div');
      icon.style.cssText = `
        background:#1e293b;border:2px solid #7c3aed;border-radius:6px;
        padding:3px 6px;font-size:11px;color:#c4b5fd;font-weight:700;
        box-shadow:0 2px 8px rgba(124,58,237,0.4);white-space:nowrap;
      `;
      icon.textContent = `🏪 ${store.name}`;
      el.append(icon);
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        onEntitySelect({ type: 'DARK_STORE', id: store.id, name: store.name, data: store });
        m.flyTo({ center: [store.lng, store.lat], zoom: 15, pitch: 45, speed: 1.2, curve: 1.42 });
      });
      storeMarkers.current.push(new mapboxgl.Marker(el).setLngLat([store.lng, store.lat]).addTo(m));
    });
    if (!fittedStores.current && darkStores.length) {
      const bounds = new mapboxgl.LngLatBounds();
      darkStores.forEach(s => bounds.extend([s.lng, s.lat]));
      m.fitBounds(bounds, { padding: 90, maxZoom: 13, duration: 600 });
      fittedStores.current = true;
    }
  }, [darkStores, simulationMode, mapReady]);

  // Rider markers — update in-place each tick, rebuild DOM only when status changes
  useEffect(() => {
    const m = map.current;
    if (!m || !mapReady || simulationMode) return;
    const seen = new Set();
    riders.forEach(rider => {
      seen.add(rider.id);
      let entry = riderMarkers.current.get(rider.id);
      const needRebuild = !entry || entry.lastStatus !== rider.status;

      if (!entry) {
        const el = buildRiderEl(rider, ordersRef.current);
        el.addEventListener('click', (e) => {
          e.stopPropagation();
          const cur = ridersRef.current.find(r => r.id === rider.id) || rider;
          onEntitySelect({ type: 'RIDER', id: cur.id, name: cur.name, data: cur });
          m.flyTo({ center: [cur.lng, cur.lat], zoom: 14.5, pitch: 40, speed: 1.2, curve: 1.42 });
        });
        const marker = new mapboxgl.Marker(el).setLngLat([rider.lng, rider.lat]).addTo(m);
        entry = { marker, el, lastStatus: rider.status };
        riderMarkers.current.set(rider.id, entry);
      } else {
        entry.marker.setLngLat([rider.lng, rider.lat]);
        if (needRebuild) {
          // Swap out the inner content when status changes
          // Keep the original root element: mapbox positions it via .mapboxgl-marker + transform,
          // so replacing the root left the new one unpositioned and stretched across the map.
          // The root already has the click handler, so only the inner content is swapped.
          entry.el.replaceChildren(buildRiderEl(rider, ordersRef.current));
          entry.lastStatus = rider.status;
        } else {
          // Just refresh tooltip order list inside existing element
          const tip = entry.el.querySelector('[data-rider-tip]');
          if (tip) {
            const cur = ridersRef.current.find(r => r.id === rider.id) || rider;
            const cfg = riderStatusCfg(cur.status);
            const assignedOrders = ordersRef.current.filter(o => o.rider_id === cur.id && !['delivered','failed','cancelled'].includes(o.status));
            const orderLines = assignedOrders.length
              ? assignedOrders.map(o => {
                  const stIcon = { created:'⏳', assigned:'📋', packing:'📦', packed:'✅', out_for_delivery:'🛵', delivered:'🏁' }[o.status] || '•';
                  return `<div style="margin-top:4px;color:#94a3b8;font-size:10px">${stIcon} ${esc(o.customer_name || o.id)} · <span style="color:${orderBg(o)}">${esc((o.status||'').replace('_',' '))}</span></div>`;
                }).join('')
              : '<div style="color:#64748b;margin-top:2px;font-size:10px">No active orders</div>';
            tip.innerHTML = `
              <div style="font-weight:700;color:#f1f5f9">${cfg.emoji} ${esc(cur.name)}</div>
              <div style="color:${cfg.bg};font-size:10px;margin-top:1px">${cfg.label}</div>
              <div style="margin-top:4px;color:#94a3b8;font-size:10px">🔋 ${cur.battery_pct}% · Load ${cur.current_load_kg?.toFixed(1)}/${cur.capacity_kg}kg</div>
              ${orderLines}
            `;
          }
        }
      }
      entry.el.style.display = rider.status === 'OFFLINE' ? 'none' : '';
    });
    for (const [id, entry] of riderMarkers.current) {
      if (!seen.has(id)) { entry.marker.remove(); riderMarkers.current.delete(id); }
    }
  }, [riders, simulationMode, mapReady]);

  // Order markers — colored by risk, pulsing when at-risk/severe
  useEffect(() => {
    const m = map.current;
    if (!m || !mapReady || simulationMode) return;
    const seen = new Set();
    orders.forEach(order => {
      seen.add(order.id);
      let entry = orderMarkers.current.get(order.id);
      if (!entry) {
        const el = document.createElement('div');
        el.className = 'cursor-pointer';
        el.addEventListener('click', (e) => {
          e.stopPropagation();
          const cur = ordersRef.current.find(o => o.id === order.id) || order;
          onEntitySelect({ type: 'ORDER', id: cur.id, name: `Order ${cur.id}`, data: cur });
          m.flyTo({ center: [cur.lng, cur.lat], zoom: 16, pitch: 60, speed: 1.2, curve: 1.42 });
        });
        const marker = new mapboxgl.Marker(el).setLngLat([order.lng, order.lat]).addTo(m);
        entry = { marker, el };
        orderMarkers.current.set(order.id, entry);
      }
      const bg = orderBg(order);
      const pulse = order.risk === 'SEVERE' || order.risk === 'DELAYED' ? 'marker-pulse-red' : (order.risk === 'AT_RISK' ? 'marker-pulse' : '');
      entry.el.innerHTML = `<div style="width:10px;height:10px;transform:rotate(45deg);background:${bg};border:1.5px solid rgba(255,255,255,0.7);box-shadow:0 0 6px ${bg}88;" class="${pulse}"></div>`;
    });
    for (const [id, entry] of orderMarkers.current) {
      if (!seen.has(id)) { entry.marker.remove(); orderMarkers.current.delete(id); }
    }
  }, [orders, simulationMode, mapReady]);

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
