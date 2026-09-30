import React from 'react';
import { api } from '../../api';

const statusColor = (s) => ({
  AVAILABLE: 'text-route-green', ON_DELIVERY: 'text-route-cyan', OFFLINE: 'text-slate-500',
}[s] || 'text-slate-300');

const RidersPanel = ({ riders, onSelect }) => (
  <div className="absolute top-40 left-6 z-10 pointer-events-auto bg-route-panel/95 backdrop-blur-md rounded-lg border border-white/10 shadow-2xl w-96 max-h-[65vh] flex flex-col">
    <div className="p-4 pb-2 border-b border-white/10 flex justify-between items-center">
      <h2 className="text-sm font-bold text-white">Riders ({riders.length})</h2>
      <span className="text-[10px] text-slate-500">{riders.filter(r => r.status === 'ON_DELIVERY').length} on delivery</span>
    </div>
    <div className="overflow-y-auto p-3 flex-1">
      {riders.map(r => (
        <div key={r.id} onClick={() => onSelect({ type: 'RIDER', id: r.id, name: r.name, data: r })}
          className="flex justify-between items-center py-2 px-2 rounded hover:bg-white/5 cursor-pointer border-b border-white/5 last:border-0 group">
          <div className="flex flex-col">
            <span className="text-xs font-medium text-white">{r.name}</span>
            <span className="text-[10px] text-slate-500">{r.current_load_kg?.toFixed(1)}/{r.capacity_kg} kg · {r.utilization}% util</span>
          </div>
          <div className="flex items-center gap-2">
            <span className={`text-[10px] font-semibold ${statusColor(r.status)}`}>{r.status.replace('_', ' ')}</span>
            {r.status !== 'OFFLINE' && (
              <button
                onClick={(e) => { e.stopPropagation(); api.disrupt('rider_offline', r.id); }}
                className="opacity-0 group-hover:opacity-100 text-[9px] text-route-red border border-route-red/40 rounded px-1.5 py-0.5 hover:bg-route-red/10 transition-opacity">
                drop
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  </div>
);

export default RidersPanel;
