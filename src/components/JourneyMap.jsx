import React, { useEffect, useRef, useState } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';

const collection = lines => ({ type: 'FeatureCollection', features: lines.filter(line => line?.length >= 2).map(coordinates => ({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates } })) });
function arc(a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  return Array.from({ length: 31 }, (_, i) => { const t = i / 30, curve = Math.sin(Math.PI * t) * .12; return [a[0] + dx * t - dy * curve, a[1] + dy * t + dx * curve]; });
}

export default function JourneyMap({ data, stores = [], riders = [], shortlist = [], step = 3, follow = false, traffic = [], placing = false, onPlace, decision, customerOnly = false }) {
  const container = useRef(null), map = useRef(null), markers = useRef(new Map());
  const click = useRef(null), frame = useRef(null), fitted = useRef(false);
  const [ready, setReady] = useState(false), [failed, setFailed] = useState(false);
  click.current = placing ? onPlace : null;
  const token = import.meta.env.VITE_MAPBOX_TOKEN;
  useEffect(() => {
    if (!token) return;
    const m = new mapboxgl.Map({ container: container.current, accessToken: token, style: 'mapbox://styles/mapbox/dark-v11', center: [72.86, 19.07], zoom: 12, pitch: 35 });
    map.current = m;
    m.on('load', () => setReady(true));
    m.on('error', () => { if (!m.isStyleLoaded()) setFailed(true); });
    m.on('click', e => click.current?.({ lat: e.lngLat.lat, lng: e.lngLat.lng }));
    m.addControl(new mapboxgl.NavigationControl(), 'bottom-right');
    const resize = new ResizeObserver(() => m.resize());
    resize.observe(container.current);
    const markerEntries = markers.current;
    return () => { resize.disconnect(); cancelAnimationFrame(frame.current); markerEntries.forEach(entry => entry.marker.remove()); markerEntries.clear(); m.remove(); map.current = null; };
  }, [token]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !data || !m) return;
    m.getCanvas().style.cursor = placing ? 'crosshair' : '';
    const customer = [data.customer_location.lng, data.customer_location.lat];
    const storeList = customerOnly ? (data.store ? [{ ...data.store, store_id: data.store.id, store_name: data.store.name, has_all_items: true }] : []) : stores;
    const riderList = customerOnly ? [] : riders;
    const moving = [...riderList.filter(r => r.id !== data.rider_id)];
    if (data.rider_position) moving.push({ id: data.rider_id, name: data.rider_name, ...data.rider_position, heading: data.heading });
    const seen = new Set(), animations = [];
    const mark = (key, lngLat, label, color, animate = false, heading = null, pulse = false) => {
      seen.add(key);
      let entry = markers.current.get(key);
      if (!entry) {
        const el = document.createElement('div');
        entry = { marker: new mapboxgl.Marker({ element: el }).setLngLat(lngLat).addTo(m), el };
        markers.current.set(key, entry);
      }
      entry.el.classList.add('journey-marker');
      entry.el.classList.toggle('shortlisted', pulse);
      entry.el.replaceChildren();
      const dot = document.createElement('span'); dot.className = 'journey-dot'; dot.style.background = color;
      if (heading != null) { dot.textContent = '↑'; dot.style.transform = `rotate(${heading}deg)`; }
      entry.el.appendChild(dot);
      if (label) { const text = document.createElement('span'); text.className = 'journey-label'; text.textContent = label; entry.el.appendChild(text); }
      if (animate) animations.push({ marker: entry.marker, from: entry.marker.getLngLat(), to: lngLat });
      else entry.marker.setLngLat(lngLat);
    };
    mark('customer', customer, data.customer_name || 'Customer', '#38BDF8');
    storeList.forEach(s => mark(`store-${s.store_id}`, [s.lng, s.lat],
      `${s.store_name}${s.store_id === data.store?.id ? ' · selected' : ''} · ${s.has_all_items ? 'items confirmed' : 'items missing'}`,
      s.has_all_items ? '#34D399' : '#475569', false, null, step === 1 && s.store_id === data.store?.id));
    moving.forEach(r => mark(`rider-${r.id}`, [r.lng, r.lat], r.id === data.rider_id ? `${r.name} · ${data.order_id} · ${data.customer_name || 'Customer'}` : (r.orderLabel || (step === 2 && shortlist.includes(r.id) ? r.name : '')),
      r.id === data.rider_id ? '#34D399' : '#94a3b8', true, r.heading, step === 2 && shortlist.includes(r.id)));
    for (const [id, entry] of markers.current) if (!seen.has(id)) { entry.marker.remove(); markers.current.delete(id); }
    cancelAnimationFrame(frame.current);
    const started = performance.now();
    const animate = now => {
      const t = Math.min(1, (now - started) / 1800);
      animations.forEach(a => a.marker.setLngLat([a.from.lng + (a.to[0] - a.from.lng) * t, a.from.lat + (a.to[1] - a.from.lat) * t]));
      if (t < 1) frame.current = requestAnimationFrame(animate);
    };
    frame.current = requestAnimationFrame(animate);
    const line = (id, points, color, width, opacity = 1, dashed = false) => {
      const geo = collection(points);
      if (m.getSource(id)) m.getSource(id).setData(geo);
      else {
        m.addSource(id, { type: 'geojson', data: geo });
        m.addLayer({ id, type: 'line', source: id, paint: { 'line-color': color, 'line-width': width, 'line-opacity': opacity, ...(dashed ? { 'line-dasharray': [2, 2] } : {}) } });
      }
    };
    line('completed-path', [data.polyline], '#64748B', 5, .45);
    line('live-path', step >= 3 ? [data.polyline_remaining] : [], '#34D399', 5);
    const arcs = [];
    if (!customerOnly && data.store && step === 1) arcs.push(arc(customer, [data.store.lng, data.store.lat]));
    if (!customerOnly && data.store && data.rider_position && step === 2) arcs.push(arc([data.store.lng, data.store.lat], [data.rider_position.lng, data.rider_position.lat]));
    line('selection-arcs', arcs, '#38BDF8', 3, .85, true);
    line('old-path', decision?.switched ? [decision.old_polyline] : [], '#F87171', 6, .7);
    line('candidate-path', decision ? [decision.candidate_polyline] : [], '#FBBF24', 3, 1, true);
    const zones = { type: 'FeatureCollection', features: traffic.map(z => {
      const ring = Array.from({ length: 49 }, (_, i) => { const angle = i / 48 * Math.PI * 2; return [z.lng + Math.cos(angle) * z.radius_km / (111 * Math.cos(z.lat * Math.PI / 180)), z.lat + Math.sin(angle) * z.radius_km / 111]; });
      return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [ring] } };
    }) };
    if (m.getSource('congestion')) m.getSource('congestion').setData(zones);
    else { m.addSource('congestion', { type: 'geojson', data: zones }); m.addLayer({ id: 'congestion', type: 'fill', source: 'congestion', paint: { 'fill-color': '#F87171', 'fill-opacity': .25 } }); }
    if (!fitted.current) {
      const bounds = new mapboxgl.LngLatBounds(customer, customer);
      if (customerOnly && data.store) bounds.extend([data.store.lng, data.store.lat]);
      else storeList.forEach(s => bounds.extend([s.lng, s.lat]));
      if (data.rider_position) bounds.extend([data.rider_position.lng, data.rider_position.lat]);
      m.fitBounds(bounds, { padding: 90, maxZoom: 15, duration: 800 }); fitted.current = true;
    }
    if (follow && data.rider_position) m.easeTo({ center: [data.rider_position.lng, data.rider_position.lat], zoom: 15.4, duration: 1800 });
  }, [ready, data, stores, riders, shortlist, step, follow, traffic, placing, decision, customerOnly]);

  return <div className="journey-map"><div ref={container} className="absolute inset-0" />
    {(!token || failed) && <div className="map-unavailable"><strong>Map unavailable</strong><p>{!token ? 'Configure VITE_MAPBOX_TOKEN to display the live map.' : 'The map could not load. Check the network or Mapbox token.'}</p><p>Order status and tracking remain live.</p></div>}
    {data?.approximate_route && data?.polyline_remaining?.length > 1 && <span className="map-route-badge">Approximate route</span>}
    {placing && <div className="map-instruction">Click the map or rider path to place traffic</div>}
  </div>;
}
