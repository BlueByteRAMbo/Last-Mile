import React from 'react';
import { CheckCircle } from 'lucide-react';

const SimulationCompletion = ({ stats, onRestart }) => {
  return (
    <div className="absolute inset-0 z-30 flex items-center justify-center pointer-events-none">
      <div className="absolute inset-0 bg-route-base/60 backdrop-blur-sm"></div>
      
      <div className="pointer-events-auto bg-route-panel border border-white/10 rounded-xl shadow-2xl p-8 max-w-md w-full relative z-10 text-center animate-[slideDown_0.5s_ease-out]">
        <div className="w-16 h-16 bg-route-green/20 rounded-full flex items-center justify-center mx-auto mb-6 border border-route-green/50 shadow-[0_0_30px_rgba(52,211,153,0.3)]">
          <CheckCircle size={32} className="text-route-green" />
        </div>
        
        <h2 className="text-2xl font-bold text-white mb-2 tracking-wide">SIMULATION COMPLETE</h2>
        <div className="text-sm text-slate-400 mb-8">All deliveries successfully executed</div>
        
        <div className="space-y-4 text-left bg-route-base/50 p-6 rounded-lg border border-white/5 mb-8">
          <div className="flex justify-between items-center">
            <span className="text-sm text-slate-400">Total time</span>
            <span className="text-sm font-bold text-white font-mono">{stats.time}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-sm text-slate-400">Orders delivered</span>
            <span className="text-sm font-bold text-white">3 / 3</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-sm text-slate-400">On-time deliveries</span>
            <span className="text-sm font-bold text-route-green">3 / 3</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-sm text-slate-400">Distance travelled</span>
            <span className="text-sm font-bold text-white">{stats.distance} km</span>
          </div>
          <div className="w-full h-px bg-white/10 my-2"></div>
          <div className="flex justify-between items-center">
            <span className="text-sm text-slate-400">Route optimization</span>
            <span className="text-sm font-bold text-route-violet">1</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-sm text-slate-400">ETA saved</span>
            <span className="text-sm font-bold text-route-violet">3 min</span>
          </div>
        </div>

        <button 
          onClick={onRestart}
          className="w-full bg-route-cyan hover:bg-route-cyan/90 text-route-base font-bold py-3 rounded-lg transition-colors"
        >
          RUN AGAIN
        </button>
      </div>
    </div>
  );
};

export default SimulationCompletion;
