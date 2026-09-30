import React from 'react';
import { Activity } from 'lucide-react';

const TopNavigation = ({ liveOperations, setLiveOperations, activeTab, onTabChange }) => {
  return (
    <div className="absolute top-0 left-0 w-full z-10 flex items-center justify-between p-4 px-6 pointer-events-none">
      
      {/* Brand */}
      <div className="flex flex-col pointer-events-auto bg-route-base/80 backdrop-blur-md p-3 rounded-lg border border-white/5 shadow-lg">
        <h1 className="text-white font-bold tracking-widest text-lg flex items-center gap-2">
          ROUTEX
        </h1>
        <div className="text-route-cyan text-xs font-semibold tracking-wider flex items-center gap-1.5">
          <Activity size={12} className={liveOperations ? "animate-pulse" : ""} />
          LIVE OPERATIONS
        </div>
      </div>

      {/* Nav Links */}
      <div className="hidden md:flex items-center gap-6 pointer-events-auto bg-route-base/80 backdrop-blur-md px-6 py-3 rounded-full border border-white/5 shadow-lg">
        <button 
          onClick={() => onTabChange('Overview')}
          className={`text-sm font-medium transition-colors ${activeTab === 'Overview' ? 'text-route-cyan' : 'text-slate-400 hover:text-white'}`}>
          Overview
        </button>
        <button className="text-slate-400 text-sm font-medium hover:text-white transition-colors cursor-not-allowed opacity-50">Orders</button>
        <button className="text-slate-400 text-sm font-medium hover:text-white transition-colors cursor-not-allowed opacity-50">Riders</button>
        <button className="text-slate-400 text-sm font-medium hover:text-white transition-colors cursor-not-allowed opacity-50">Dark Stores</button>
        <button className="text-slate-400 text-sm font-medium hover:text-white transition-colors cursor-not-allowed opacity-50">Optimization</button>
        <button 
          onClick={() => onTabChange('Simulation')}
          className={`text-sm font-medium transition-colors ${activeTab === 'Simulation' ? 'text-route-cyan' : 'text-slate-400 hover:text-white'}`}>
          Simulation
        </button>
        <button className="text-slate-400 text-sm font-medium hover:text-white transition-colors cursor-not-allowed opacity-50">Analytics</button>
      </div>

      {/* Right Controls */}
      <div className="flex items-center gap-4 pointer-events-auto bg-route-base/80 backdrop-blur-md p-3 px-5 rounded-lg border border-white/5 shadow-lg">
        <button 
          onClick={() => setLiveOperations(!liveOperations)}
          className="flex items-center gap-2 text-sm font-medium cursor-pointer hover:bg-white/5 px-2 py-1 rounded"
        >
          <span className={`w-2 h-2 rounded-full ${liveOperations ? 'bg-route-cyan marker-pulse' : 'bg-slate-500'}`}></span>
          LIVE
        </button>
        <div className="w-px h-4 bg-white/10"></div>
        <div className="text-sm font-medium text-slate-300">Mumbai</div>
        <div className="text-sm text-slate-500">{new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
      </div>
    </div>
  );
};

export default TopNavigation;
