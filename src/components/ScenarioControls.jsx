import React, { useState } from 'react';
import { CloudRain, Zap, RotateCcw } from 'lucide-react';
import { api } from '../api';

const ScenarioControls = () => {
  const [traffic, setTraffic] = useState(false);

  const toggleTraffic = () => {
    api.disrupt(traffic ? 'clear_traffic' : 'traffic');
    setTraffic(!traffic);
  };

  return (
    <div className="absolute top-24 left-6 z-10 pointer-events-auto flex flex-col gap-2 bg-route-base/80 backdrop-blur-md p-2 rounded-lg border border-white/5 shadow-lg">
      <button onClick={toggleTraffic}
        className={`flex items-center gap-2 text-xs px-3 py-2 rounded-md transition-colors ${traffic ? 'bg-route-amber/20 text-route-amber' : 'text-slate-400 hover:bg-white/5 hover:text-white'}`}>
        <CloudRain size={14} /> Rain / Traffic Surge
      </button>
      <button onClick={() => api.disrupt('surge')}
        className="flex items-center gap-2 text-xs px-3 py-2 rounded-md text-slate-400 hover:bg-white/5 hover:text-white transition-colors">
        <Zap size={14} /> Demand Surge
      </button>
      <button onClick={() => api.reset()}
        className="flex items-center gap-2 text-xs px-3 py-2 rounded-md text-slate-400 hover:bg-white/5 hover:text-white transition-colors">
        <RotateCcw size={14} /> Reset Scenario
      </button>
    </div>
  );
};

export default ScenarioControls;
