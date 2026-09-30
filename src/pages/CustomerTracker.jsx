import React, { useEffect, useState } from 'react';
import { Package, CheckCircle2, Circle, AlertTriangle, MapPin, Clock } from 'lucide-react';
import { api } from '../api';

const riskBanner = (risk) => {
  if (risk === 'SEVERE') return { text: 'This order is significantly delayed.', cls: 'bg-route-red/15 text-route-red border-route-red/30' };
  if (risk === 'DELAYED') return { text: 'This order is running late.', cls: 'bg-route-red/15 text-route-red border-route-red/30' };
  if (risk === 'AT_RISK') return { text: 'This order is at risk of missing its promised time.', cls: 'bg-route-amber/15 text-route-amber border-route-amber/30' };
  return null;
};

const CustomerTracker = ({ orderId }) => {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => api.track(orderId).then(d => { if (!cancelled) { setData(d); setError(null); } })
      .catch(() => { if (!cancelled) setError('Order not found.'); });
    load();
    const t = setInterval(load, 3000);
    return () => { cancelled = true; clearInterval(t); };
  }, [orderId]);

  if (error) {
    return (
      <div className="w-full h-screen flex items-center justify-center bg-route-base text-white">
        <div className="text-center">
          <AlertTriangle className="mx-auto mb-3 text-route-amber" size={32} />
          <p className="text-slate-300">{error}</p>
          <p className="text-slate-500 text-sm mt-1">Order ID: {orderId}</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return <div className="w-full h-screen flex items-center justify-center bg-route-base text-slate-400">Loading…</div>;
  }

  const banner = riskBanner(data.risk);
  const isTerminal = data.status === 'delivered' || data.status === 'cancelled' || data.status === 'failed';

  return (
    <div className="w-full min-h-screen bg-route-base text-white p-6 flex flex-col items-center">
      <div className="w-full max-w-md">
        <div className="mb-6">
          <div className="text-xs text-slate-500 tracking-wider mb-1">ORDER {data.order_id}</div>
          <h1 className="text-2xl font-bold">{data.status_label}</h1>
          {data.priority && <span className="inline-block mt-1 text-xs text-route-cyan">★ Express delivery</span>}
        </div>

        {banner && (
          <div className={`mb-5 px-3 py-2 rounded-lg border text-sm flex items-center gap-2 ${banner.cls}`}>
            <AlertTriangle size={16} /> {banner.text}
          </div>
        )}

        {!isTerminal && data.eta_seconds != null && (
          <div className="mb-6 bg-route-panel/70 border border-white/10 rounded-lg p-4 flex items-center gap-3">
            <Clock className="text-route-cyan" size={22} />
            <div>
              <div className="text-xs text-slate-400">Estimated arrival</div>
              <div className="text-lg font-bold">{Math.max(0, Math.round(data.eta_seconds / 60))} min</div>
            </div>
          </div>
        )}

        <div className="space-y-0 mb-6">
          {data.stages.map((stage, i) => (
            <div key={stage.key} className="flex gap-3">
              <div className="flex flex-col items-center">
                {stage.done ? <CheckCircle2 className="text-route-green" size={20} /> : <Circle className="text-slate-600" size={20} />}
                {i < data.stages.length - 1 && <div className={`w-0.5 flex-1 min-h-[24px] ${stage.done ? 'bg-route-green/50' : 'bg-white/10'}`}></div>}
              </div>
              <div className="pb-6">
                <div className={`text-sm font-medium ${stage.done ? 'text-white' : 'text-slate-500'}`}>{stage.label}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="bg-route-panel/50 border border-white/10 rounded-lg p-4 space-y-2 text-sm">
          <div className="flex justify-between text-slate-400">
            <span className="flex items-center gap-1.5"><Package size={14} /> Items</span>
            <span className="text-white text-right">{data.items.map(it => `${it.qty}× ${it.name}`).join(', ')}</span>
          </div>
          {data.store_name && (
            <div className="flex justify-between text-slate-400">
              <span className="flex items-center gap-1.5"><MapPin size={14} /> From</span>
              <span className="text-white">{data.store_name}</span>
            </div>
          )}
          <div className="flex justify-between text-slate-400">
            <span>Promised by</span>
            <span className="text-white">{new Date(data.promised_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
          </div>
          {data.delivered_at && (
            <div className="flex justify-between text-slate-400">
              <span>Delivered at</span>
              <span className="text-route-green">{new Date(data.delivered_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default CustomerTracker;
