import React, { useState, useEffect, Suspense, lazy } from 'react';
import { api } from '../api';
import RouteMap from '../components/RouteMap';
import TopNavigation from '../components/TopNavigation';
import KPIBar from '../components/KPIBar';
import MapLegend from '../components/MapLegend';
import NetworkStatus from '../components/NetworkStatus';
import MapControls from '../components/MapControls';
import EntityPanel from '../components/EntityPanel';
import ScenarioControls from '../components/ScenarioControls';
import OrdersPanel from '../components/panels/OrdersPanel';
import RidersPanel from '../components/panels/RidersPanel';
import StoresPanel from '../components/panels/StoresPanel';
import OptimizationPanel from '../components/panels/OptimizationPanel';
import useLiveOps from '../hooks/useLiveOps';

// Heaviest two screens (recharts, and the GLB/3D simulation machinery) split out of the main
// bundle — most sessions never open either tab, so there's no reason to ship them up front.
const AnalyticsPanel = lazy(() => import('../components/panels/AnalyticsPanel'));


const PanelLoading = () => (
  <div className="absolute top-40 left-6 z-10 text-xs text-slate-500 bg-route-panel/95 backdrop-blur-md rounded-lg border border-white/10 px-4 py-3">
    Loading…
  </div>
);

const OperationsMap = () => {
  const [selectedEntity, setSelectedEntity] = useState(null);
  const [liveOperations, setLiveOperations] = useState(true);
  const [activeTab, setActiveTab] = useState('Overview');

  const live = useLiveOps();
  const [riderDetail, setRiderDetail] = useState(null);
  const selectedRiderId = selectedEntity?.type === 'RIDER' ? selectedEntity.id : null;

  useEffect(() => {
    setRiderDetail(null);
    if (!selectedRiderId) return;
    let stop = false;
    const load = () => api.riderDetail(selectedRiderId).then(d => { if (!stop && d.id) setRiderDetail(d); }).catch(() => {});
    load();
    const t = setInterval(load, 2000);
    return () => { stop = true; clearInterval(t); };
  }, [selectedRiderId]);

  const handleEntitySelect = (entity) => {
    setSelectedEntity(entity);
  };

  const handleZoomIn = () => {
    if (window.mapAPI) window.mapAPI.zoomIn();
  };

  const handleZoomOut = () => {
    if (window.mapAPI) window.mapAPI.zoomOut();
  };

  const handleReset = () => {
    if (window.mapAPI) window.mapAPI.resetView();
  };

  const isSimulation = false;

  return (
    <div className="relative w-full h-full bg-route-base">
      <TopNavigation
        liveOperations={liveOperations}
        setLiveOperations={setLiveOperations}
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />

      {!isSimulation && <KPIBar kpis={live.kpis} orders={live.orders} riders={live.riders} />}
      {!isSimulation && <ScenarioControls />}

      <RouteMap
        onEntitySelect={handleEntitySelect}
        liveOperations={liveOperations}
        simulationMode={isSimulation}
        darkStores={live.darkStores}
        riders={live.riders}
        orders={live.orders}
        trafficZones={live.trafficZones}
        riderDetail={riderDetail}
        demandZones={live.kpis?.zone_density || []}
        showDemandHeatmap={activeTab === 'Analytics'}
      />

      {activeTab === 'Orders' && <OrdersPanel orders={live.orders} onSelect={handleEntitySelect} />}
      {activeTab === 'Riders' && <RidersPanel riders={live.riders} onSelect={handleEntitySelect} />}
      {activeTab === 'Dark Stores' && <StoresPanel darkStores={live.darkStores} onSelect={handleEntitySelect} />}
      {activeTab === 'Optimization' && <OptimizationPanel riders={live.riders} />}
      {activeTab === 'Analytics' && (
        <Suspense fallback={<PanelLoading />}>
          <AnalyticsPanel kpis={live.kpis} riders={live.riders} />
        </Suspense>
      )}

      {!isSimulation && (
        <>
          <EntityPanel
            entity={selectedEntity}
            riderDetail={riderDetail}
            onClose={() => setSelectedEntity(null)}
          />

          <MapLegend />

          <MapControls
            onZoomIn={handleZoomIn}
            onZoomOut={handleZoomOut}
            onReset={handleReset}
          />

          <NetworkStatus kpis={live.kpis} orders={live.orders} riders={live.riders} />
        </>
      )}
    </div>
  );
};

export default OperationsMap;
