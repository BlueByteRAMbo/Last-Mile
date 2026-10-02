import React from 'react';
import { Compass, ZoomIn, ZoomOut } from 'lucide-react';

const MapControls = ({ onZoomIn, onZoomOut, onReset }) => {
  return (
    <div className="absolute bottom-6 right-4 md:right-72 md:mr-4 z-10 pointer-events-auto flex flex-col gap-2">
      <button 
        onClick={onReset}
        className="bg-route-base/80 backdrop-blur-md p-2 rounded-lg border border-white/5 shadow-lg text-slate-400 hover:text-white transition-colors flex items-center justify-center mb-2"
        title="Reset View"
      >
        <Compass size={20} />
      </button>
      <div className="bg-route-base/80 backdrop-blur-md rounded-lg border border-white/5 shadow-lg flex flex-col overflow-hidden">
        <button 
          onClick={onZoomIn}
          className="p-2 text-slate-400 hover:text-white transition-colors hover:bg-white/5 border-b border-white/5 flex items-center justify-center"
        >
          <ZoomIn size={20} />
        </button>
        <button 
          onClick={onZoomOut}
          className="p-2 text-slate-400 hover:text-white transition-colors hover:bg-white/5 flex items-center justify-center"
        >
          <ZoomOut size={20} />
        </button>
      </div>
    </div>
  );
};

export default MapControls;
