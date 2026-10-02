import React from 'react';

const NetworkStatus = ({ kpis, orders = [], riders = [] }) => {
  const atRisk = orders.filter(o => o.risk === 'AT_RISK' || o.risk === 'DELAYED' || o.risk === 'SEVERE').length;
  const activeRiders = riders.filter(r => r.status !== 'OFFLINE').length;

  return (
    <div className="hidden md:block absolute bottom-6 right-6 z-10 pointer-events-auto bg-route-base/80 backdrop-blur-md p-5 rounded-lg border border-white/5 shadow-lg w-64">
      <h3 className="text-xs font-semibold text-slate-400 tracking-wider mb-4">NETWORK STATUS</h3>

      <div className="flex flex-col gap-3">
        <div className="flex justify-between items-center">
          <span className="text-sm text-slate-300">Active Riders</span>
          <span className="text-sm font-medium text-white">{activeRiders}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-sm text-slate-300">Active Orders</span>
          <span className="text-sm font-medium text-white">{orders.length}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-sm text-slate-300">Orders At Risk</span>
          <span className="text-sm font-medium text-route-red">{atRisk}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-sm text-slate-300">Avg Delivery</span>
          <span className="text-sm font-medium text-white">{kpis?.avg_delivery_minutes != null ? `${kpis.avg_delivery_minutes}m` : '—'}</span>
        </div>

        <div className="w-full h-px bg-white/10 my-1"></div>

        <div className="flex justify-between items-center">
          <span className="text-sm font-medium text-slate-300">On-time rate</span>
          <span className="text-sm font-bold text-route-green">{kpis?.on_time_rate_pct != null ? `${kpis.on_time_rate_pct}%` : '—'}</span>
        </div>
      </div>
    </div>
  );
};

export default NetworkStatus;
