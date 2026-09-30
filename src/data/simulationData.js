/**
 * simulationData.js
 *
 * Static configuration for the Rider RX-104 simulation.
 * Route geometry is fetched at runtime from Mapbox Directions API.
 * See RouteEngine.js for the fetching logic.
 */

// Waypoints: [lng, lat] — real Mumbai road-network coordinates
export const WAYPOINTS = [
  [72.8295, 19.0596],  // 0: Bandra Dark Store
  [72.8273, 19.0639],  // 1: Order 1 – Bandra West (Linking Rd)
  [72.8371, 19.0720],  // 2: Order 2 – Khar West (16th Rd)
  [72.8364, 19.0847],  // 3: Order 3 – Santacruz West (Juhu Tara Rd)
];

// Which waypoint index each order corresponds to (1-indexed into WAYPOINTS)
export const simulationOrders = [
  {
    id: 'RX-2841',
    dest: WAYPOINTS[1],
    location: 'Bandra West',
    priority: 'HIGH',
    promise: '12 min',
    status: 'CURRENT',
    waypointIndex: 1,
  },
  {
    id: 'RX-2847',
    dest: WAYPOINTS[2],
    location: 'Khar West',
    priority: 'NORMAL',
    promise: '19 min',
    status: 'PENDING',
    waypointIndex: 2,
  },
  {
    id: 'RX-2853',
    dest: WAYPOINTS[3],
    location: 'Santacruz West',
    priority: 'NORMAL',
    promise: '27 min',
    status: 'PENDING',
    waypointIndex: 3,
  },
];

export const simulationRider = {
  id: 'RX-104',
  name: 'Aarav Mehta',
  vehicle: 'Motorcycle',
  status: 'ON DELIVERY',
  capacity: 5,
};

// Traffic detour waypoints (fetched separately when traffic event fires)
// Detour goes slightly around the congested area
export const TRAFFIC_DETOUR_WAYPOINTS = [
  null,               // placeholder – replaced at runtime with rider's current pos
  [72.8395, 19.0760], // Detour mid-point
  WAYPOINTS[3],       // still ends at final destination
];

// Simulation speed: metres per second at 1x
export const BASE_SPEED_MPS = 8; // ≈ 29 km/h realistic urban delivery
