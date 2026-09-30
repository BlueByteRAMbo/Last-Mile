# Last Mile Mission Control — Implementation Plan & Claude Code Master Prompt
**TechNext Minithon 4.0 · The Last Mile Problem**

## Primary Rule & Guidelines
Coverage of the official problem statement is **PRIORITY #1**. Every mandatory feature must be fully functional, backed by real database state (Neon PostgreSQL), and visualised dynamically in the Mapbox 3D Mission Control UI.

---

## Environment & Configuration
- **Mapbox Access Token:** Read dynamically from `VITE_MAPBOX_TOKEN` in `.env`
- **Database URL (Neon PostgreSQL):** `postgresql://neondb_owner:npg_8U6zkFMBWpon@ep-dark-smoke-b536ei2e-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require`
- **3D Asset Paths:**
  - Delivery Rider Model: `/public/models/delivery-rider.glb` (or `/delivery_rider_3d.glb`)
  - Dark Warehouse Model: `/public/models/warehouse.glb` (or `/warehouse.glb`)

---

## Technical Stack Architecture
- **Frontend:** React 18 + Vite + Tailwind CSS + Mapbox GL JS (v3 with 3D models) + Lucide Icons + Recharts
- **Backend:** FastAPI + SQLAlchemy / AsyncPG + WebSockets + Google OR-Tools
- **Database:** Neon PostgreSQL (`neondb`)
- **Real-time Engine:** WebSockets fan-out for live rider movement, order progression, and metric recalculations

---

## Mandatory Requirements Checklist (The 6 PS Modules)

1. **Order & Demand Mapping**
   - Catalog & Dark Store Inventory mapping with real-time reservation.
   - Order creation (location lat/lng, item list, promised delivery window, priority tag).
   - Stock availability validation & automatic lock on assignment.

2. **Rider & Dark Store Resource Management**
   - Dark store packing capacity, active packing queue, inventory levels.
   - Rider live location, capacity (kg/volume), active load, shift status, battery/fuel, speed.

3. **Dynamic Allocation Engine (Explainable)**
   - Seconds-scale multi-criteria scoring algorithm:
     $$\text{Score} = w_1 \cdot \text{ETA} + w_2 \cdot \text{Load} + w_3 \cdot \text{DeadlineSlack} - w_4 \cdot \text{BatchingBenefit}$$
   - Continuous re-optimization loop.
   - Inspector Panel showing "Why this rider/store?" with ranked alternatives.

4. **Route Optimization & Adaptation**
   - Google OR-Tools / Cheapest-Insertion TSP & VRP with time windows.
   - Dynamic rerouting on traffic congestion, rider offline/dropout, order cancellation, and demand surge.

5. **Tracking, Status & Prioritization**
   - Lifecycle state machine: `created` → `assigned` → `packing` → `packed` → `out_for_delivery` → `delivered` (or `failed` / `cancelled`).
   - At-risk & delay indicators with priority queue boosting for tight SLA deadlines.

6. **Performance Analytics Dashboard**
   - Real-time computation of:
     - Average Delivery Time (mins)
     - On-Time Delivery Rate (%)
     - Rider Utilization (%)
     - Zone Demand Density
     - SLA Breach / Failure Rate

---

## 3D Map & UI Specification
- Render 3D Dark Warehouse model (`/models/warehouse.glb`) at store coordinates.
- Render 3D Delivery Rider model (`/models/delivery-rider.glb`) along route vectors.
- Map controls: Toggle 3D buildings, traffic heatmap, assignment arcs, rider paths, store packing pressure.

---

## Phased Execution Roadmap

### Phase 1: Core Vertical Slice
End-to-end flow: Order Creation → Stock Check & Reserve → Rider Allocation → 3D Route Movement → Delivery Complete → KPI Update.

### Phase 2: Full PS Requirements & DB Integration
Connect FastAPI backend to Neon PostgreSQL (`neondb`), run migrations, enforce inventory locking, OR-Tools VRP route generation, and explainable scoring logs.

### Phase 3: Simulator & Disruption Scenarios
Deterministic seed engine (`--seed=42`) with triggerable disruptions:
- Rain / High Traffic Surge
- Unexpected Rider Dropout
- Dark Store Stockout
- Last-Minute Order Cancellation

### Phase 4: UI Polish & Live Metrics
Connect WebSockets for zero-latency state sync, enable 3D models, smooth camera tracking, and live KPI strip updates.

---

## Engineering Rules
- **No Hardcoded Metrics:** All numbers must compute dynamically from database events.
- **Fail-safe Fallbacks:** If 3D GLB models fail to load, gracefully degrade to custom SVG/DOM markers.
- **Explainable Decisions:** Every allocation must return a structured reasoning payload for the UI inspector.
