import React from 'react';
import { X, Navigation, Package, Battery, Clock, TrendingUp } from 'lucide-react';

const EntityPanel = ({ entity, onClose }) => {
  if (!entity) return null;

  return (
    <div className="absolute top-24 right-6 z-10 pointer-events-auto bg-route-panel/95 backdrop-blur-md p-5 rounded-lg border border-white/10 shadow-2xl w-72">
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
                entity.data.status === 'ON_DELIVERY' ? 'text-route-cyan' : 
                entity.data.status === 'NEAR_CAPACITY' ? 'text-route-amber' : 'text-slate-500'
              }`}>{entity.data.status.replace('_', ' ')}</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400 flex items-center gap-2"><Package size={14}/> Load</span>
              <span className="text-sm font-medium text-white">{entity.data.currentLoad} / {entity.data.capacity}</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400 flex items-center gap-2"><Clock size={14}/> ETA</span>
              <span className="text-sm font-medium text-white">{entity.data.eta || 'N/A'}</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400 flex items-center gap-2"><TrendingUp size={14}/> Utilization</span>
              <span className="text-sm font-medium text-white">{entity.data.utilization || 0}%</span>
            </div>
            <div className="mt-2 w-full bg-white/10 rounded-full h-1.5">
              <div 
                className="bg-route-cyan h-1.5 rounded-full" 
                style={{ width: `${entity.data.utilization || 0}%` }}
              ></div>
            </div>
          </>
        )}

        {entity.type === 'ORDER' && (
          <>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400">Status</span>
              <span className={`text-sm font-medium ${
                entity.data.status === 'AT_RISK' ? 'text-route-amber' : 
                entity.data.status === 'DELAYED' ? 'text-route-red' : 
                entity.data.status === 'PRIORITY' ? 'text-route-cyan' : 'text-slate-300'
              }`}>{entity.data.status.replace('_', ' ')}</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400">ETA</span>
              <span className="text-sm font-medium text-white">{entity.data.eta}</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400">Promise</span>
              <span className="text-sm font-medium text-white">{entity.data.promise}</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400">Rider</span>
              <span className="text-sm font-medium text-route-cyan">{entity.data.rider}</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400">Dark Store</span>
              <span className="text-sm font-medium text-white">{entity.data.darkStore}</span>
            </div>
          </>
        )}

        {entity.type === 'DARK_STORE' && (
          <>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400">Orders queued</span>
              <span className="text-sm font-medium text-white">{entity.data.ordersQueued}</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400">Packing</span>
              <span className="text-sm font-medium text-white">{entity.data.packing}</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400">Available riders</span>
              <span className="text-sm font-medium text-route-cyan">{entity.data.availableRiders}</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-sm text-slate-400">Capacity</span>
              <span className="text-sm font-medium text-white">{entity.data.capacity}%</span>
            </div>
            <div className="mt-2 w-full bg-white/10 rounded-full h-1.5">
              <div 
                className="bg-route-green h-1.5 rounded-full" 
                style={{ width: `${entity.data.capacity}%` }}
              ></div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default EntityPanel;
