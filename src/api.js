import { subscribeSocket } from './socket';

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const WS_BASE = BASE.replace(/^http/, 'ws');

async function request(path, body) {
  const response = await fetch(`${BASE}${path}`, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : 'Request failed. Please check your inputs.');
    error.status = response.status;
    throw error;
  }
  return data;
}

export const api = {
  dispatchMode: () => request('/dispatch/mode'),
  setDispatchMode: mode => request('/dispatch/mode', { mode }),
  simSpeed: () => request('/simulation/speed'),
  setSimSpeed: multiplier => request('/simulation/speed', { multiplier }),
  comparison: () => request('/analytics/comparison'),
  journey: id => request(`/orders/${encodeURIComponent(id)}/journey`),
  traffic: body => request(`/disruptions/traffic?${new URLSearchParams(body)}`, {}),
  interveneOrder: async (id, action) => {
    const response = await fetch(`${BASE}/orders/${encodeURIComponent(id)}/intervene/${action}`, { method: 'POST' });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || 'Intervention failed');
    return body;
  },
  darkStores: () => fetch(`${BASE}/dark_stores`).then(r => r.json()),
  storeInventory: (id) => fetch(`${BASE}/dark_stores/${id}/inventory`).then(r => r.json()),
  riders: () => fetch(`${BASE}/riders`).then(r => r.json()),
  riderRoute: (id) => fetch(`${BASE}/riders/${id}/route`).then(r => r.json()),
  orders: (status) => fetch(`${BASE}/orders${status ? `?status=${status}` : ''}`).then(r => r.json()),
  explainOrder: (id) => fetch(`${BASE}/orders/${id}/explain`).then(r => r.json()),
  track: id => request(`/track/${encodeURIComponent(id)}`),
  createOrder: body => request('/orders', body),
  catalog: () => fetch(`${BASE}/catalog`).then(r => r.json()),
  catalogAvailability: (skus, lat, lng) => fetch(`${BASE}/catalog/availability?skus=${skus.join(',')}${lat != null ? `&customer_lat=${lat}&customer_lng=${lng}` : ''}`).then(r => r.json()),
  restock: (storeId, sku, qty) => fetch(`${BASE}/dark_stores/${storeId}/restock`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sku, qty }),
  }).then(r => r.json()),
  kpis: () => fetch(`${BASE}/kpis`).then(r => r.json()),
  disrupt: (kind, target) => fetch(`${BASE}/disruptions/${kind}${target ? `?target=${target}` : ''}`, { method: 'POST' }).then(r => r.json()),
  reset: () => fetch(`${BASE}/reset`, { method: 'POST' }).then(r => r.json()),
};

export function connectWs(onMessage, path = '/ws', onStatus = () => {}) {
  return subscribeSocket(`${WS_BASE}${path}`, onMessage, onStatus);
}
