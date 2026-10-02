import { subscribeSocket } from './socket';

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const WS_BASE = BASE.replace(/^http/, 'ws');

// Custom header on every state-changing call: the backend requires it on operator endpoints, and a
// browser cannot send it cross-site without a CORS preflight that the server's origin allow-list refuses.
const OPS_HEADERS = { 'X-Ops-Request': '1', ...(import.meta.env.VITE_OPS_TOKEN ? { 'X-Ops-Token': import.meta.env.VITE_OPS_TOKEN } : {}) };

// Every call goes through here: a failed or non-JSON response becomes a thrown Error with a readable
// message, never an error object or HTML quietly handed to code that expects an array.
async function parse(response) {
  let data = null;
  try { data = await response.json(); } catch { /* empty or non-JSON body */ }
  if (!response.ok) {
    const detail = data?.detail;
    const message = typeof detail === 'string' ? detail
      : Array.isArray(detail) ? detail.map(d => d.msg).filter(Boolean).join('; ')
      : '';
    const error = new Error(message || `Request failed (${response.status}). Please check your inputs.`);
    error.status = response.status;
    throw error;
  }
  return data;
}

const get = path => fetch(`${BASE}${path}`).then(parse);
const post = (path, body) => fetch(`${BASE}${path}`, {
  method: 'POST', headers: { 'Content-Type': 'application/json', ...OPS_HEADERS },
  body: body === undefined ? undefined : JSON.stringify(body),
}).then(parse);
// kept for the existing call shape: request(path) is a GET, request(path, body) a POST
const request = (path, body) => (body === undefined ? get(path) : post(path, body));

export const api = {
  dispatchMode: () => request('/dispatch/mode'),
  setDispatchMode: mode => request('/dispatch/mode', { mode }),
  simSpeed: () => request('/simulation/speed'),
  setSimSpeed: multiplier => request('/simulation/speed', { multiplier }),
  comparison: () => request('/analytics/comparison'),
  journey: id => request(`/orders/${encodeURIComponent(id)}/journey`),
  traffic: body => request(`/disruptions/traffic?${new URLSearchParams(body)}`, {}),
  interveneOrder: (id, action) => post(`/orders/${encodeURIComponent(id)}/intervene/${action}`),
  darkStores: () => get('/dark_stores'),
  storeInventory: id => get(`/dark_stores/${id}/inventory`),
  riders: () => get('/riders'),
  riderRoute: id => get(`/riders/${id}/route`),
  riderDetail: id => get(`/riders/${id}/detail`),
  orders: status => get(`/orders${status ? `?status=${status}` : ''}`),
  explainOrder: id => get(`/orders/${id}/explain`),
  track: id => request(`/track/${encodeURIComponent(id)}`),
  createOrder: body => request('/orders', body),
  catalog: () => get('/catalog'),
  catalogAvailability: (skus, lat, lng) => get(`/catalog/availability?skus=${skus.join(',')}${lat != null ? `&customer_lat=${lat}&customer_lng=${lng}` : ''}`),
  restock: (storeId, sku, qty) => post(`/dark_stores/${storeId}/restock`, { sku, qty }),
  kpis: () => get('/kpis'),
  disrupt: (kind, target) => post(`/disruptions/${kind}${target ? `?target=${encodeURIComponent(target)}` : ''}`),
  reset: () => post('/reset'),
};

export function connectWs(onMessage, path = '/ws', onStatus = () => {}) {
  return subscribeSocket(`${WS_BASE}${path}`, onMessage, onStatus);
}
