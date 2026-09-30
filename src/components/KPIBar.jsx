import React from 'react';

const KPIBar = () => {
  const kpis = [
    { label: 'ACTIVE ORDERS', value: '126', highlight: false },
    { label: 'AT RISK', value: '8', highlight: true },
    { label: 'ACTIVE RIDERS', value: '42', highlight: false },
    { label: 'AVG ETA', value: '09m', highlight: false },
    { label: 'ON-TIME', value: '94.8%', highlight: false },
  ];

  return (
    <div className="absolute top-20 left-0 w-full z-10 flex justify-center pointer-events-none">
      <div className="flex gap-8 pointer-events-auto bg-route-base/70 backdrop-blur-md px-8 py-2.5 rounded-full border border-white/5 shadow-lg">
        {kpis.map((kpi, idx) => (
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
