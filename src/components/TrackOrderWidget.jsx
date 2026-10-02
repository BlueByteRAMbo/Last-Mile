import React, { useEffect, useState } from 'react';
import { Package, ExternalLink } from 'lucide-react';
import { api } from '../api';

// The customer-facing surface (src/pages/CustomerTracker.jsx) lives at #track/<order-id> deliberately
// outside the ops chrome — a real customer never sees the map/KPI dashboard. This widget is the
// ops-side shortcut to open it for any live order, so it's not buried three clicks deep.
const TrackOrderWidget = () => {
  const [orders, setOrders] = useState([]);
  const [selected, setSelected] = useState('');
  const [open, setOpen] = useState(false);

  // Orders worth tracking first (rider on the road), finished ones last. The list refreshes while the
  // dropdown is open, and the user's pick is kept unless that order disappeared (e.g. after a reset).
  const RANK = { out_for_delivery: 0, packed: 1, packing: 2, assigned: 3, created: 4 };
  const rank = (o) => RANK[o.status] ?? 5;
  useEffect(() => {
    if (!open) return;
    let stop = false;
    const load = () => api.orders().then(list => {
      if (stop || !Array.isArray(list)) return;
      const sorted = [...list].sort((a, b) => rank(a) - rank(b));
      setOrders(sorted);
      setSelected(cur => (sorted.some(o => o.id === cur) ? cur : sorted[0]?.id || ''));
    }).catch(() => {});
    load();
    const t = setInterval(load, 3000);
    return () => { stop = true; clearInterval(t); };
  }, [open]);

  const openTracker = () => {
    if (!selected) return;
    window.open(`${window.location.origin}/#track/${selected}`, '_blank');
    setOpen(false);
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 text-sm font-medium cursor-pointer hover:bg-white/5 px-2 py-1 rounded text-slate-300 hover:text-white transition-colors"
        title="Open the customer-facing order tracker"
      >
        <Package size={15} /> Track Order
      </button>
      {open && (
        <div className="absolute top-full right-0 mt-2 w-80 max-w-[90vw] bg-route-panel/95 backdrop-blur-md border border-white/10 rounded-lg shadow-2xl p-3 z-20">
          <div className="text-[10px] text-slate-400 tracking-wider mb-2">CUSTOMER VIEW — pick an order</div>
          <select value={selected} onChange={e => setSelected(e.target.value)}
            className="w-full bg-white/5 text-xs text-white rounded px-2 py-1.5 border border-white/10 mb-2">
            {orders.length === 0 && <option value="">No orders yet</option>}
            {orders.map(o => (
              <option key={o.id} value={o.id}>{o.id} · {o.customer_name} · {o.status.replace(/_/g, ' ')}{o.priority ? ' ★' : ''}</option>
            ))}
          </select>
          <button onClick={openTracker} disabled={!selected}
            className="w-full flex items-center justify-center gap-1.5 text-xs font-medium bg-route-cyan/20 text-route-cyan hover:bg-route-cyan/30 transition-colors rounded px-3 py-2">
            <ExternalLink size={13} /> Open customer tracker
          </button>
        </div>
      )}
    </div>
  );
};

export default TrackOrderWidget;
