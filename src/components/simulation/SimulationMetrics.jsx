import React from 'react';

const SimulationMetrics = ({ state }) => {
  const kpis = [
    { label: 'ETA', value: state.eta },
    { label: 'DISTANCE', value: state.distanceRemaining },
    { label: 'ORDERS', value: `${state.ordersCompleted} / ${state.totalOrders}` },
    { label: 'AVG SPEED', value: `${state.speed} km/h` },
    { label: 'ON-TIME', value: '100%' },
  ];

  return (
    <div className="absolute top-[140px] left-1/2 -translate-x-1/2 z-10 flex justify-center pointer-events-none">
      <div className="flex gap-8 pointer-events-auto bg-route-base/70 backdrop-blur-md px-8 py-2.5 rounded-full border border-white/5 shadow-lg">
        {kpis.map((kpi, idx) => (
          <div key={idx} className="flex flex-col items-center min-w-[60px]">
            <div className="text-[10px] font-semibold text-slate-400 tracking-wider mb-0.5">{kpi.label}</div>
            <div className="text-sm font-bold tracking-wide text-slate-200">
              {kpi.value}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default SimulationMetrics;
