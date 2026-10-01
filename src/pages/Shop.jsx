import React, { useEffect, useState } from 'react';
import { api } from '../api';

export default function Shop() {
  const [catalog, setCatalog] = useState([]);
  const [stores, setStores] = useState([]);
  const [cart, setCart] = useState({});
  const [category, setCategory] = useState('All');
  const [name, setName] = useState('');
  const [location, setLocation] = useState('');
  const [express, setExpress] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let alive = true;
    Promise.all([api.catalog(), api.darkStores()]).then(([products, hubs]) => {
      if (!alive) return;
      setCatalog(products); setStores(hubs); setLocation(hubs[0]?.id || '');
    }).catch(() => { if (alive) setError('Could not load the shop. Check the backend connection.'); });
    return () => { alive = false; };
  }, []);
  const items = catalog.filter(p => cart[p.sku] > 0);
  const change = (sku, delta) => setCart(old => ({ ...old, [sku]: Math.max(0, Math.min(20, (old[sku] || 0) + delta)) }));
  const total = items.reduce((sum, p) => sum + p.price * cart[p.sku], 0);
  const place = async e => {
    e.preventDefault(); setError(''); setBusy(true);
    try {
      const store = stores.find(s => s.id === location);
      if (!store || !items.length) throw new Error('Add an item and choose a delivery address.');
      const order = await api.createOrder({ customer_name: name.trim(), address_label: `Residential delivery near ${store.name}`,
        customer_lat: store.lat + .002, customer_lng: store.lng + .002,
        priority: express, promise_minutes: express ? 12 : 20,
        items: items.map(p => ({ sku: p.sku, name: p.name, qty: cart[p.sku], weight_kg: p.weight_kg })) });
      window.location.hash = `journey/${encodeURIComponent(order.id)}`;
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };
  return <main className="flow-page">
    <header className="flow-header"><a href="#shop" className="flow-brand">ROUTEX <span>QUICK COMMERCE</span></a><a href="#ops">Mission control ↗</a></header>
    <div className="shop-layout">
      <section>
        <p className="flow-eyebrow">MUMBAI · YOUR NEIGHBOURHOOD, DELIVERED</p>
        <h1>Everyday essentials.<br /><span className="text-route-cyan">A smarter last mile.</span></h1>
        <p className="text-slate-400 mt-3 mb-6">Build your basket, then follow the stock check, rider allocation and delivery live.</p>
        <div className="flex flex-wrap gap-2 mb-6">{['All', ...new Set(catalog.map(p => p.category))].map(c => <button key={c} className={`flow-chip ${category === c ? 'selected' : ''}`} onClick={() => setCategory(c)}>{c}</button>)}</div>
        <div className="product-grid">{catalog.filter(p => category === 'All' || p.category === category).map(p => <article className="product-card" key={p.sku}>
          <div className="product-emoji" aria-hidden="true">{p.emoji}</div><span className="flow-eyebrow">{p.category}</span><h2>{p.name}</h2>
          <div className="flex justify-between items-center mt-4"><strong>₹{p.price}</strong><button aria-label={`Add ${p.name}`} onClick={() => change(p.sku, 1)} className="flow-chip selected">{cart[p.sku] ? `${cart[p.sku]} in cart · +` : '+ Add'}</button></div>
        </article>)}</div>
        {!catalog.length && !error && <p>Loading products…</p>}
      </section>
      <form className="flow-card cart-panel" onSubmit={place}>
        <p className="flow-eyebrow">YOUR BASKET</p><h2>Ready when you are</h2>
        {!items.length && <p className="text-slate-500 my-6">Add essentials to get started.</p>}
        {items.map(p => <div className="cart-row" key={p.sku}><span>{p.emoji} {p.name}</span><div className="flex gap-3 items-center"><button type="button" aria-label={`Remove one ${p.name}`} onClick={() => change(p.sku, -1)}>−</button><span>{cart[p.sku]}</span><button type="button" aria-label={`Add one ${p.name}`} onClick={() => change(p.sku, 1)}>+</button></div></div>)}
        <div className="cart-row text-lg"><strong>Total</strong><strong>₹{total.toFixed(2)}</strong></div>
        <label>Your name<input required maxLength={100} value={name} onChange={e => setName(e.target.value)} placeholder="Customer name" /></label>
        <label>Delivery address<select required value={location} onChange={e => setLocation(e.target.value)}>{stores.map(s => <option key={s.id} value={s.id}>Residential block near {s.name}</option>)}</select></label>
        <p className="text-xs text-slate-500">Preset Mumbai addresses, about 300 m from each hub. Stock determines which hub fulfills the basket.</p>
        <div className="flex gap-2 my-4"><button type="button" className={`flow-chip ${!express ? 'selected' : ''}`} onClick={() => setExpress(false)}>Regular · 20 min</button><button type="button" className={`flow-chip ${express ? 'selected' : ''}`} onClick={() => setExpress(true)}>Express · 12 min</button></div>
        {error && <p role="alert" className="text-route-red text-sm mb-3">{error}</p>}
        <button disabled={busy || !items.length} className="flow-primary w-full">{busy ? 'Placing order…' : 'Place order & follow delivery →'}</button>
        <p className="text-xs text-slate-500 mt-3">Simulation only. No payment or real delivery.</p>
      </form>
    </div>
  </main>;
}
