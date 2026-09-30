import React from 'react';
import { AlertTriangle, Map } from 'lucide-react';

const SimulationEventToast = ({ event }) => {
  if (!event) return null;

  const isTraffic = event.type === 'TRAFFIC';
  
  return (
    <div className={`absolute top-[220px] left-1/2 -translate-x-1/2 z-20 pointer-events-auto backdrop-blur-md p-4 pr-6 rounded-lg border shadow-2xl flex items-start gap-4 animate-[slideDown_0.3s_ease-out]
      ${isTraffic ? 'bg-route-amber/10 border-route-amber/30' : 'bg-route-violet/10 border-route-violet/30'}
    `}>
      <div className={`w-10 h-10 rounded-full flex items-center justify-center border 
        ${isTraffic ? 'bg-route-amber/20 text-route-amber border-route-amber/50' : 'bg-route-violet/20 text-route-violet border-route-violet/50'}
      `}>
        {isTraffic ? <AlertTriangle size={20} /> : <Map size={20} />}
      </div>
      
      <div>
        <h4 className={`text-sm font-bold tracking-wider mb-1
          ${isTraffic ? 'text-route-amber' : 'text-route-violet'}
        `}>
          {event.title}
        </h4>
        <div className="text-xs text-white font-medium mb-1">{event.message}</div>
        <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{event.detail}</div>
      </div>
    </div>
  );
};

export default SimulationEventToast;
