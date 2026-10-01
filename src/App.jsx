import React, { useEffect, useState } from 'react';
import OperationsMap from './pages/OperationsMap';
import CustomerTracker from './pages/CustomerTracker';
import Shop from './pages/Shop';
import GuidedJourney from './pages/GuidedJourney';

function getTrackOrderId() {
  const match = window.location.hash.match(/^#track\/(.+)$/);
  return match ? decodeURIComponent(match[1]) : null;
}

function App() {
  const [hash, setHash] = useState(window.location.hash);
  const [trackOrderId, setTrackOrderId] = useState(getTrackOrderId());

  useEffect(() => {
    const onHashChange = () => { setTrackOrderId(getTrackOrderId()); setHash(window.location.hash); };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  if (trackOrderId) {
    return <CustomerTracker key={trackOrderId} orderId={trackOrderId} />;
  }
  if (hash === '#shop') return <Shop />;
  if (hash.startsWith('#journey/')) return <GuidedJourney key={hash} orderId={decodeURIComponent(hash.slice(9))} />;

  return (
    <div className="w-full h-screen bg-route-base text-white overflow-hidden">
      <OperationsMap />
    </div>
  );
}

export default App;
