import React from 'react';
import { CheckCircle2, Circle, Clock } from 'lucide-react';

const DeliveryQueue = ({ orders }) => {
  return (
    <div className="absolute right-6 top-[420px] z-10 pointer-events-auto bg-route-panel/95 backdrop-blur-md p-5 rounded-lg border border-white/10 shadow-2xl w-72">
      <h3 className="text-[10px] font-bold text-slate-400 tracking-[0.2em] mb-4">DELIVERY QUEUE</h3>
      
      <div className="space-y-4">
        {orders.map((order, idx) => {
          const isDelivered = order.status === 'DELIVERED';
          const isCurrent = order.status === 'CURRENT';
          
          return (
            <div key={order.id} className={`relative pl-4 ${idx !== orders.length - 1 ? 'pb-4 border-l border-white/10' : ''} ${isDelivered ? 'opacity-50' : ''}`}>
              <div className="absolute -left-2 top-0 bg-route-panel">
                {isDelivered ? (
                  <CheckCircle2 size={16} className="text-route-green" />
                ) : isCurrent ? (
                  <div className="w-4 h-4 rounded-full border-2 border-route-cyan flex items-center justify-center bg-route-cyan/20">
                    <div className="w-1.5 h-1.5 bg-route-cyan rounded-full animate-pulse"></div>
                  </div>
                ) : (
                  <Circle size={16} className="text-slate-500" />
                )}
              </div>
              
              <div className="-mt-1">
                <div className="flex justify-between items-start mb-1">
                  <span className="text-xs font-bold text-white tracking-wide">ORDER {order.id}</span>
                  {order.priority === 'HIGH' && (
                    <span className="text-[9px] font-bold text-route-amber bg-route-amber/10 px-1.5 py-0.5 rounded-sm border border-route-amber/20">PRIORITY</span>
                  )}
                </div>
                <div className="text-sm font-medium text-slate-300 mb-1">{order.location}</div>
                <div className="flex justify-between items-center text-xs text-slate-500">
                  <span className="flex items-center gap-1"><Clock size={12}/> Promise: {order.promise}</span>
                  <span className={`font-semibold ${isDelivered ? 'text-route-green' : isCurrent ? 'text-route-cyan' : ''}`}>
                    {isDelivered ? 'Delivered' : isCurrent ? 'Current Delivery' : 'Upcoming'}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default DeliveryQueue;
