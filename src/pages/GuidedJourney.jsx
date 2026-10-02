import React, { useEffect, useState } from 'react';
import { api } from '../api';
import useTrackedOrder from '../hooks/useTrackedOrder';
import useLiveOps from '../hooks/useLiveOps';
import JourneyMap from '../components/JourneyMap';

const steps = ['Stock check', 'Nearest store', 'Rider allocation', 'Journey'];
export default function GuidedJourney({ orderId }) {
  const { data, error, connected, eta } = useTrackedOrder(orderId);
  const live = useLiveOps();
  const [context, setContext] = useState(null), [step, setStep] = useState(0), [follow, setFollow] = useState(false);
  const [placing, setPlacing] = useState(false), [radius, setRadius] = useState(.4), [multiplier, setMultiplier] = useState(.25), [duration, setDuration] = useState(6);
  const [notice, setNotice] = useState(''), [busy, setBusy] = useState(false), [decision, setDecision] = useState(null);
  useEffect(() => {
    let alive = true;
    api.journey(orderId).then(result => { if (alive) setContext(result); }).catch(e => { if (alive) setNotice(e.message); });
    return () => { alive = false; };
  }, [orderId, data?.status, data?.rider_id, data?.route_version, data?.route_events?.length]);
  const hasContext = Boolean(context), hasStore = Boolean(data?.store);
  useEffect(() => {
    if (step >= 3 || !hasContext || (step > 0 && !hasStore)) return;
    const timer = setTimeout(() => setStep(s => Math.min(s + 1, 3)), 4500);
    return () => clearTimeout(timer);
  }, [step, hasContext, hasStore, context?.decision?.chosen?.rider_id, data?.store?.id]);
  useEffect(() => {
    if (!decision) return;
    const timer = setTimeout(() => setDecision(null), 8000);
    return () => clearTimeout(timer);
  }, [decision]);
  const placeTraffic = async ({ lat, lng }) => {
    setPlacing(false); setBusy(true); setNotice('Evaluating routes around the new traffic zone…');
    try {
      const result = await api.traffic({ lat, lng, radius_km: radius, multiplier, duration_minutes: duration });
      const route = result.reroute_decisions?.[data?.rider_id]?.route;
      setDecision(route || null);
      setNotice(route ? route.switched ? `Faster route selected: saves ${Math.round(route.gain_seconds)} seconds.` : `Keeping current route. ${route.reason || `Gain ${Math.round(route.gain_seconds)} seconds is below the threshold.`}` : 'Traffic placed. No active rider route intersects this zone.');
      setContext(await api.journey(orderId));
    } catch (e) { setNotice(e.message); }
    finally { setBusy(false); }
  };
  if (error || !data) return <div className="flow-page p-8"><a href="#shop">← Shop</a><p role="status" className="mt-8">{error || 'Loading your order…'}</p></div>;
  const candidates = [context?.decision?.chosen, ...(context?.decision?.alternatives || [])].filter(Boolean);
  const selected = context?.stock_check?.find(s => s.store_id === data.store?.id);
  const maxCost = Math.max(1, ...candidates.map(c => Math.abs(c.cost)));
  return <main className="flow-page">
    <header className="flow-header"><a href="#shop" className="flow-brand">ROUTEX <span>MISSION CONTROL</span></a><div className="flex gap-4"><a href="#ops">All operations</a><a href={`#track/${orderId}`} target="_blank" rel="noreferrer">Customer tracking ↗</a></div></header>
    <div className="journey-heading"><div><p className="flow-eyebrow">{orderId} · {data.customer_name}</p><h1>Your order, in motion.</h1></div><span className={connected ? 'text-route-green' : 'text-route-amber'}>{connected ? '● Live' : 'Reconnecting…'}</span></div>
    <nav className="journey-steps" aria-label="Delivery explanation">{steps.map((label, i) => <button key={label} className={step === i ? 'active' : ''} onClick={() => setStep(i)}><span>{i + 1}</span>{label}</button>)}</nav>
    <div className="journey-layout"><section className="journey-map-shell">
      <JourneyMap data={data} stores={context?.stock_check || []} riders={live.riders.map(r => ({ ...r, orderLabel: live.orders.filter(o => o.rider_id === r.id).map(o => `${o.id} · ${o.customer_name || 'Customer'}`).join(', ') }))} shortlist={candidates.map(c => c.rider_id)} step={step} follow={follow} traffic={live.trafficZones} placing={placing} onPlace={placeTraffic} decision={decision} />
      <div className="journey-hud"><div><span className="flow-eyebrow">LIVE STATUS</span><strong>{data.status_label}</strong></div><div><span className="flow-eyebrow">ARRIVAL</span><strong>{eta == null ? 'Allocating…' : `${Math.floor(eta / 60)}m ${eta % 60}s`}</strong></div><div><span className="flow-eyebrow">CURRENT LEG</span><strong>{data.distance_remaining_km?.toFixed(2) || '0.00'} km</strong></div><button className={`flow-chip ${follow ? 'selected' : ''}`} onClick={() => setFollow(!follow)}>Follow rider {follow ? 'on' : 'off'}</button></div>
    </section><aside className="flow-card journey-details">
      <p className="flow-eyebrow">{String(step + 1).padStart(2, '0')} / THE DECISION</p><h2>{steps[step]}</h2>
      {step === 0 && <><p className="text-slate-400 text-sm my-3">Stock at allocation, including the quantities in your basket.</p>{(context?.stock_check || []).map(s => <div key={s.store_id} className={`stock-row ${s.has_all_items ? 'eligible' : ''}`}><strong>{s.store_name}</strong><span>{s.distance_km} km · {s.has_all_items ? 'All items available' : `Missing: ${s.missing.map(sku => data.items.find(i => i.sku === sku)?.name || sku).join(', ')}`}</span>{s.has_all_items && <small>Has {data.items.map(i => `${i.qty} × ${i.name}`).join(', ')}</small>}</div>)}</>}
      {step === 1 && <><p className="text-2xl text-route-green my-4">{data.store_name || 'Checking eligible stores…'}</p><p className="text-slate-400 text-sm">{selected ? `${selected.distance_km} km · about ${Math.ceil(selected.eta_seconds / 60)} minutes from store to customer.` : 'Waiting for an allocation that can fulfill the entire basket.'}</p><p className="text-slate-500 text-xs mt-3">Optimized dispatch chooses the nearest stock-eligible store with a feasible rider, then ranks its riders. Distances use cached roads when available.</p></>}
      {step === 2 && <><p className="text-route-green my-3">{data.rider_name || 'Waiting for a feasible rider…'}</p>{candidates.map((c, i) => <div key={`${c.store_id}-${c.rider_id}`} className="mb-4"><div className="flex justify-between text-xs"><span>{i === 0 ? 'Selected · ' : ''}{c.rider_name}</span><span>{c.cost.toFixed(2)}</span></div><div className="h-1.5 bg-white/10 mt-2 rounded"><div className="h-full bg-route-cyan rounded" style={{ width: `${Math.max(4, Math.abs(c.cost) / maxCost * 100)}%` }} /></div><p className="text-[10px] text-slate-500 mt-1">Pickup {Math.round(c.reason.pickup_eta_seconds)}s · packing {Math.round(c.reason.packing_wait_seconds)}s · load {c.reason.workload_penalty} · batch benefit {c.reason.batching_benefit}</p></div>)}{candidates.length > 1 && <p className="text-xs text-slate-400">Runner-up cost difference: {(candidates[1].cost - candidates[0].cost).toFixed(2)}. Lower cost is preferred.</p>}</>}
      {step === 3 && <><p className="text-lg text-route-green my-3">{data.status === 'delivered' ? 'Delivered. Mission complete.' : `${data.rider_name || 'Your rider'} · ${data.status_label}`}</p><ol className="journey-timeline">{data.stages.map(s => <li key={s.key} className={s.done ? 'done' : ''}><span>{s.done ? '✓' : '○'} {s.label}</span><small>{s.ts ? new Date(s.ts).toLocaleTimeString() : 'Pending'}</small></li>)}</ol></>}
      {context?.decision?.suggestion && !data.rider_id && <p className="text-route-amber text-sm mt-4">No single feasible allocation yet. Try a smaller basket or use Operations → Dark Stores to restock. The simulator will retry.</p>}
      <div className="traffic-tool"><h3>Traffic control</h3><label>Radius · {radius} km<input type="range" min="0.1" max="2" step="0.1" value={radius} onChange={e => setRadius(Number(e.target.value))} /></label><label>Speed in zone · {Math.round(multiplier * 100)}%<input type="range" min="0.1" max="0.8" step="0.05" value={multiplier} onChange={e => setMultiplier(Number(e.target.value))} /></label><label>Duration · {duration} min<input type="range" min="1" max="15" value={duration} onChange={e => setDuration(Number(e.target.value))} /></label><button disabled={busy || ['delivered', 'failed', 'cancelled'].includes(data.status)} className="flow-primary w-full" onClick={() => { setStep(3); setPlacing(!placing); }}>{busy ? 'Evaluating…' : placing ? 'Cancel placement' : 'Simulate traffic · click map'}</button></div>
      {notice && <p role="status" className="flow-notice">{notice}</p>}
      {decision?.candidate_polyline && <p className="text-xs text-route-amber mt-2">Dashed amber: candidate path · gain {Math.round(decision.gain_seconds)}s · threshold {Math.round(decision.threshold_seconds)}s</p>}
      <h3 className="mt-5 mb-2">Route history</h3>{(context?.route_history || []).slice(-8).reverse().map((r, i) => <p key={`${r.ts}-${i}`} className="text-xs text-slate-400 border-t border-white/10 py-2">{new Date(r.ts).toLocaleTimeString()} · {r.switched ? 'Switched to faster route' : r.reason || 'Route updated'}{r.gain_seconds != null ? ` · ${Math.round(r.gain_seconds)}s gain` : ''}</p>)}
      <div className="mt-4 text-xs text-slate-500">Delivered fleet-wide: {live.kpis?.delivered_count ?? 0} · On-time: {live.kpis?.on_time_rate_pct != null ? `${live.kpis.on_time_rate_pct}%` : '—'}</div>
    </aside></div>
  </main>;
}
