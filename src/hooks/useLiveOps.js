import { useEffect, useState } from 'react';
import { api, connectWs } from '../api';

// Live state backed by the FastAPI + Neon backend: REST for initial load, WS ticks after.
export default function useLiveOps() {
  const [darkStores, setDarkStores] = useState([]);
  const [riders, setRiders] = useState([]);
  const [orders, setOrders] = useState([]);
  const [trafficZones, setTrafficZones] = useState([]);
  const [connected, setConnected] = useState(false);
  const [kpis, setKpis] = useState(null);

  useEffect(() => {
    api.darkStores().then(setDarkStores).catch(() => {});
    api.riders().then(setRiders).catch(() => {});
    api.orders().then(setOrders).catch(() => {});
    api.kpis().then(setKpis).catch(() => {});

    const close = connectWs((msg) => {
      if (msg.type !== 'tick') return;
      setConnected(true);
      setDarkStores(msg.dark_stores);
      setRiders(msg.riders);
      setOrders(msg.orders);
      setTrafficZones(msg.traffic_zones || []);
    }, '/ws', setConnected);

    const kpiInterval = setInterval(() => api.kpis().then(setKpis).catch(() => {}), 4000);
    // dark store packing/queue counts aren't in the WS tick payload, poll them separately
    const storeInterval = setInterval(() => api.darkStores().then(setDarkStores).catch(() => {}), 4000);
    return () => { close(); clearInterval(kpiInterval); clearInterval(storeInterval); };
  }, []);

  return { darkStores, riders, orders, trafficZones, kpis, connected };
}
