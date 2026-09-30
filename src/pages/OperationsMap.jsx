import React, { useState } from 'react';
import RouteMap from '../components/RouteMap';
import TopNavigation from '../components/TopNavigation';
import KPIBar from '../components/KPIBar';
import MapLegend from '../components/MapLegend';
import NetworkStatus from '../components/NetworkStatus';
import MapControls from '../components/MapControls';
import EntityPanel from '../components/EntityPanel';
import RiderSimulation from '../components/simulation/RiderSimulation';
import ScenarioControls from '../components/ScenarioControls';
import OrdersPanel from '../components/panels/OrdersPanel';
import RidersPanel from '../components/panels/RidersPanel';
import StoresPanel from '../components/panels/StoresPanel';
import OptimizationPanel from '../components/panels/OptimizationPanel';
import AnalyticsPanel from '../components/panels/AnalyticsPanel';
import useLiveOps from '../hooks/useLiveOps';

const OperationsMap = () => {
  const [selectedEntity, setSelectedEntity] = useState(null);
  const [liveOperations, setLiveOperations] = useState(true);
  const [activeTab, setActiveTab] = useState('Overview');
  const [mapInstance, setMapInstance] = useState(null);
  const live = useLiveOps();

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

  const isSimulation = activeTab === 'Simulation';

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
        onMapLoad={setMapInstance}
        darkStores={live.darkStores}
        riders={live.riders}
        orders={live.orders}
        trafficZones={live.trafficZones}
      />

      {isSimulation && mapInstance && (
        <RiderSimulation map={mapInstance} />
      )}

      {activeTab === 'Orders' && <OrdersPanel orders={live.orders} onSelect={handleEntitySelect} />}
      {activeTab === 'Riders' && <RidersPanel riders={live.riders} onSelect={handleEntitySelect} />}
      {activeTab === 'Dark Stores' && <StoresPanel darkStores={live.darkStores} onSelect={handleEntitySelect} />}
      {activeTab === 'Optimization' && <OptimizationPanel riders={live.riders} />}
      {activeTab === 'Analytics' && <AnalyticsPanel kpis={live.kpis} riders={live.riders} />}

      {!isSimulation && (
        <>
          <EntityPanel
            entity={selectedEntity}
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
