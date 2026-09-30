import React, { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { api } from '../../api';

const StoresPanel = ({ darkStores, onSelect }) => {
  const [expanded, setExpanded] = useState(null);
  const [inventory, setInventory] = useState({});

  const toggle = async (store) => {
    if (expanded === store.id) { setExpanded(null); return; }
    setExpanded(store.id);
    if (!inventory[store.id]) {
      const inv = await api.storeInventory(store.id);
      setInventory(prev => ({ ...prev, [store.id]: inv }));
    }
  };

  return (
    <div className="absolute top-40 left-6 z-10 pointer-events-auto bg-route-panel/95 backdrop-blur-md rounded-lg border border-white/10 shadow-2xl w-96 max-h-[65vh] flex flex-col">
      <div className="p-4 pb-2 border-b border-white/10">
        <h2 className="text-sm font-bold text-white">Dark Stores ({darkStores.length})</h2>
      </div>
      <div className="overflow-y-auto p-3 flex-1">
        {darkStores.map(s => (
          <div key={s.id} className="border-b border-white/5 last:border-0">
            <div className="flex justify-between items-center py-2 px-2 rounded hover:bg-white/5 cursor-pointer" onClick={() => toggle(s)}>
              <div className="flex items-center gap-1.5">
                {expanded === s.id ? <ChevronDown size={12} className="text-slate-500" /> : <ChevronRight size={12} className="text-slate-500" />}
                <span className="text-xs font-medium text-white">{s.name}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-[10px] text-slate-400">Pack {s.packing_now}/{s.packing_capacity}</span>
                <span className="text-[10px] text-slate-400">Queue {s.queued}</span>
                <button
                  onClick={(e) => { e.stopPropagation(); onSelect({ type: 'DARK_STORE', id: s.id, name: s.name, data: s }); api.disrupt('stockout', s.id); }}
                  className="text-[9px] text-route-amber border border-route-amber/40 rounded px-1.5 py-0.5 hover:bg-route-amber/10">
                  stockout
                </button>
              </div>
            </div>
            {expanded === s.id && (
              <div className="pl-6 pb-2 space-y-1">
                {(inventory[s.id] || []).map(item => (
                  <div key={item.sku} className="flex justify-between text-[10px] text-slate-400">
                    <span>{item.name}</span>
                    <span className={item.available === 0 ? 'text-route-red' : 'text-slate-300'}>{item.available} / {item.qty} available</span>
                  </div>
                ))}
                {!inventory[s.id] && <div className="text-[10px] text-slate-500">Loading…</div>}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default StoresPanel;
