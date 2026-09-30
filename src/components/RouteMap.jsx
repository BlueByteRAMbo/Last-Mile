import React, { useEffect, useRef, useState } from 'react';
import mapboxgl from 'mapbox-gl';
import { darkStores, riders as initialRiders, orders, routes, trafficZones } from '../data/mockData';

// Mapbox Token
mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN;

const INITIAL_VIEW = {
  center: [72.8777, 19.0760],
  zoom: 13,
  pitch: 60,
  bearing: -15
};

const RouteMap = ({ onEntitySelect, liveOperations, onMapLoad, simulationMode }) => {
  const mapContainer = useRef(null);
  const map = useRef(null);
  const markersRef = useRef([]);
  const riderMarkersRef = useRef([]);
  const animationRef = useRef(null);
  
  // Keep local mutable state for simulation
  const simulationRiders = useRef(JSON.parse(JSON.stringify(initialRiders)));

  useEffect(() => {
    if (map.current) return;

    if (!mapboxgl.accessToken) {
      console.error("Mapbox token is missing!");
      return;
    }

    map.current = new mapboxgl.Map({
      container: mapContainer.current,
      style: 'mapbox://styles/mapbox/standard',
      center: INITIAL_VIEW.center,
      zoom: INITIAL_VIEW.zoom,
      pitch: INITIAL_VIEW.pitch,
      bearing: INITIAL_VIEW.bearing,
      antialias: true
    });

    map.current.on('style.load', () => {
      map.current.setConfigProperty('basemap', 'theme', 'night');
      addSourcesAndLayers();
      addMarkers();
      if (onMapLoad) onMapLoad(map.current);
    });

    return () => {
      if (map.current) {
        map.current.remove();
        map.current = null;
      }
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, []);

  // Simulation Effect
  useEffect(() => {
    if (!liveOperations) {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
      return;
    }

    let lastTime = 0;
    const animate = (time) => {
      if (time - lastTime > 1000) { // Update roughly every 1 second
        lastTime = time;
        // Move riders slightly
        simulationRiders.current.forEach((rider, idx) => {
          if (rider.status === 'ON_DELIVERY' || rider.status === 'AVAILABLE' || rider.status === 'NEAR_CAPACITY') {
            // Random walk simulation (slow drifting)
            rider.lng += (Math.random() - 0.5) * 0.0004;
            rider.lat += (Math.random() - 0.5) * 0.0004;
            
            // Update marker position
            const marker = riderMarkersRef.current[idx];
            if (marker) {
              marker.setLngLat([rider.lng, rider.lat]);
            }
          }
        });
      }
      animationRef.current = requestAnimationFrame(animate);
    };
    
    animationRef.current = requestAnimationFrame(animate);
    
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [liveOperations]);

  // Toggle layer visibility when simulationMode changes
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    if (m.isStyleLoaded()) {
      ['routes-line', 'routes-line-glow'].forEach(layer => {
        if (m.getLayer(layer)) {
          m.setLayoutProperty(layer, 'visibility', simulationMode ? 'none' : 'visible');
        }
      });
      addMarkers();
    }
  }, [simulationMode]);

  const addSourcesAndLayers = () => {
    const m = map.current;
    if (!m) return;

    const trafficFeatures = trafficZones.map(zone => {
      const points = 64;
      const coords = [];
      const km = zone.radius;
      const [lng, lat] = zone.center;
      
      for(let i = 0; i < points; i++) {
        const theta = (i / points) * (2 * Math.PI);
        const dx = (km / 111.32) * Math.cos(theta);
        const dy = (km / 111.32) * Math.sin(theta);
        coords.push([lng + dx / Math.cos(lat * (Math.PI/180)), lat + dy]);
      }
      coords.push(coords[0]);

      return {
        type: 'Feature',
        properties: { level: zone.level },
        geometry: { type: 'Polygon', coordinates: [coords] }
      };
    });

    m.addSource('traffic-zones', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: trafficFeatures }
    });

    m.addLayer({
      id: 'traffic-zones-fill',
      type: 'fill',
      source: 'traffic-zones',
      paint: {
        'fill-color': ['match', ['get', 'level'], 'HIGH', '#F87171', 'MEDIUM', '#F59E0B', '#38BDF8'],
        'fill-opacity': 0.15
      }
    });

    m.addLayer({
      id: 'traffic-zones-line',
      type: 'line',
      source: 'traffic-zones',
      paint: {
        'line-color': ['match', ['get', 'level'], 'HIGH', '#F87171', 'MEDIUM', '#F59E0B', '#38BDF8'],
        'line-width': 1,
        'line-opacity': 0.3
      }
    });

    const routeFeatures = routes.map(route => ({
      type: 'Feature',
      properties: { id: route.id, status: route.status, riderId: route.riderId },
      geometry: { type: 'LineString', coordinates: route.coordinates }
    }));

    m.addSource('delivery-routes', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: routeFeatures }
    });

    m.addLayer({
      id: 'routes-line-glow',
      type: 'line',
      source: 'delivery-routes',
      layout: { visibility: simulationMode ? 'none' : 'visible' },
      paint: {
        'line-color': ['match', ['get', 'status'], 'ACTIVE', '#38BDF8', 'AT_RISK', '#F59E0B', 'DELAYED', '#F87171', '#38BDF8'],
        'line-width': 6,
        'line-opacity': 0.2,
        'line-blur': 4
      }
    });

    m.addLayer({
      id: 'routes-line',
      type: 'line',
      source: 'delivery-routes',
      layout: { visibility: simulationMode ? 'none' : 'visible' },
      paint: {
        'line-color': ['match', ['get', 'status'], 'ACTIVE', '#38BDF8', 'AT_RISK', '#F59E0B', 'DELAYED', '#F87171', '#38BDF8'],
        'line-width': 2,
        'line-opacity': 0.8
      }
    });

    m.on('click', 'routes-line', (e) => {
      const prop = e.features[0].properties;
      onEntitySelect({ type: 'ROUTE', id: prop.id, name: `Route ${prop.id}`, data: prop });
      
      // Smooth fly to route start point
      const coords = e.features[0].geometry.coordinates[0];
      m.flyTo({ center: coords, zoom: 14.5, pitch: 50, speed: 1.2, curve: 1.42 });
    });

    m.on('mouseenter', 'routes-line', () => { m.getCanvas().style.cursor = 'pointer'; });
    m.on('mouseleave', 'routes-line', () => { m.getCanvas().style.cursor = ''; });
  };

  const addMarkers = () => {
    const m = map.current;
    if (!m) return;

    markersRef.current.forEach(marker => marker.remove());
    riderMarkersRef.current.forEach(marker => marker?.remove());
    markersRef.current = [];
    riderMarkersRef.current = [];
    
    if (simulationMode) return; // Don't draw standard markers in sim mode

    // Dark Stores
    darkStores.forEach(store => {
      const el = document.createElement('div');
      el.className = 'cursor-pointer';
      el.innerHTML = `<div class="w-4 h-4 bg-slate-200 border-2 border-route-base rounded-sm shadow-lg flex items-center justify-center transition-transform hover:scale-125 hover:bg-white"></div>`;
      
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        onEntitySelect({ type: 'DARK_STORE', id: store.id, name: store.name, data: store });
        m.flyTo({ center: [store.lng, store.lat], zoom: 15, pitch: 45, speed: 1.2, curve: 1.42 });
      });

      const marker = new mapboxgl.Marker(el).setLngLat([store.lng, store.lat]).addTo(m);
      markersRef.current.push(marker);
    });

    // Orders
    orders.forEach(order => {
      const el = document.createElement('div');
      el.className = 'cursor-pointer';
      
      let colorClass = 'bg-route-cyan';
      let animClass = '';
      if (order.status === 'AT_RISK') {
        colorClass = 'bg-route-amber';
      } else if (order.status === 'DELAYED') {
        colorClass = 'bg-route-red';
        animClass = 'marker-pulse-red';
      } else if (order.status === 'PRIORITY') {
        colorClass = 'bg-route-cyan';
        animClass = 'marker-pulse';
      }

      el.innerHTML = `<div class="w-3 h-3 rotate-45 border-2 border-route-base shadow-lg ${colorClass} ${animClass} transition-transform hover:scale-125"></div>`;
      
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        onEntitySelect({ type: 'ORDER', id: order.id, name: `Order ${order.id}`, data: order });
        m.flyTo({ center: [order.lng, order.lat], zoom: 16, pitch: 60, speed: 1.2, curve: 1.42 });
      });

      const marker = new mapboxgl.Marker(el).setLngLat([order.lng, order.lat]).addTo(m);
      markersRef.current.push(marker);
    });

    // Riders
    simulationRiders.current.forEach(rider => {
      if (rider.status === 'OFFLINE') {
        riderMarkersRef.current.push(null);
        return;
      }

      const el = document.createElement('div');
      el.className = 'cursor-pointer z-10';
      
      let colorClass = 'bg-route-green';
      if (rider.status === 'ON_DELIVERY') colorClass = 'bg-route-cyan';
      if (rider.status === 'NEAR_CAPACITY') colorClass = 'bg-route-amber';

      el.innerHTML = `<div class="w-4 h-4 rounded-full border-2 border-route-base shadow-lg ${colorClass} flex items-center justify-center transition-transform hover:scale-125"><div class="w-1 h-1 bg-white rounded-full opacity-50 pointer-events-none"></div></div>`;
      
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        onEntitySelect({ type: 'RIDER', id: rider.id, name: rider.name, data: rider });
        // Make the camera follow the rider smoothly
        m.flyTo({ center: [rider.lng, rider.lat], zoom: 16.5, pitch: 65, speed: 1.2, curve: 1.42 });
      });

      const marker = new mapboxgl.Marker(el).setLngLat([rider.lng, rider.lat]).addTo(m);
      riderMarkersRef.current.push(marker);
      markersRef.current.push(marker);
    });
  };

  useEffect(() => {
    if (map.current) {
      window.mapAPI = {
        resetView: () => {
          map.current.flyTo({ ...INITIAL_VIEW, speed: 1.2, curve: 1.42, essential: true });
        },
        zoomIn: () => map.current.zoomIn({ duration: 500 }),
        zoomOut: () => map.current.zoomOut({ duration: 500 })
      };
    }
  }, []);

  return <div ref={mapContainer} className="w-full h-full transition-opacity duration-1000" />;
};

export default RouteMap;
