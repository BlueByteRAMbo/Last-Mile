import React from 'react';
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid } from 'recharts';

const StatCard = ({ label, value, accent }) => (
  <div className="bg-black/30 rounded-lg p-3 border border-white/10">
    <div className="text-[10px] text-slate-400 tracking-wider mb-1">{label}</div>
    <div className={`text-xl font-bold ${accent || 'text-white'}`}>{value}</div>
  </div>
);

const AnalyticsPanel = ({ kpis, riders }) => {
  if (!kpis) return null;
  const zoneData = kpis.zone_density.map(z => ({ zone: z.zone, orders: z.count }));
  const riderUtil = riders.map(r => ({ name: r.name.replace('Rider ', 'R'), util: r.utilization })).slice(0, 15);

  return (
    <div className="absolute top-40 left-6 z-10 pointer-events-auto bg-route-panel/95 backdrop-blur-md rounded-lg border border-white/10 shadow-2xl w-[420px] max-h-[65vh] overflow-y-auto p-4">
      <h2 className="text-sm font-bold text-white mb-3">Performance Analytics</h2>

      <div className="grid grid-cols-3 gap-2 mb-4">
        <StatCard label="AVG DELIVERY" value={`${kpis.avg_delivery_minutes}m`} />
        <StatCard label="ON-TIME RATE" value={`${kpis.on_time_rate_pct}%`} accent="text-route-green" />
        <StatCard label="RIDER UTIL" value={`${kpis.rider_utilization_pct}%`} accent="text-route-cyan" />
        <StatCard label="SLA BREACH" value={`${kpis.sla_breach_rate_pct}%`} accent={kpis.sla_breach_rate_pct > 10 ? 'text-route-red' : 'text-white'} />
        <StatCard label="DELIVERED" value={kpis.delivered_count} />
        <StatCard label="FAILED/CANCELLED" value={kpis.failed_count} accent={kpis.failed_count > 0 ? 'text-route-amber' : 'text-white'} />
      </div>

      <div className="mb-4">
        <div className="text-[10px] text-slate-400 tracking-wider mb-2">ZONE DEMAND DENSITY</div>
        <ResponsiveContainer width="100%" height={140}>
          <BarChart data={zoneData} layout="vertical" margin={{ left: 10, right: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 9, fill: '#94a3b8' }} allowDecimals={false} />
            <YAxis type="category" dataKey="zone" tick={{ fontSize: 8, fill: '#94a3b8' }} width={80} />
            <Tooltip contentStyle={{ background: '#0a0e14', border: '1px solid #ffffff20', fontSize: 11 }} />
            <Bar dataKey="orders" fill="#38BDF8" radius={[0, 3, 3, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div>
        <div className="text-[10px] text-slate-400 tracking-wider mb-2">RIDER UTILIZATION</div>
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={riderUtil} margin={{ left: -20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 8, fill: '#94a3b8' }} />
            <YAxis tick={{ fontSize: 9, fill: '#94a3b8' }} domain={[0, 100]} />
            <Tooltip contentStyle={{ background: '#0a0e14', border: '1px solid #ffffff20', fontSize: 11 }} />
            <Bar dataKey="util" fill="#34D399" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default AnalyticsPanel;
