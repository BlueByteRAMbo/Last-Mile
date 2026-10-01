// Keep reconnect handling independent of Vite so it can be regression-tested.
export function subscribeSocket(url, onMessage, onStatus = () => {}) {
  let socket, retry;
  let stopped = false;
  const open = () => {
    if (stopped) return;
    socket = new WebSocket(url);
    socket.onopen = () => { if (!stopped) onStatus(true); };
    socket.onmessage = event => { if (!stopped) onMessage(JSON.parse(event.data)); };
    socket.onclose = event => {
      if (stopped) return;
      onStatus(false);
      // Unknown/reset orders are permanent failures, not transient outages.
      if (event.code === 1008) { stopped = true; return; }
      retry = setTimeout(open, 1500);
    };
  };
  open();
  return () => { stopped = true; clearTimeout(retry); socket?.close(); };
}
