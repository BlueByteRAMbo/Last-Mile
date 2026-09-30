import React from 'react';
import { ArrowDown } from 'lucide-react';

const SimulationTimeline = ({ events }) => {
  return (
    <div className="absolute bottom-6 left-6 z-10 pointer-events-auto bg-route-panel/95 backdrop-blur-md p-4 rounded-lg border border-white/10 shadow-2xl flex items-center overflow-x-auto max-w-[600px] hide-scrollbar">
      
      <div className="flex items-center">
        {events.map((event, idx) => (
          <React.Fragment key={idx}>
            <div className={`flex flex-col items-center min-w-[80px] ${event.active ? 'opacity-100' : 'opacity-40'}`}>
              <div className="text-[10px] font-bold font-mono text-route-cyan mb-1">{event.time}</div>
              <div className={`text-[10px] font-bold text-center leading-tight ${event.active ? 'text-white' : 'text-slate-400'}`}>
                {event.label.split('\n').map((line, i) => <div key={i}>{line}</div>)}
              </div>
            </div>
            
            {idx < events.length - 1 && (
              <div className={`px-2 flex flex-col items-center justify-center ${events[idx+1].active ? 'opacity-100' : 'opacity-20'}`}>
                <div className="w-8 h-px bg-route-cyan/50 my-1"></div>
                <ArrowDown size={12} className="-rotate-90 text-route-cyan/50" />
              </div>
            )}
          </React.Fragment>
        ))}
      </div>

    </div>
  );
};

export default SimulationTimeline;
