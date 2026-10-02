import React from 'react';
import { Activity } from 'lucide-react';
import TrackOrderWidget from './TrackOrderWidget';
import SpeedSelector from './SpeedSelector';

const TopNavigation = ({ liveOperations, setLiveOperations, activeTab, onTabChange }) => {
  return (
    <div className="absolute top-0 left-0 w-full z-40 flex items-center justify-between p-4 px-6 pointer-events-none">
      
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
        {['Overview', 'Orders', 'Riders', 'Dark Stores', 'Optimization', 'Analytics', 'Shop'].map(tab => (
          <button
            key={tab}
            onClick={() => tab === 'Shop' ? window.location.hash = 'shop' : onTabChange(tab)}
            className={`text-sm font-medium transition-colors whitespace-nowrap ${activeTab === tab ? 'text-route-cyan' : 'text-slate-400 hover:text-white'}`}>
            {tab}
          </button>
        ))}
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
        <TrackOrderWidget />
        <div className="w-px h-4 bg-white/10"></div>
        <div className="text-sm font-medium text-slate-300 hidden lg:block">Mumbai</div>
        <div className="text-sm text-slate-500 hidden lg:block">{new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
      </div>
      <div className="absolute top-20 right-6 pointer-events-auto">
        <SpeedSelector />
      </div>
    </div>
  );
};

export default TopNavigation;
