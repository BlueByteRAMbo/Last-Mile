import React, { useEffect, useState } from 'react';
import { Activity } from 'lucide-react';

const SimulationHeader = ({ rider, isPlaying, timeElapsed }) => {
  
  // Format seconds to mm:ss
  const formatTime = (seconds) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `00:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="absolute top-20 left-1/2 -translate-x-1/2 z-10 pointer-events-auto bg-route-panel/95 backdrop-blur-md px-6 py-3 rounded-full border border-white/10 shadow-2xl flex items-center gap-6">
      
      <div className="flex flex-col">
        <h1 className="text-[10px] font-bold text-slate-400 tracking-[0.2em] uppercase">RouteX / Simulation</h1>
        <div className="text-white text-sm font-bold tracking-wider flex items-center gap-2 mt-0.5">
          <Activity size={14} className={isPlaying ? "text-route-cyan animate-pulse" : "text-slate-500"} />
          LIVE RIDER REPLAY
        </div>
      </div>

      <div className="w-px h-8 bg-white/10"></div>

      <div className="flex flex-col">
        <div className="text-xs font-bold text-white tracking-wide">Rider {rider.id}</div>
        <div className="text-[10px] font-bold text-route-cyan bg-route-cyan/10 px-1.5 rounded-sm border border-route-cyan/20 inline-block w-max mt-0.5">
          {rider.status}
        </div>
      </div>

      <div className="w-px h-8 bg-white/10"></div>

      <div className="flex flex-col items-end min-w-[80px]">
        <div className="text-[10px] font-semibold text-slate-400 tracking-wider">Simulation time</div>
        <div className="text-sm font-bold font-mono text-white tracking-wider mt-0.5">{formatTime(timeElapsed)}</div>
      </div>

    </div>
  );
};

export default SimulationHeader;
