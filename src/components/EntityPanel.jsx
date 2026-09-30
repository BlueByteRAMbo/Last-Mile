import React, { useEffect, useState } from 'react';
import { X, Navigation, Package, Battery, Clock, TrendingUp } from 'lucide-react';
import { api } from '../api';

const riskColor = (risk) => ({
  SEVERE: 'text-route-red', DELAYED: 'text-route-red', AT_RISK: 'text-route-amber',
}[risk] || 'text-route-green');

const EntityPanel = ({ entity, onClose }) => {
  const [explain, setExplain] = useState(null);

  useEffect(() => {
    setExplain(null);
    if (entity?.type === 'ORDER') {
      api.explainOrder(entity.id).then(setExplain).catch(() => {});
    }
  }, [entity?.id, entity?.type]);

  if (!entity) return null;

  return (
    <div className="absolute top-24 right-6 z-10 pointer-events-auto bg-route-panel/95 backdrop-blur-md p-5 rounded-lg border border-white/10 shadow-2xl w-80 max-h-[75vh] overflow-y-auto">
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
                entity.data.status === 'AVAILABLE' ? 'text-route-green' :
                entity.data.status === 'ON_DELIVERY' ? 'text-route-cyan' : 'text-slate-500'
              }`}>{entity.data.status.replace('_', ' ')}</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400 flex items-center gap-2"><Package size={14}/> Load</span>
              <span className="text-sm font-medium text-white">{entity.data.current_load_kg?.toFixed(1)} / {entity.data.capacity_kg} kg</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400 flex items-center gap-2"><Battery size={14}/> Battery</span>
              <span className="text-sm font-medium text-white">{entity.data.battery_pct}%</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400 flex items-center gap-2"><TrendingUp size={14}/> Utilization</span>
              <span className="text-sm font-medium text-white">{entity.data.utilization || 0}%</span>
            </div>
            <div className="mt-2 w-full bg-white/10 rounded-full h-1.5">
              <div className="bg-route-cyan h-1.5 rounded-full" style={{ width: `${entity.data.utilization || 0}%` }}></div>
            </div>
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
