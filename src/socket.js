// Keep reconnect handling independent of Vite so it can be regression-tested.
const RETRY_BASE_MS = 1500;
const RETRY_MAX_MS = 15000;

export function subscribeSocket(url, onMessage, onStatus = () => {}) {
  let socket, retry;
  let stopped = false;
  let attempts = 0;
  const open = () => {
    if (stopped) return;
    socket = new WebSocket(url);
    socket.onopen = () => { attempts = 0; if (!stopped) onStatus(true); };
    socket.onmessage = event => {
      if (stopped) return;
      let message;
      try { message = JSON.parse(event.data); } catch { return; }  // one malformed frame must not break the feed
      onMessage(message);
    };
    socket.onclose = event => {
      if (stopped) return;
      onStatus(false);
      // Unknown/reset orders are permanent failures, not transient outages.
      if (event.code === 1008) { stopped = true; return; }
      // exponential backoff: 1.5s, 3s, 6s ... capped, so a down backend isn't hit every 1.5s forever
      retry = setTimeout(open, Math.min(RETRY_MAX_MS, RETRY_BASE_MS * 2 ** attempts++));
    };
  };
  open();
  return () => { stopped = true; clearTimeout(retry); socket?.close(); };
}
