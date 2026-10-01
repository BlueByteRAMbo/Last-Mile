import React, { useEffect, useState } from 'react';
import { Gauge } from 'lucide-react';
import { api } from '../api';

const SPEEDS = [1, 10, 20, 40];

const SpeedSelector = () => {
  const [speed, setSpeed] = useState(1);

  useEffect(() => { api.simSpeed().then(d => setSpeed(d.multiplier)).catch(() => {}); }, []);

  const change = async (m) => {
    setSpeed(m);
    try { await api.setSimSpeed(m); } catch { api.simSpeed().then(d => setSpeed(d.multiplier)).catch(() => {}); }
  };

  return (
    <div className="flex items-center gap-1.5 bg-route-base/80 backdrop-blur-md px-2 py-1.5 rounded-lg border border-white/5 shadow-lg">
      <Gauge size={13} className="text-slate-400" />
      {SPEEDS.map(m => (
        <button key={m} onClick={() => change(m)}
          className={`text-[11px] font-semibold px-2 py-0.5 rounded transition-colors ${speed === m ? 'bg-route-cyan/20 text-route-cyan' : 'text-slate-400 hover:text-white'}`}>
          {m}x
        </button>
      ))}
    </div>
  );
};

export default SpeedSelector;
