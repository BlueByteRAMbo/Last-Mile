import React from 'react';
import { Bike, Clock, Navigation } from 'lucide-react';

/**
 * Minimal immersive HUD shown when Follow Camera is active.
 * The map should dominate the screen – this sits at edges only.
 */
const FollowHUD = ({ rider, eta, speed, distKm }) => {
  return (
    <>
      {/* Top-left pill: rider identity */}
      <div className="absolute top-6 left-6 z-20 pointer-events-none">
        <div className="bg-route-base/80 backdrop-blur-md border border-white/10 rounded-lg px-4 py-3 flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-route-cyan/20 border border-route-cyan/30 flex items-center justify-center">
            <Bike size={16} className="text-route-cyan" />
          </div>
          <div>
            <div className="text-xs font-bold text-white tracking-wider">{rider.id}</div>
            <div className="text-[10px] font-bold text-route-cyan tracking-widest">{rider.status}</div>
          </div>
          <div className="ml-2 flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-route-cyan marker-pulse"></div>
            <span className="text-[10px] font-bold text-route-cyan tracking-widest">LIVE FOLLOW</span>
          </div>
        </div>
      </div>

      {/* Bottom-center strip: key metrics */}
      <div className="absolute bottom-24 left-1/2 -translate-x-1/2 z-20 pointer-events-none">
        <div className="bg-route-base/80 backdrop-blur-md border border-white/10 rounded-full px-8 py-3 flex items-center gap-10">
          <div className="flex flex-col items-center">
            <div className="text-[10px] font-bold text-slate-400 tracking-widest mb-0.5 flex items-center gap-1">
              <Clock size={10}/> ETA
            </div>
            <div className="text-lg font-bold text-white font-mono">{eta}<span className="text-xs text-slate-400 ml-0.5">MIN</span></div>
          </div>

          <div className="w-px h-8 bg-white/10"></div>

          <div className="flex flex-col items-center">
            <div className="text-[10px] font-bold text-slate-400 tracking-widest mb-0.5">SPEED</div>
            <div className="text-lg font-bold text-white font-mono">{speed}<span className="text-xs text-slate-400 ml-0.5">KM/H</span></div>
          </div>

          <div className="w-px h-8 bg-white/10"></div>

          <div className="flex flex-col items-center">
            <div className="text-[10px] font-bold text-slate-400 tracking-widest mb-0.5 flex items-center gap-1">
              <Navigation size={10}/> DIST
            </div>
            <div className="text-lg font-bold text-white font-mono">{distKm}<span className="text-xs text-slate-400 ml-0.5">KM</span></div>
          </div>
        </div>
      </div>
    </>
  );
};

export default FollowHUD;
