# Last Mile Mission Control — Project Instructions

## Primary rule
Coverage of the official problem statement is PRIORITY #1. Do not spend significant time on optional AI, forecasting, visual effects, or extras until all six mandatory requirements are implemented end-to-end and demonstrable.

## Product
Build a real-time quick-commerce dispatch system that continuously matches each order to a feasible dark store and rider, optimizes/batches routes, adapts to disruptions, tracks delivery state, and reports operational performance.

## Mandatory requirements
1. Order & Demand Mapping — location, items, timestamp, promised window, priority, catalog/stock.
2. Rider & Dark Store Resource Management — rider location/capacity/load/shift/status; store location/inventory/packing capacity.
3. Dynamic Allocation — proximity, load, deadline, store selection, batching, fast decisions, continuous re-optimization.
4. Route Optimization & Adaptation — route/sequence optimization; new orders, cancellations, rider unavailability, traffic.
5. Tracking & Prioritization — complete lifecycle, delayed/failed/at-risk handling, time-sensitive prioritization.
6. Performance Analytics — average delivery time, on-time rate, rider utilization, zone density, delayed/failed deliveries.

## Preferred stack
React + Vite + TypeScript; MapLibre + deck.gl; FastAPI; WebSockets; Google OR-Tools; PostgreSQL; Recharts/ECharts.

## Build order
First make this complete slice work:
Order → stock-aware store match → rider allocation → route → rider movement → delivered → KPI update.

Then complete every PS requirement. Then improve optimization. Then UI polish. Optional differentiators come last.

## Engineering rules
- Separate domain logic from API/UI.
- Optimizer decisions must be explainable.
- Simulator must support deterministic seeds.
- Never assign infeasible rider/store pairs.
- Reserve stock on assignment.
- Avoid reassignment after pickup except failure recovery.
- Prefer stable assignments.
- Add tests for feasibility, scoring, batching, deadlines, cancellation, traffic and rider dropout.

## Definition of done
A feature is done only when real state flows through backend logic, appears in the UI, responds to relevant events, and is demonstrable.
