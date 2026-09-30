import React, { useState } from 'react';
import RouteMap from '../components/RouteMap';
import TopNavigation from '../components/TopNavigation';
import KPIBar from '../components/KPIBar';
import MapLegend from '../components/MapLegend';
import NetworkStatus from '../components/NetworkStatus';
import MapControls from '../components/MapControls';
import EntityPanel from '../components/EntityPanel';
import RiderSimulation from '../components/simulation/RiderSimulation';

const OperationsMap = () => {
  const [selectedEntity, setSelectedEntity] = useState(null);
  const [liveOperations, setLiveOperations] = useState(true);
  const [activeTab, setActiveTab] = useState('Overview');
  const [mapInstance, setMapInstance] = useState(null);

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

  return (
    <div className="relative w-full h-full bg-route-base">
      <TopNavigation 
        liveOperations={liveOperations} 
        setLiveOperations={setLiveOperations} 
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />
      
      {activeTab === 'Overview' && <KPIBar />}
      
      <RouteMap 
        onEntitySelect={handleEntitySelect} 
        liveOperations={liveOperations} 
        simulationMode={activeTab === 'Simulation'}
        onMapLoad={setMapInstance}
      />
      
      {activeTab === 'Simulation' && mapInstance && (
        <RiderSimulation map={mapInstance} />
      )}
      
      {activeTab === 'Overview' && (
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
          
          <NetworkStatus />
        </>
      )}
    </div>
  );
};

export default OperationsMap;
