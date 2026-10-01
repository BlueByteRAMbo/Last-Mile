import React, { useState } from 'react';
import useTrackedOrder from '../hooks/useTrackedOrder';
import JourneyMap from '../components/JourneyMap';
import SpeedSelector from '../components/SpeedSelector';

export default function CustomerTracker({ orderId }) {
  const { data, error, connected, eta } = useTrackedOrder(orderId);
  const [follow, setFollow] = useState(true);
  if (error || !data) return <main className="flow-page p-8"><a href="#shop">← Shop</a><p role="status" className="mt-8">{error || 'Finding your order…'}</p></main>;
  const terminal = ['delivered', 'failed', 'cancelled'].includes(data.status);
  const event = data.route_events?.at(-1);
  return <main className="flow-page customer-page">
    <header className="flow-header"><a href="#shop" className="flow-brand">ROUTEX <span>YOUR DELIVERY</span></a><div className="flex items-center gap-3"><SpeedSelector /><span className={connected ? 'text-route-green' : 'text-route-amber'}>{connected ? '● Live updates' : 'Reconnecting… last known status'}</span></div></header>
    <div className="journey-heading"><div><p className="flow-eyebrow">{orderId} · {data.customer_name}</p><h1>{data.status === 'delivered' ? 'At your doorstep.' : data.status_label}</h1><p className="text-slate-400 mt-2">{data.address_label}</p></div><div className="customer-eta"><span>{terminal ? 'ORDER STATUS' : 'ESTIMATED ARRIVAL'}</span><strong>{terminal ? data.status_label : eta == null ? 'Finding a rider' : `${Math.floor(eta / 60)}m ${eta % 60}s`}</strong></div></div>
    {!terminal && data.predicted_late && <div className="customer-banner">Your delivery is taking longer than promised. The estimated arrival is updating live.</div>}
    {!terminal && event && <div className="customer-banner">{event.message}{eta != null ? ` Estimated arrival in ${Math.ceil(eta / 60)} min.` : ''}</div>}
    <section className="customer-map"><JourneyMap data={data} customerOnly follow={follow} /><button className="flow-chip selected customer-follow" onClick={() => setFollow(!follow)}>Follow rider {follow ? 'on' : 'off'}</button></section>
    <div className="customer-details"><section className="flow-card"><p className="flow-eyebrow">EVERY STEP, LIVE</p><h2>Your delivery timeline</h2><ol className="journey-timeline">{data.stages.map(s => <li key={s.key} className={s.done ? 'done' : ''}><div><span>{s.done ? '✓' : '○'} {s.label}</span>{s.detail && <p className="text-xs text-slate-400">{s.detail}{s.key === 'store' ? ' · items confirmed' : ''}</p>}</div><small>{s.ts ? new Date(s.ts).toLocaleTimeString() : 'Pending'}</small></li>)}</ol></section>
    <section className="flow-card"><p className="flow-eyebrow">YOUR ORDER</p><h2>{data.priority ? 'Express delivery' : 'Everyday essentials'}</h2>{data.items.map((item, i) => <div className="cart-row" key={`${item.sku}-${i}`}><span>{item.name}</span><strong>× {item.qty}</strong></div>)}<p className="text-sm text-slate-400 mt-5">From {data.store_name || 'a nearby store'}<br />{data.rider_name ? `Rider: ${data.rider_name} · ${data.rider_vehicle}` : 'We are finding your rider.'}<br />Promised by {new Date(data.promised_at).toLocaleTimeString()}</p></section></div>
  </main>;
}
