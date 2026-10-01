import React, { useEffect, useState } from 'react';
import { api } from '../../api';

export default function DispatchComparison() {
  const [mode, setMode] = useState('optimized');
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { api.dispatchMode().then(r => setMode(r.mode)).catch(e => setError(e.message)); }, []);
  const change = async value => {
    setBusy(true); setError('');
    try { setMode((await api.setDispatchMode(value)).mode); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const compare = async () => {
    setBusy(true); setError('');
    try { setData(await api.comparison()); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  return <div className="mt-4 pt-4 border-t border-white/10 text-xs">
    <h3 className="font-semibold mb-2">Dispatch comparison</h3>
    <label className="text-slate-400">Live dispatch mode <select aria-label="Live dispatch mode" value={mode} disabled={busy} onChange={e => change(e.target.value)} className="bg-slate-800 p-2 rounded ml-2">
      <option value="optimized">Optimized</option><option value="nearest">Nearest eligible rider</option>
    </select></label>
    <p className="text-slate-500 my-2">Mode changes apply to new allocations. Nearest mode disables rolling optimization.</p>
    <button disabled={busy} onClick={compare} className="bg-route-cyan/20 text-route-cyan rounded p-2 disabled:opacity-50">{busy ? 'Working…' : 'Compare the same seeded demand'}</button>
    {error && <p role="alert" className="text-route-red mt-2">{error}</p>}
    {data && <>
      <p className="text-slate-500 my-2">{data.order_count} orders · seed {data.seed}. Isolated replay; live operations continue. Both use identical straight-line routing.</p>
      <table className="w-full text-left"><thead><tr><th>Metric</th><th>Nearest</th><th>Optimized</th></tr></thead><tbody>
        {[['On time / all orders', 'on_time_of_all_orders_pct', '%'], ['On time / delivered', 'on_time_rate_pct', '%'], ['Average delivery', 'avg_delivery_minutes', 'm'], ['Delivered', 'delivered_count', ''], ['Failed', 'failure_count', ''], ['Still active', 'active_orders', '']].map(([label, key, unit]) => <tr key={key} className="border-t border-white/5"><td className="py-2 text-slate-400">{label}</td><td>{data.results.nearest[key]}{unit}</td><td>{data.results.optimized[key]}{unit}</td></tr>)}
      </tbody></table>
    </>}
  </div>;
}
