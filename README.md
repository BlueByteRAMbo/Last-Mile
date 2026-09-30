# RouteX Logistics Command Center

This is a prototype for the RouteX logistics command-center map, built with React, Vite, Tailwind CSS, Mapbox GL JS, and Lucide React.

## 1. Installation

```bash
npm install
```

## 2. Environment variable & 3. Mapbox token setup

The application requires a Mapbox public token to render the 3D map.

1. Ensure you have a Mapbox account.
2. Get your default public token from the Mapbox dashboard.
3. Copy `.env.example` to `.env` at the root of the project.
4. Replace the placeholder with your Mapbox public token:
   `VITE_MAPBOX_TOKEN=your_mapbox_public_token_here`

*(Note: `.env` and `.env.local` are gitignored so tokens are not pushed to version control.)*

## 4. Development command

```bash
npm run dev
```

This will start the Vite development server. Open the provided local URL (typically `http://localhost:5173`) in your browser to view the application.

## 5. Architecture

The prototype is built with a component-based architecture for easy integration and maintainability.

*   `App.jsx`: Main entry point setting up the full-screen container.
*   `pages/OperationsMap.jsx`: The main page component that orchestrates all map-related UI and state.
*   `components/RouteMap.jsx`: The core Mapbox implementation handling 3D layers, routes, and custom markers.
*   `components/TopNavigation.jsx`, `KPIBar.jsx`, `MapLegend.jsx`, `NetworkStatus.jsx`, `MapControls.jsx`: Floating UI overlays.
*   `components/EntityPanel.jsx`: Detail view for selected logistics entities (riders, orders, stores).

## 6. How mock data is structured

Mock data is stored in `src/data/mockData.js`. It contains separate arrays for:
*   `darkStores`: Hubs for dispatching orders.
*   `riders`: Delivery personnel with location and status.
*   `orders`: Individual deliveries with varied risk levels.
*   `routes`: GeoJSON LineString coordinates connecting hubs, riders, and destinations.
*   `trafficZones`: Circular polygon approximations for high/medium traffic areas.

## 7. Integration

To integrate the `RouteMap` component into a larger React application:
1. Ensure the parent container has defined dimensions (e.g., `w-full h-full`).
2. Import the component: `import RouteMap from './components/RouteMap';`
3. Pass required props like `onEntitySelect` to handle interactions.
4. Overlay your own UI components using absolute positioning over the map container.
