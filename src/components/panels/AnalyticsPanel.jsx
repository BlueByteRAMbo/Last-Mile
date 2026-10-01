import React from 'react';
import DispatchComparison from './DispatchComparison';
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid, ComposedChart, Line } from 'recharts';

const StatCard = ({ label, value, accent }) => (
  <div className="bg-black/30 rounded-lg p-3 border border-white/10">
    <div className="text-[10px] text-slate-400 tracking-wider mb-1">{label}</div>
    <div className={`text-xl font-bold ${accent || 'text-white'}`}>{value}</div>
  </div>
);

const AnalyticsPanel = ({ kpis }) => {
  if (!kpis) return null;
  const zoneData = kpis.zone_density.map(z => ({ zone: z.zone, orders: z.count }));
  const riderUtil = (kpis.rider_stats || []).map(r => ({ name: r.name.replace('Rider ', 'R'), util: r.utilization_pct, delivered: r.delivered_count }));
  const series = (kpis.on_time_series || []).map(point => ({ ...point,
    time: new Date(point.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }));

  return (
    <div className="absolute top-40 left-6 z-10 pointer-events-auto bg-route-panel/95 backdrop-blur-md rounded-lg border border-white/10 shadow-2xl w-[420px] max-h-[65vh] overflow-y-auto p-4">
      <h2 className="text-sm font-bold text-white mb-3">Performance Analytics</h2>
      <DispatchComparison />

      <div className="grid grid-cols-3 gap-2 mb-4">
        <StatCard label="AVG DELIVERY" value={`${kpis.avg_delivery_minutes}m`} />
        <StatCard label="ON-TIME RATE" value={`${kpis.on_time_rate_pct}%`} accent="text-route-green" />
        <StatCard label="RIDER UTIL" value={`${kpis.rider_utilization_pct}%`} accent="text-route-cyan" />
        <StatCard label="SLA BREACH" value={`${kpis.sla_breach_rate_pct}%`} accent={kpis.sla_breach_rate_pct > 10 ? 'text-route-red' : 'text-white'} />
        <StatCard label="DELIVERED" value={kpis.delivered_count} />
        <StatCard label="FAILED/CANCELLED" value={kpis.failed_count} accent={kpis.failed_count > 0 ? 'text-route-amber' : 'text-white'} />
        <StatCard label="OVERDUE NOW" value={kpis.delayed_count ?? 0} accent="text-route-red" />
        <StatCard label="FAILED" value={kpis.failure_count ?? 0} />
        <StatCard label="WORKLOAD GINI" value={kpis.workload_gini ?? 0} />
      </div>
      <p className="text-[10px] text-slate-400 mb-4">Gini: 0 means equal completed deliveries; 1 means maximum imbalance. Zero deliveries also gives 0.</p>

      <div className="mb-4">
        <div className="text-[10px] text-slate-400 tracking-wider mb-2">DEMAND BY NEAREST HUB CATCHMENT · ALL ORDERS</div>
        <p className="text-[10px] text-slate-500 mb-2">Map heatmap weights each hub by its catchment demand; it does not show individual delivery locations.</p>
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
        <div className="text-[10px] text-slate-400 tracking-wider mb-2">RIDER TIME UTILIZATION (%)</div>
        <p className="text-[10px] text-slate-500 mb-2">Busy assignment time / observed simulated shift time. Offline shift time counts as idle; server downtime is excluded.</p>
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
      <div className="mt-4">
        <div className="text-[10px] text-slate-400 tracking-wider mb-2">ON-TIME DELIVERIES · LAST HOUR</div>
        <p className="text-[10px] text-slate-500 mb-2">Green: on-time % per 5 minutes. Amber: disruption impact events (right axis). Empty delivery intervals have no rate.</p>
        <ResponsiveContainer width="100%" height={170}>
          <ComposedChart data={series} margin={{ left: -20, right: -15 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
            <XAxis dataKey="time" tick={{ fontSize: 8, fill: '#94a3b8' }} />
            <YAxis yAxisId="rate" domain={[0, 100]} tick={{ fontSize: 9, fill: '#94a3b8' }} />
            <YAxis yAxisId="events" orientation="right" allowDecimals={false} tick={{ fontSize: 9, fill: '#94a3b8' }} />
            <Tooltip contentStyle={{ background: '#0a0e14', border: '1px solid #ffffff20', fontSize: 11 }} />
            <Bar yAxisId="events" dataKey="disruptions" name="Disruption impacts" fill="#FBBF24" opacity={0.5} />
            <Line yAxisId="rate" dataKey="on_time_rate_pct" name="On-time %" stroke="#34D399" connectNulls={false} dot={{ r: 3 }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-4">
        <div className="text-[10px] text-slate-400 tracking-wider mb-2">DELAY SIGNALS · DISTINCT AFFECTED ORDERS</div>
        <p className="text-[10px] text-slate-500 mb-2">Categories may overlap. Packing wait shows current at-risk packing orders; other signals include history. Unallocated can mean stock or rider constraints.</p>
        <ResponsiveContainer width="100%" height={170}>
          <BarChart data={kpis.delay_reasons || []} layout="vertical" margin={{ left: 0, right: 10 }}>
            <XAxis type="number" allowDecimals={false} tick={{ fontSize: 9, fill: '#94a3b8' }} />
            <YAxis type="category" dataKey="reason" width={90} tick={{ fontSize: 9, fill: '#94a3b8' }} />
            <Tooltip contentStyle={{ background: '#0a0e14', border: '1px solid #ffffff20', fontSize: 11 }} />
            <Bar dataKey="count" fill="#FBBF24" radius={[0, 3, 3, 0]} />
          </BarChart>
        </ResponsiveContainer>
        {(kpis.disruption_markers || []).slice(-5).reverse().map((event, i) => (
          <div key={`${event.ts}-${event.order_id}-${i}`} className="text-[10px] text-slate-400 py-1">
            {new Date(event.ts).toLocaleTimeString()} · {event.reason} · {event.order_id}
          </div>
        ))}
      </div>
    </div>
  );
};

export default AnalyticsPanel;
