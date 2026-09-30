export const darkStores = [
  { id: 'DS-1', name: 'Andheri Hub', lat: 19.1136, lng: 72.8697, ordersQueued: 14, packing: 6, availableRiders: 4, capacity: 82 },
  { id: 'DS-2', name: 'Bandra Hub', lat: 19.0596, lng: 72.8295, ordersQueued: 8, packing: 3, availableRiders: 6, capacity: 60 },
  { id: 'DS-3', name: 'Powai Hub', lat: 19.1176, lng: 72.9060, ordersQueued: 22, packing: 10, availableRiders: 2, capacity: 95 },
  { id: 'DS-4', name: 'Lower Parel Hub', lat: 18.9953, lng: 72.8300, ordersQueued: 12, packing: 5, availableRiders: 5, capacity: 70 },
  { id: 'DS-5', name: 'Dadar Hub', lat: 19.0178, lng: 72.8478, ordersQueued: 18, packing: 8, availableRiders: 3, capacity: 88 },
];

export const riders = [
  { id: 'RX-101', name: 'Rider 101', lat: 19.1000, lng: 72.8600, status: 'AVAILABLE', capacity: 5, currentLoad: 0, assignedOrders: 0 },
  { id: 'RX-102', name: 'Rider 102', lat: 19.0600, lng: 72.8400, status: 'ON_DELIVERY', capacity: 5, currentLoad: 3, assignedOrders: 3, eta: '12m', utilization: 60 },
  { id: 'RX-103', name: 'Rider 103', lat: 19.1200, lng: 72.9000, status: 'NEAR_CAPACITY', capacity: 5, currentLoad: 4, assignedOrders: 4, eta: '05m', utilization: 80 },
  { id: 'RX-104', name: 'Rider 104', lat: 19.0000, lng: 72.8200, status: 'ON_DELIVERY', capacity: 5, currentLoad: 2, assignedOrders: 2, eta: '08m', utilization: 40 },
  { id: 'RX-105', name: 'Rider 105', lat: 19.0200, lng: 72.8500, status: 'OFFLINE', capacity: 5, currentLoad: 0, assignedOrders: 0 },
  { id: 'RX-106', name: 'Rider 106', lat: 19.1150, lng: 72.8750, status: 'AVAILABLE', capacity: 5, currentLoad: 0, assignedOrders: 0 },
  { id: 'RX-107', name: 'Rider 107', lat: 19.0550, lng: 72.8350, status: 'ON_DELIVERY', capacity: 5, currentLoad: 1, assignedOrders: 1, eta: '15m', utilization: 20 },
  { id: 'RX-108', name: 'Rider 108', lat: 19.1100, lng: 72.9100, status: 'NEAR_CAPACITY', capacity: 5, currentLoad: 5, assignedOrders: 5, eta: '02m', utilization: 100 },
  { id: 'RX-109', name: 'Rider 109', lat: 19.0050, lng: 72.8250, status: 'ON_DELIVERY', capacity: 5, currentLoad: 3, assignedOrders: 3, eta: '10m', utilization: 60 },
  { id: 'RX-110', name: 'Rider 110', lat: 19.0150, lng: 72.8450, status: 'AVAILABLE', capacity: 5, currentLoad: 0, assignedOrders: 0 },
  { id: 'RX-111', name: 'Rider 111', lat: 19.0900, lng: 72.8500, status: 'ON_DELIVERY', capacity: 5, currentLoad: 2, assignedOrders: 2, eta: '11m', utilization: 40 },
  { id: 'RX-112', name: 'Rider 112', lat: 19.0700, lng: 72.8600, status: 'ON_DELIVERY', capacity: 5, currentLoad: 4, assignedOrders: 4, eta: '04m', utilization: 80 },
  { id: 'RX-113', name: 'Rider 113', lat: 19.1050, lng: 72.8900, status: 'AVAILABLE', capacity: 5, currentLoad: 0, assignedOrders: 0 },
  { id: 'RX-114', name: 'Rider 114', lat: 19.0100, lng: 72.8350, status: 'NEAR_CAPACITY', capacity: 5, currentLoad: 4, assignedOrders: 4, eta: '06m', utilization: 80 },
  { id: 'RX-115', name: 'Rider 115', lat: 19.0250, lng: 72.8550, status: 'OFFLINE', capacity: 5, currentLoad: 0, assignedOrders: 0 },
];

export const orders = [
  { id: 'ORD-2841', lat: 19.0950, lng: 72.8550, status: 'NORMAL', priority: false, eta: '14m', promise: '15m', rider: 'RX-102', darkStore: 'Andheri Hub', risk: 'LOW' },
  { id: 'ORD-2842', lat: 19.0650, lng: 72.8450, status: 'PRIORITY', priority: true, eta: '09m', promise: '10m', rider: 'RX-102', darkStore: 'Bandra Hub', risk: 'LOW' },
  { id: 'ORD-2843', lat: 19.1250, lng: 72.9050, status: 'AT_RISK', priority: false, eta: '06m', promise: '05m', rider: 'RX-103', darkStore: 'Powai Hub', risk: 'HIGH' },
  { id: 'ORD-2844', lat: 19.0050, lng: 72.8150, status: 'NORMAL', priority: false, eta: '07m', promise: '10m', rider: 'RX-104', darkStore: 'Lower Parel Hub', risk: 'LOW' },
  { id: 'ORD-2845', lat: 19.0500, lng: 72.8300, status: 'NORMAL', priority: false, eta: '16m', promise: '20m', rider: 'RX-107', darkStore: 'Bandra Hub', risk: 'LOW' },
  { id: 'ORD-2846', lat: 19.1050, lng: 72.9150, status: 'DELAYED', priority: true, eta: '03m', promise: '00m', rider: 'RX-108', darkStore: 'Powai Hub', risk: 'SEVERE' },
  { id: 'ORD-2847', lat: 19.0100, lng: 72.8200, status: 'NORMAL', priority: false, eta: '11m', promise: '15m', rider: 'RX-109', darkStore: 'Lower Parel Hub', risk: 'LOW' },
  { id: 'ORD-2848', lat: 19.0850, lng: 72.8450, status: 'AT_RISK', priority: false, eta: '12m', promise: '10m', rider: 'RX-111', darkStore: 'Andheri Hub', risk: 'HIGH' },
  { id: 'ORD-2849', lat: 19.0750, lng: 72.8650, status: 'NORMAL', priority: false, eta: '05m', promise: '10m', rider: 'RX-112', darkStore: 'Dadar Hub', risk: 'LOW' },
  { id: 'ORD-2850', lat: 19.0150, lng: 72.8300, status: 'DELAYED', priority: true, eta: '08m', promise: '05m', rider: 'RX-114', darkStore: 'Dadar Hub', risk: 'SEVERE' },
  // ... more orders could be added
];

export const routes = [
  {
    id: 'RTE-1',
    riderId: 'RX-102',
    status: 'ACTIVE',
    coordinates: [
      [72.8295, 19.0596], // Bandra Hub
      [72.8400, 19.0600], // Rider
      [72.8450, 19.0650], // Order
    ]
  },
  {
    id: 'RTE-2',
    riderId: 'RX-103',
    status: 'AT_RISK',
    coordinates: [
      [72.9060, 19.1176], // Powai Hub
      [72.9000, 19.1200], // Rider
      [72.9050, 19.1250], // Order
    ]
  },
  {
    id: 'RTE-3',
    riderId: 'RX-108',
    status: 'DELAYED',
    coordinates: [
      [72.9060, 19.1176],
      [72.9100, 19.1100],
      [72.9150, 19.1050],
    ]
  },
  {
    id: 'RTE-4',
    riderId: 'RX-111',
    status: 'AT_RISK',
    coordinates: [
      [72.8697, 19.1136],
      [72.8500, 19.0900],
      [72.8450, 19.0850],
    ]
  }
];

export const trafficZones = [
  {
    id: 'TRF-1',
    level: 'HIGH',
    center: [72.8550, 19.0750],
    radius: 1.5,
  },
  {
    id: 'TRF-2',
    level: 'MEDIUM',
    center: [72.8350, 19.0250],
    radius: 2.0,
  },
  {
    id: 'TRF-3',
    level: 'HIGH', // Road disruption
    center: [72.9000, 19.1050],
    radius: 1.0,
  }
];
