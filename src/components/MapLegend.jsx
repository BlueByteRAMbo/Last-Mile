import React from 'react';

const MapLegend = () => {
  return (
    <div className="hidden md:block absolute bottom-6 left-6 z-10 pointer-events-auto bg-route-base/80 backdrop-blur-md p-4 rounded-lg border border-white/5 shadow-lg w-48">
      <h3 className="text-xs font-semibold text-slate-400 tracking-wider mb-3">MAP LEGEND</h3>
      
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-3">
          <div className="w-3 h-3 rounded-full bg-route-green border border-route-base"></div>
          <span className="text-xs text-slate-300">Riders</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="w-3 h-3 rotate-45 bg-route-cyan border border-route-base"></div>
          <span className="text-xs text-slate-300">Orders</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="w-3 h-3 rounded-sm bg-slate-200 border border-route-base"></div>
          <span className="text-xs text-slate-300">Dark Stores</span>
        </div>
        <div className="flex items-center gap-3 mt-1">
          <div className="w-4 h-0.5 bg-route-cyan"></div>
          <span className="text-xs text-slate-300">Active Route</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="w-4 h-0.5 bg-route-amber"></div>
          <span className="text-xs text-slate-300">At Risk Route</span>
        </div>
        <div className="flex items-center gap-3 mt-1">
          <div className="w-3 h-3 rounded-full bg-route-red/30 border border-route-red/50"></div>
          <span className="text-xs text-slate-300">Traffic</span>
        </div>
      </div>
    </div>
  );
};

export default MapLegend;
