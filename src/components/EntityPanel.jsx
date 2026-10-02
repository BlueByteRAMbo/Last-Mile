import React, { useEffect, useState } from 'react';
import { X, Navigation, Package, Battery, Clock, TrendingUp } from 'lucide-react';
import { api } from '../api';

const riskColor = (risk) => ({
  SEVERE: 'text-route-red', DELAYED: 'text-route-red', AT_RISK: 'text-route-amber',
}[risk] || 'text-route-green');

const PHASE = { to_store: 'Heading to store to pick up', to_customer: 'Delivering to customer', idle: 'Idle — no active leg' };
const fmtEta = (s) => s == null ? '—' : s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;

const RiderRouteDetail = ({ d }) => {
  if (!d) return <p className="text-xs text-slate-500 pt-3">Loading route…</p>;
  return (
    <div className="mt-4 pt-3 border-t border-white/10 space-y-2">
      <div className="text-xs font-semibold text-slate-400 tracking-wider">CURRENT LEG</div>
      <div className="text-sm text-white">{PHASE[d.phase] || PHASE.idle}</div>
      {d.leg_to ? (
        <div className="text-xs space-y-1">
          <div className="flex gap-2"><span className="text-route-amber font-semibold w-10">FROM</span><span className="text-slate-300">{d.leg_from?.label}</span></div>
          <div className="flex gap-2"><span className="text-route-green font-semibold w-10">TO</span><span className="text-slate-300">{d.leg_to.label}</span></div>
          <div className="text-slate-400">{d.distance_remaining_km} km left · ETA {fmtEta(d.leg_eta_seconds)} · {d.speed_kmh} km/h</div>
        </div>
      ) : <p className="text-xs text-slate-500">Waiting for an order to be packed.</p>}
      <div className="text-xs font-semibold text-slate-400 tracking-wider pt-2">ORDERS ({d.orders.length})</div>
      {d.orders.length === 0 && <p className="text-xs text-slate-500">None</p>}
      {d.orders.map(o => (
        <div key={o.id} className="rounded bg-white/5 p-2 text-xs space-y-0.5">
          <div className="flex justify-between"><span className="text-white font-medium">{o.id}</span><span className="text-route-cyan">{o.status.replace(/_/g, ' ')}</span></div>
          <div className="text-slate-400">Picked up from: <span className="text-slate-200">{o.store?.name || '—'}</span>{o.picked_up_at ? ` at ${new Date(o.picked_up_at).toLocaleTimeString()}` : ' (not yet)'}</div>
          <div className="text-slate-400">Deliver to: <span className="text-slate-200">{o.customer_name}{o.address_label ? ` · ${o.address_label}` : ''}</span></div>
          <div className="text-slate-400">{o.items.map(i => `${i.qty}× ${i.sku.replace('SKU-', '')}`).join(', ')} · {o.weight_kg} kg</div>
          <div className="text-slate-400">Promised {new Date(o.promised_at).toLocaleTimeString()}</div>
        </div>
      ))}
    </div>
  );
};

const EntityPanel = ({ entity, riderDetail, onClose }) => {
  const [explain, setExplain] = useState(null);

  useEffect(() => {
    setExplain(null);
    if (entity?.type === 'ORDER') {
      api.explainOrder(entity.id).then(setExplain).catch(() => {});
    }
  }, [entity?.id, entity?.type]);

  if (!entity) return null;
  // entity.data is a snapshot from the moment of the click; the polled detail is live
  const rider = entity.type === 'RIDER' ? { ...entity.data, ...(riderDetail || {}) } : null;

  return (
    <div className="absolute top-24 right-6 z-30 pointer-events-auto bg-route-panel/95 backdrop-blur-md p-5 rounded-lg border border-white/10 shadow-2xl w-80 max-h-[calc(100%-7rem)] overflow-y-auto">
      <div className="flex justify-between items-start mb-4">
        <div>
          <h2 className="text-lg font-bold text-white mb-0.5">{entity.name || entity.id}</h2>
          <span className="text-xs font-semibold text-slate-400 tracking-wider">
            {entity.type.replace('_', ' ')}
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-white transition-colors bg-white/5 hover:bg-white/10 p-1.5 rounded-md"
        >
          <X size={16} />
        </button>
      </div>

      <div className="space-y-3">
        {entity.type === 'RIDER' && (
          <>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400 flex items-center gap-2"><Navigation size={14}/> Status</span>
              <span className={`text-sm font-medium ${
                rider.status === 'AVAILABLE' ? 'text-route-green' :
                rider.status === 'ON_DELIVERY' ? 'text-route-cyan' : 'text-slate-500'
              }`}>{rider.status.replace('_', ' ')}</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400 flex items-center gap-2"><Package size={14}/> Load</span>
              <span className="text-sm font-medium text-white">{rider.current_load_kg?.toFixed(1)} / {rider.capacity_kg} kg</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400 flex items-center gap-2"><Battery size={14}/> Battery</span>
              <span className="text-sm font-medium text-white">{rider.battery_pct}%</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400 flex items-center gap-2"><TrendingUp size={14}/> Utilization</span>
              <span className="text-sm font-medium text-white">{rider.utilization || 0}%</span>
            </div>
            <div className="mt-2 w-full bg-white/10 rounded-full h-1.5">
              <div className="bg-route-cyan h-1.5 rounded-full" style={{ width: `${rider.utilization || 0}%` }}></div>
            </div>
            <RiderRouteDetail d={riderDetail} />
          </>
        )}

        {entity.type === 'DARK_STORE' && (
          <>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400">Queued (awaiting pack)</span>
              <span className="text-sm font-medium text-white">{entity.data.queued}</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400">Packing now</span>
              <span className="text-sm font-medium text-white">{entity.data.packing_now} / {entity.data.packing_capacity}</span>
            </div>
            <div className="mt-2 w-full bg-white/10 rounded-full h-1.5">
              <div className="bg-route-green h-1.5 rounded-full" style={{ width: `${Math.min(100, 100 * entity.data.packing_now / entity.data.packing_capacity)}%` }}></div>
            </div>
          </>
        )}

        {entity.type === 'ORDER' && (
          <>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400">Status</span>
              <span className="text-sm font-medium text-slate-300">{entity.data.status?.replace('_', ' ')}</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400">Risk</span>
              <span className={`text-sm font-medium ${riskColor(entity.data.risk)}`}>{entity.data.risk}</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400">Promised</span>
              <span className="text-sm font-medium text-white">{new Date(entity.data.promised_at).toLocaleTimeString()}</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400">Rider</span>
              <span className="text-sm font-medium text-route-cyan">{entity.data.rider_id || '—'}</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400">Dark Store</span>
              <span className="text-sm font-medium text-white">{entity.data.store_id || '—'}</span>
            </div>

            {explain?.decision?.chosen && (
              <div className="mt-4 pt-3 border-t border-white/10">
                <div className="text-xs font-semibold text-slate-400 tracking-wider mb-2">WHY THIS RIDER?</div>
                <div className="text-sm text-white mb-1">
                  {explain.decision.chosen.rider_name} via {explain.decision.chosen.store_name}
                </div>
                <div className="text-xs text-slate-400 space-y-0.5 mb-2">
                  <div>ETA: {Math.round(explain.decision.chosen.reason.eta_seconds / 60)}m · Deadline slack: {Math.round(explain.decision.chosen.reason.deadline_slack_seconds / 60)}m</div>
                  <div>Workload penalty: {explain.decision.chosen.reason.workload_penalty} · Batching benefit: {explain.decision.chosen.reason.batching_benefit}</div>
                  <div>Score: {explain.decision.chosen.cost}</div>
                </div>
                {explain.decision.alternatives?.length > 0 && (
                  <>
                    <div className="text-xs font-semibold text-slate-400 tracking-wider mb-1">RANKED ALTERNATIVES</div>
                    <div className="space-y-1">
                      {explain.decision.alternatives.map((alt, i) => (
                        <div key={i} className="flex justify-between text-xs text-slate-400">
                          <span>{alt.rider_name} · {alt.store_name}</span>
                          <span>{alt.cost}</span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default EntityPanel;
