import React from 'react';
import { Play, Pause, RotateCcw } from 'lucide-react';

const SimulationControls = ({ isPlaying, onTogglePlay, onRestart, speed, onSpeedChange, isComplete }) => {
  return (
    <div className="absolute bottom-6 right-[350px] z-10 pointer-events-auto bg-route-panel/95 backdrop-blur-md p-3 px-4 rounded-full border border-white/10 shadow-2xl flex items-center gap-6">
      
      <div className="flex items-center gap-2">
        <button 
          onClick={onTogglePlay}
          className="w-10 h-10 rounded-full bg-white text-route-base flex items-center justify-center hover:bg-slate-200 transition-colors shadow-lg shadow-white/10"
        >
          {isPlaying ? <Pause size={18} fill="currentColor" /> : <Play size={18} fill="currentColor" className="ml-1" />}
        </button>
        <button 
          onClick={onRestart}
          className="w-10 h-10 rounded-full bg-white/10 text-white flex items-center justify-center hover:bg-white/20 transition-colors"
        >
          <RotateCcw size={16} />
        </button>
      </div>

      <div className="w-px h-8 bg-white/10"></div>

      <div className="flex items-center gap-1 bg-route-base rounded-full p-1 border border-white/5">
        {[1, 2, 4].map(s => (
          <button
            key={s}
            onClick={() => onSpeedChange(s)}
            className={`px-3 py-1 rounded-full text-xs font-bold transition-colors ${speed === s ? 'bg-route-cyan text-route-base' : 'text-slate-400 hover:text-white hover:bg-white/5'}`}
          >
            {s}x
          </button>
        ))}
      </div>

      <div className="w-px h-8 bg-white/10"></div>

      <div className="flex items-center gap-2 pr-2">
        <div className={`w-2 h-2 rounded-full ${isComplete ? 'bg-route-green' : isPlaying ? 'bg-route-cyan marker-pulse' : 'bg-slate-500'}`}></div>
        <span className="text-xs font-bold tracking-wider text-slate-300">
          {isComplete ? 'COMPLETED' : isPlaying ? 'ACTIVE' : 'PAUSED'}
        </span>
      </div>

    </div>
  );
};

export default SimulationControls;
