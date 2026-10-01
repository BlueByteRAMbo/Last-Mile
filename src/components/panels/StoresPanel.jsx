import React, { useState } from 'react';
import { ChevronDown, ChevronRight, PackagePlus } from 'lucide-react';
import { api } from '../../api';

const StoresPanel = ({ darkStores, onSelect }) => {
  const [expanded, setExpanded] = useState(null);
  const [inventory, setInventory] = useState({});
  const [restocking, setRestocking] = useState(null);

  const loadInventory = async (storeId) => {
    const inv = await api.storeInventory(storeId);
    setInventory(prev => ({ ...prev, [storeId]: inv }));
  };

  const toggle = async (store) => {
    if (expanded === store.id) { setExpanded(null); return; }
    setExpanded(store.id);
    if (!inventory[store.id]) await loadInventory(store.id);
  };

  const restock = async (storeId, sku) => {
    setRestocking(sku);
    await api.restock(storeId, sku, 50);
    await loadInventory(storeId);
    setRestocking(null);
  };

  return (
    <div className="absolute top-40 left-6 z-10 pointer-events-auto bg-route-panel/95 backdrop-blur-md rounded-lg border border-white/10 shadow-2xl w-[26rem] max-h-[65vh] flex flex-col">
      <div className="p-4 pb-2 border-b border-white/10">
        <h2 className="text-sm font-bold text-white">Dark Stores ({darkStores.length})</h2>
      </div>
      <div className="overflow-y-auto p-3 flex-1">
        {darkStores.map(s => {
          const packingPct = Math.min(100, 100 * (s.packing_now || 0) / (s.packing_capacity || 1));
          const items = inventory[s.id] || [];
          const lowStockCount = items.filter(i => i.low_stock || i.out_of_stock).length;
          return (
            <div key={s.id} className="border-b border-white/5 last:border-0">
              <div className="py-2 px-2 rounded hover:bg-white/5 cursor-pointer" onClick={() => toggle(s)}>
                <div className="flex justify-between items-center mb-1.5">
                  <div className="flex items-center gap-1.5">
                    {expanded === s.id ? <ChevronDown size={12} className="text-slate-500" /> : <ChevronRight size={12} className="text-slate-500" />}
                    <span className="text-xs font-medium text-white">{s.name}</span>
                    {lowStockCount > 0 && (
                      <span className="text-[9px] text-route-amber bg-route-amber/10 border border-route-amber/30 rounded-full px-1.5">
                        {lowStockCount} low stock
                      </span>
                    )}
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); onSelect({ type: 'DARK_STORE', id: s.id, name: s.name, data: s }); api.disrupt('stockout', s.id); }}
                    className="text-[9px] text-route-amber border border-route-amber/40 rounded px-1.5 py-0.5 hover:bg-route-amber/10">
                    stockout
                  </button>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[9px] text-slate-500 w-20">Packing {s.packing_now}/{s.packing_capacity}</span>
                  <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${packingPct >= 100 ? 'bg-route-red' : packingPct >= 60 ? 'bg-route-amber' : 'bg-route-green'}`}
                      style={{ width: `${packingPct}%` }} />
                  </div>
                  <span className="text-[9px] text-slate-500">Queue {s.queued}</span>
                </div>
              </div>
              {expanded === s.id && (
                <div className="pl-6 pb-2 space-y-1">
                  {items.map(item => (
                    <div key={item.sku} className="flex justify-between items-center text-[10px] py-0.5">
                      <span className="text-slate-400 flex items-center gap-1">
                        <span>{item.emoji}</span> {item.name}
                        {item.out_of_stock && <span className="text-route-red text-[9px]">out of stock</span>}
                        {!item.out_of_stock && item.low_stock && <span className="text-route-amber text-[9px]">low</span>}
                      </span>
                      <span className="flex items-center gap-2">
                        <span className={item.out_of_stock ? 'text-route-red' : item.low_stock ? 'text-route-amber' : 'text-slate-300'}>
                          {item.available} / {item.qty}
                        </span>
                        <button onClick={() => restock(s.id, item.sku)} disabled={restocking === item.sku}
                          title="Restock +50"
                          className="text-slate-500 hover:text-route-cyan disabled:opacity-40">
                          <PackagePlus size={12} />
                        </button>
                      </span>
                    </div>
                  ))}
                  {!items.length && <div className="text-[10px] text-slate-500">Loading…</div>}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default StoresPanel;
