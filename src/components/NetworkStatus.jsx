import React from 'react';

const NetworkStatus = () => {
  return (
    <div className="absolute bottom-6 right-6 z-10 pointer-events-auto bg-route-base/80 backdrop-blur-md p-5 rounded-lg border border-white/5 shadow-lg w-64">
      <h3 className="text-xs font-semibold text-slate-400 tracking-wider mb-4">NETWORK STATUS</h3>
      
      <div className="flex flex-col gap-3">
        <div className="flex justify-between items-center">
          <span className="text-sm text-slate-300">Active Riders</span>
          <span className="text-sm font-medium text-white">42</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-sm text-slate-300">Active Orders</span>
          <span className="text-sm font-medium text-white">126</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-sm text-slate-300">Orders At Risk</span>
          <span className="text-sm font-medium text-route-red">8</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-sm text-slate-300">Avg ETA</span>
          <span className="text-sm font-medium text-white">09m</span>
        </div>
        
        <div className="w-full h-px bg-white/10 my-1"></div>
        
        <div className="flex justify-between items-center">
          <span className="text-sm font-medium text-slate-300">On-time rate</span>
          <span className="text-sm font-bold text-route-green">94.8%</span>
        </div>
      </div>
    </div>
  );
};

export default NetworkStatus;
