import React from 'react';

const KPIBar = ({ kpis, orders = [], riders = [] }) => {
  const atRisk = orders.filter(o => o.risk === 'AT_RISK' || o.risk === 'DELAYED' || o.risk === 'SEVERE').length;
  const activeRiders = riders.filter(r => r.status !== 'OFFLINE').length;

  const items = [
    { label: 'ACTIVE ORDERS', value: String(orders.length), highlight: false },
    { label: 'AT RISK', value: String(atRisk), highlight: atRisk > 0 },
    { label: 'ACTIVE RIDERS', value: String(activeRiders), highlight: false },
    { label: 'AVG DELIVERY', value: kpis?.avg_delivery_minutes != null ? `${kpis.avg_delivery_minutes}m` : '—', highlight: false },
    { label: 'ON-TIME', value: kpis?.on_time_rate_pct != null ? `${kpis.on_time_rate_pct}%` : '—', highlight: false },
  ];

  return (
    <div className="absolute top-44 md:top-20 left-0 w-full z-10 flex justify-center pointer-events-none px-2">
      <div className="flex gap-3 md:gap-8 pointer-events-auto bg-route-base/70 backdrop-blur-md px-4 md:px-8 py-2.5 rounded-2xl md:rounded-full max-w-full overflow-x-auto border border-white/5 shadow-lg">
        {items.map((kpi, idx) => (
          <div key={idx} className="flex flex-col items-center">
            <div className="text-[10px] font-semibold text-slate-400 tracking-wider mb-0.5">{kpi.label}</div>
            <div className={`text-sm font-bold tracking-wide ${kpi.highlight ? 'text-route-red' : 'text-slate-200'}`}>
              {kpi.value}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default KPIBar;
