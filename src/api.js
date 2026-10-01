const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const WS_BASE = BASE.replace(/^http/, 'ws');

export const api = {
  darkStores: () => fetch(`${BASE}/dark_stores`).then(r => r.json()),
  storeInventory: (id) => fetch(`${BASE}/dark_stores/${id}/inventory`).then(r => r.json()),
  riders: () => fetch(`${BASE}/riders`).then(r => r.json()),
  riderRoute: (id) => fetch(`${BASE}/riders/${id}/route`).then(r => r.json()),
  orders: (status) => fetch(`${BASE}/orders${status ? `?status=${status}` : ''}`).then(r => r.json()),
  explainOrder: (id) => fetch(`${BASE}/orders/${id}/explain`).then(r => r.json()),
  track: (id) => fetch(`${BASE}/track/${id}`).then(r => { if (!r.ok) throw new Error('not found'); return r.json(); }),
  createOrder: (body) => fetch(`${BASE}/orders`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }).then(r => r.json()),
  catalog: () => fetch(`${BASE}/catalog`).then(r => r.json()),
  catalogAvailability: (skus, lat, lng) => fetch(`${BASE}/catalog/availability?skus=${skus.join(',')}${lat != null ? `&customer_lat=${lat}&customer_lng=${lng}` : ''}`).then(r => r.json()),
  restock: (storeId, sku, qty) => fetch(`${BASE}/dark_stores/${storeId}/restock`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sku, qty }),
  }).then(r => r.json()),
  kpis: () => fetch(`${BASE}/kpis`).then(r => r.json()),
  disrupt: (kind, target) => fetch(`${BASE}/disruptions/${kind}${target ? `?target=${target}` : ''}`, { method: 'POST' }).then(r => r.json()),
  reset: () => fetch(`${BASE}/reset`, { method: 'POST' }).then(r => r.json()),
};

export function connectWs(onMessage) {
  let ws;
  let closedByUs = false;
  const open = () => {
    ws = new WebSocket(`${WS_BASE}/ws`);
    ws.onmessage = (ev) => onMessage(JSON.parse(ev.data));
    ws.onclose = () => { if (!closedByUs) setTimeout(open, 1500); };
  };
  open();
  return () => { closedByUs = true; ws?.close(); };
}
