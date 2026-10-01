import { useEffect, useState } from 'react';
import { api, connectWs } from '../api';

export default function useTrackedOrder(id) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [connected, setConnected] = useState(false);
  const [receivedAt, setReceivedAt] = useState(Date.now());
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    let alive = true;
    let close = () => {};
    setData(null); setError('');
    const receive = payload => {
      if (!alive) return;
      if (payload.type === 'not_found') {
        setError('This order is no longer available after the simulation restarted. Return to the shop to place a new order.');
        setConnected(false); close(); return;
      }
      if (payload.type !== 'tracking') {
        setError('The backend is running an older version. Restart it and refresh this page.');
        setConnected(false); close(); return;
      }
      setData(payload); setReceivedAt(Date.now()); setError('');
    };
    api.track(id).then(receive).catch(error => {
      if (!alive) return;
      if (error.status === 404) receive({ type: 'not_found' });
      else setError('Unable to reach the backend. Reconnecting…');
    });
    close = connectWs(receive, `/ws/track/${encodeURIComponent(id)}`, status => { if (alive) setConnected(status); });
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => { alive = false; close(); clearInterval(timer); };
  }, [id]);
  const eta = data?.eta_seconds == null ? null : Math.max(0, Math.ceil(data.eta_seconds - (connected ? (now - receivedAt) / 1000 : 0)));
  return { data, error, connected, eta };
}
