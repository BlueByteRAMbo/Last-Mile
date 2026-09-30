import React, { useEffect, useState } from 'react';
import { api } from '../../api';

const OptimizationPanel = ({ riders }) => {
  const busyRiders = riders.filter(r => r.status === 'ON_DELIVERY');
  const [riderId, setRiderId] = useState(null);
  const [route, setRoute] = useState(null);

  useEffect(() => {
    if (!riderId && busyRiders[0]) setRiderId(busyRiders[0].id);
  }, [busyRiders]);

  useEffect(() => {
    if (!riderId) return;
    const load = () => api.riderRoute(riderId).then(setRoute).catch(() => {});
    load();
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
  }, [riderId]);

  return (
    <div className="absolute top-40 left-6 z-10 pointer-events-auto bg-route-panel/95 backdrop-blur-md rounded-lg border border-white/10 shadow-2xl w-96 max-h-[65vh] flex flex-col">
      <div className="p-4 pb-2 border-b border-white/10">
        <h2 className="text-sm font-bold text-white mb-2">Route Optimization</h2>
        <select value={riderId || ''} onChange={e => setRiderId(e.target.value)}
          className="w-full bg-white/5 text-xs text-white rounded px-2 py-1.5 border border-white/10">
          {busyRiders.length === 0 && <option value="">No riders currently on delivery</option>}
          {busyRiders.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select>
      </div>
      <div className="overflow-y-auto p-3 flex-1">
        {!route?.stops?.length && <div className="text-xs text-slate-500 py-4 text-center">No active route for this rider</div>}
        {route?.stops?.map((stop, i) => (
          <div key={i} className="flex items-start gap-3 py-2 border-b border-white/5 last:border-0">
            <div className={`mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${stop.stop_type === 'PICKUP' ? 'bg-slate-300' : 'bg-route-cyan'}`}></div>
            <div className="flex-1">
              <div className="flex justify-between">
                <span className="text-xs font-medium text-white">{stop.stop_type === 'PICKUP' ? `Pickup · ${stop.store_id}` : `Drop · ${stop.order_id}`}</span>
                <span className="text-[10px] text-slate-400">ETA {Math.round(stop.eta_seconds / 60)}m</span>
              </div>
              <div className="text-[10px] text-slate-500">
                cum. load {stop.cumulative_load_kg}kg
                {stop.deadline_slack_seconds !== undefined && (
                  <span className={stop.deadline_slack_seconds < 0 ? 'text-route-red ml-2' : 'text-slate-500 ml-2'}>
                    slack {Math.round(stop.deadline_slack_seconds / 60)}m
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
      {route && (
        <div className="p-2 text-[10px] text-slate-500 border-t border-white/10 text-center">route v{route.route_version}</div>
      )}
    </div>
  );
};

export default OptimizationPanel;
