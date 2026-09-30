import React, { useEffect, useState } from 'react';
import OperationsMap from './pages/OperationsMap';
import CustomerTracker from './pages/CustomerTracker';

function getTrackOrderId() {
  const match = window.location.hash.match(/^#track\/(.+)$/);
  return match ? decodeURIComponent(match[1]) : null;
}

function App() {
  const [trackOrderId, setTrackOrderId] = useState(getTrackOrderId());

  useEffect(() => {
    const onHashChange = () => setTrackOrderId(getTrackOrderId());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  if (trackOrderId) {
    return <CustomerTracker orderId={trackOrderId} />;
  }

  return (
    <div className="w-full h-screen bg-route-base text-white overflow-hidden">
      <OperationsMap />
    </div>
  );
}

export default App;
