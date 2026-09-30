import React from 'react';
import { Navigation, Bike, Clock, TrendingUp, MapPin } from 'lucide-react';

const RiderStatusPanel = ({ rider, state }) => {
  return (
    <div className="absolute right-6 top-24 z-10 pointer-events-auto bg-route-panel/95 backdrop-blur-md p-5 rounded-lg border border-white/10 shadow-2xl w-72">
      <h3 className="text-[10px] font-bold text-slate-400 tracking-[0.2em] mb-4">RIDER STATUS</h3>
      
      <div className="flex items-center gap-3 mb-5 pb-5 border-b border-white/10">
        <div className="w-10 h-10 rounded-full bg-route-base border border-white/10 flex items-center justify-center text-route-cyan">
          <Bike size={20} />
        </div>
        <div>
          <h2 className="text-lg font-bold text-white leading-tight">{rider.id}</h2>
          <div className="text-sm text-slate-400">{rider.name}</div>
        </div>
        <div className="ml-auto text-[10px] font-bold text-route-cyan bg-route-cyan/10 px-2 py-1 rounded-sm border border-route-cyan/20">
          {rider.status}
        </div>
      </div>

      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <span className="text-xs text-slate-400 flex items-center gap-2"><MapPin size={14}/> Current location</span>
          <span className="text-sm font-medium text-white">{state.currentLocation}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-xs text-slate-400 flex items-center gap-2"><Navigation size={14}/> Speed</span>
          <span className="text-sm font-medium text-white">{state.speed} km/h</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-xs text-slate-400 flex items-center gap-2">Current load</span>
          <span className="text-sm font-medium text-white">{state.currentLoad} / {rider.capacity}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-xs text-slate-400 flex items-center gap-2"><Clock size={14}/> ETA</span>
          <span className="text-sm font-medium text-white">{state.eta}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-xs text-slate-400 flex items-center gap-2">Distance rem.</span>
          <span className="text-sm font-medium text-white">{state.distanceRemaining}</span>
        </div>
        
        <div className="pt-2">
          <div className="flex justify-between items-center mb-1.5">
            <span className="text-xs text-slate-400 flex items-center gap-2"><TrendingUp size={14}/> Route progress</span>
            <span className="text-xs font-bold text-route-cyan">{state.progress}%</span>
          </div>
          <div className="w-full bg-route-base rounded-full h-1.5 border border-white/5">
            <div 
              className="bg-route-cyan h-full rounded-full transition-all duration-300 relative overflow-hidden" 
              style={{ width: `${state.progress}%` }}
            >
              <div className="absolute top-0 left-0 right-0 bottom-0 bg-white/20 w-full animate-[shimmer_2s_infinite]" style={{ transform: 'skewX(-20deg)' }}></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RiderStatusPanel;
