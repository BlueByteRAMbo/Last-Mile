import React, { useEffect, useState } from 'react';
import { Plus, X } from 'lucide-react';
import { api } from '../../api';

const statusColor = (risk) => ({
  SEVERE: 'text-route-red', DELAYED: 'text-route-red', AT_RISK: 'text-route-amber',
}[risk] || 'text-route-green');

const NewOrderForm = ({ onClose, onCreated }) => {
  const [catalog, setCatalog] = useState([]);
  const [sku, setSku] = useState('');
  const [qty, setQty] = useState(1);
  const [lat, setLat] = useState(19.06);
  const [lng, setLng] = useState(72.85);
  const [priority, setPriority] = useState(false);
  const [promiseMin, setPromiseMin] = useState(20);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  useEffect(() => { api.catalog().then(c => { setCatalog(c); if (c[0]) setSku(c[0].sku); }).catch(() => setFormError('Could not load the catalog.')); }, []);

  const submit = async () => {
    if (!sku) return;
    setSubmitting(true); setFormError('');
    const item = catalog.find(c => c.sku === sku);
    try {
      await api.createOrder({
        customer_lat: Number(lat), customer_lng: Number(lng),
        items: [{ sku, name: item?.name || sku, qty: Number(qty), weight_kg: item?.weight_kg || 0.3 }],
        priority, promise_minutes: Number(promiseMin),
      });
      onCreated();
      onClose();
    } catch (e) {
      setFormError(e.message);  // e.g. location in the water, basket too heavy, quantity out of range
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="bg-black/30 rounded-lg p-4 mb-3 border border-white/10 space-y-2">
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs font-semibold text-slate-300 tracking-wide">PLACE NEW ORDER</span>
        <button onClick={onClose}><X size={14} className="text-slate-400 hover:text-white" /></button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <select value={sku} onChange={e => setSku(e.target.value)} className="bg-white/5 text-xs text-white rounded px-2 py-1.5 border border-white/10">
          {catalog.map(c => <option key={c.sku} value={c.sku}>{c.name}</option>)}
        </select>
        <input type="number" min="1" max="20" value={qty} onChange={e => setQty(e.target.value)} placeholder="Qty"
          className="bg-white/5 text-xs text-white rounded px-2 py-1.5 border border-white/10" />
        <input type="number" step="0.001" value={lat} onChange={e => setLat(e.target.value)} placeholder="Lat"
          className="bg-white/5 text-xs text-white rounded px-2 py-1.5 border border-white/10" />
        <input type="number" step="0.001" value={lng} onChange={e => setLng(e.target.value)} placeholder="Lng"
          className="bg-white/5 text-xs text-white rounded px-2 py-1.5 border border-white/10" />
        <input type="number" min="5" max="120" value={promiseMin} onChange={e => setPromiseMin(e.target.value)} placeholder="Promise (min)"
          className="bg-white/5 text-xs text-white rounded px-2 py-1.5 border border-white/10" />
        <label className="flex items-center gap-2 text-xs text-slate-300">
          <input type="checkbox" checked={priority} onChange={e => setPriority(e.target.checked)} /> Express / Priority
        </label>
      </div>
      {formError && <p role="alert" className="text-xs text-route-red">{formError}</p>}
      <button onClick={submit} disabled={submitting}
        className="w-full mt-1 text-xs font-medium bg-route-cyan/20 text-route-cyan hover:bg-route-cyan/30 transition-colors rounded px-3 py-2 disabled:opacity-50">
        {submitting ? 'Placing…' : 'Place Order'}
      </button>
    </div>
  );
};

const OrdersPanel = ({ orders, onSelect }) => {
  const [filter, setFilter] = useState('QUEUE');
  const [showForm, setShowForm] = useState(false);
  const [pending, setPending] = useState(null);
  const [notice, setNotice] = useState('');
  const [updated, setUpdated] = useState({});
  useEffect(() => setUpdated({}), [orders]);
  const intervene = async (order, action) => {
    setPending(order.id);
    setNotice('');
    try {
      if (action === 'cancel' && !window.confirm(`Cancel order ${order.id}? This cannot be undone.`)) { setPending(null); return; }
      const result = await api.interveneOrder(order.id, action);
      setUpdated(previous => ({ ...previous, [order.id]: result }));
      setNotice(`${order.id}: ${action === 'boost' ? 'priority boosted' : action === 'reassign' ? `reassigned to ${result.rider_id}` : 'cancelled'}`);
    } catch (error) {
      setNotice(error.message);
    } finally {
      setPending(null);
    }
  };

  const active = o => !['delivered', 'failed', 'cancelled'].includes(o.status);
  const atRisk = o => active(o) && (o.predicted_late || ['AT_RISK', 'DELAYED', 'SEVERE'].includes(o.risk));
  const current = orders.map(o => ({ ...o, ...updated[o.id] }));
  const filtered = current.filter(o => filter === 'QUEUE' ? active(o) : filter === 'AT RISK' ? atRisk(o) : filter === 'ALL' || o.status === filter)
    .sort((a, b) => (b.priority_score || 0) - (a.priority_score || 0) || a.id.localeCompare(b.id));
  const statuses = ['QUEUE', 'AT RISK', 'ALL', 'created', 'assigned', 'packing', 'packed', 'out_for_delivery'];

  return (
    <div className="absolute top-56 md:top-40 left-3 md:left-6 max-w-[calc(100vw-1.5rem)] z-10 pointer-events-auto bg-route-panel/95 backdrop-blur-md rounded-lg border border-white/10 shadow-2xl w-96 max-h-[65vh] flex flex-col">
      <div className="p-4 pb-2 border-b border-white/10 flex justify-between items-center">
        <h2 className="text-sm font-bold text-white">Orders ({orders.length})</h2>
        <button onClick={() => setShowForm(s => !s)} className="text-route-cyan hover:text-white flex items-center gap-1 text-xs font-medium">
          <Plus size={14} /> New
        </button>
      </div>
      <div className="p-3 pb-0">
        {showForm && <NewOrderForm onClose={() => setShowForm(false)} onCreated={() => setNotice('Order placed; awaiting live update.')} />}
        <p className="text-[10px] text-slate-400 mb-2">Priority queue: urgency + express + overdue minutes. {current.filter(atRisk).length} at risk.</p>
        {notice && <p role="status" className="text-xs text-route-amber mb-2">{notice}</p>}
        <div className="flex gap-1 flex-wrap mb-2">
          {statuses.map(s => (
            <button key={s} onClick={() => setFilter(s)}
              className={`text-[10px] px-2 py-1 rounded-full border ${filter === s ? 'bg-route-cyan/20 text-route-cyan border-route-cyan/40' : 'text-slate-400 border-white/10 hover:text-white'}`}>
              {s}
            </button>
          ))}
        </div>
      </div>
      <div className="overflow-y-auto px-3 pb-3 flex-1">
        {filtered.length === 0 && <div className="text-xs text-slate-500 py-4 text-center">No orders</div>}
        {filtered.map(o => (
          <div key={o.id} onClick={() => onSelect({ type: 'ORDER', id: o.id, name: `Order ${o.id}`, data: o })}
            className="flex flex-wrap justify-between items-center py-2 px-2 rounded hover:bg-white/5 cursor-pointer border-b border-white/5 last:border-0">
            <div className="flex flex-col">
              <span className="text-xs font-medium text-white">{o.id}{o.priority && <span className="text-route-cyan ml-1">★</span>}</span>
              <span className="text-[10px] text-slate-500">{o.status.replace('_', ' ')} · {o.rider_id || 'unassigned'}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className={`text-[10px] font-semibold ${statusColor(o.risk)}`}>{o.risk}</span>
              <a href={`#track/${o.id}`} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
                className="text-[9px] text-slate-400 border border-white/10 rounded px-1.5 py-0.5 hover:text-white hover:border-white/30">
                track
              </a>
            </div>
            <div className="w-full text-[10px] text-slate-400 mt-1">
              {o.customer_name || 'Customer'} · ETA {o.eta_seconds == null ? 'pending' : `${Math.ceil(o.eta_seconds / 60)} min`} · Score {o.priority_score ?? '—'}
              {o.predicted_late && <span className="text-route-red ml-1">Predicted late</span>}
            </div>
            {active(o) && <div className="w-full flex gap-2 mt-2" onClick={e => e.stopPropagation()}>
              {['boost', 'reassign', 'cancel'].map(action => <button key={action}
                disabled={pending !== null || (action === 'boost' && o.priority) || (action === 'reassign' && !['assigned', 'packing', 'packed'].includes(o.status))}
                onClick={() => intervene(o, action)}
                className="text-[10px] px-2 py-1 rounded border border-white/20 text-slate-300 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed">
                {action === 'boost' ? 'Boost priority' : action === 'reassign' ? 'Reassign' : 'Cancel'}
              </button>)}
            </div>}
          </div>
        ))}
      </div>
    </div>
  );
};

export default OrdersPanel;
