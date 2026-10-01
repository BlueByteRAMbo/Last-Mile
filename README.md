# RouteX: Last Mile Mission Control

A quick-commerce dispatch simulator for Mumbai. Place a basket, watch stock-based
store selection and rider allocation, follow delivery on a live map, and inject
traffic to see threshold-based route decisions. No real payment or delivery occurs.

Built with FastAPI, SQLAlchemy, React, Vite, Tailwind, Mapbox GL and Recharts.

## Run locally

Python 3.11+ and Node.js are required. From the repository root on Windows:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements.txt
npm install
Copy-Item .env.example .env
```

Set your own values in `.env`. Start two terminals:

```powershell
# Terminal 1
cd backend
.\.venv\Scripts\python.exe run.py
```

```powershell
# Terminal 2, repository root
npm run dev
```

On macOS/Linux use `backend/.venv/bin/python` instead of the Windows interpreter
path. Backend runs at `http://127.0.0.1:8000`; open the Vite URL printed in terminal
(normally `http://localhost:5173`). Schema additions and initial seeding run at startup.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL URL; unset uses local SQLite with aiosqlite |
| `VITE_MAPBOX_TOKEN` | Map display token, also accepted by backend Directions |
| `MAPBOX_TOKEN` | Alternative backend Directions token |
| `VITE_API_URL` | Frontend API URL; defaults to `http://localhost:8000` |

Vite loads root env files; backend calls python-dotenv from its own process context.
Ensure the required values are available to both processes. Do not commit credentials.
Without Directions, paths use labeled straight-line estimates. Without a map token,
the map displays an unavailable message while status tracking still works.

## Pages

- `#shop`: catalog, cart, name, preset Mumbai delivery addresses and regular/express.
- `#journey/ORDER-ID`: stock evidence, selected store, ranked riders, live journey,
  traffic placement, route decisions and a link to customer tracking.
- `#track/ORDER-ID`: customer-safe live map, ETA and timestamped delivery timeline.
- `#ops` (or no hash): fleet dashboard, order interventions, inventory and analytics.

The old canned Simulation tab is no longer used. Journey and customer screens are
driven by actual backend orders, routes and WebSocket updates.

## Three-minute presentation

1. **0:00-0:30:** Open `#shop`. Add Curd 400g and choose the residential address near
   Powai Hub, enter a name and place the order. The seeded Powai inventory has curd;
   Andheri does not, demonstrating that the nearest physical store alone is insufficient.
2. **0:30-1:10:** Walk through Stock check, Nearest store and Rider allocation. Green
   stores cover the full quantities. Inspect the selected rider and cost components.
3. **1:10-2:00:** Open the customer tracking link in another tab. Return to Journey,
   enable Follow rider and wait for pickup. Normal packing takes 75 seconds. The
   timeline and ETA come from the same live simulation in both views.
4. **2:00-2:30:** Select Simulate traffic and click the rider's active path. Choose
   radius/severity/duration. The red zone slows travel; the response explains whether
   an alternative clears max(45 seconds, 10%) savings. A switch is not guaranteed:
   keeping the current route is a valid, visible decision. A dashed amber candidate
   and old-route flash appear when geometry is returned.
5. **2:30-3:00:** Show delivery completion if reached and the updated fleet KPIs.
   Open Operations > Analytics: trends, utilization, delay signals, fairness and
   Compare the same seeded demand. Start the comparison earlier if presenting on
   a slow machine; it runs independently while live operations continue.

This is a three-minute presentation sequence, not a guarantee that every route
finishes in three minutes. Stock, existing rider work, roads and traffic change ETA.
Reset Scenario clears orders/history and restores seeded inventory/riders.

## Analytics and dispatch modes

- Optimized dispatch chooses the nearest stock-eligible store with a feasible rider,
  then scores riders for travel, packing, workload, deadline and batching effects.
- Nearest mode ranks eligible candidates by pickup ETA and disables rolling route
  optimization. The Analytics selector applies to future live allocations.
- The comparison replays the same 36 seed-42 orders against both modes in an isolated
  process using the real tick engine. Initial resources and straight-line routes are
  identical; no external disruptions/provider variability. Results are cached.
- Comparison reports both on-time/all-orders and on-time/delivered, plus average
  delivery time, failures and unfinished orders. Do not interpret it as live-road proof.
- Time utilization is busy assignment time / observed simulated shift time. Offline
  shift time counts as idle; server downtime is excluded. Counters persist.
- Gini measures inequality of completed deliveries per rider (0 = equal or no work).
- Demand heatmap is weighted at nearest-hub catchment centers, not customer locations.
- Delay signals count distinct affected orders per category; categories can overlap.
  Packing wait reflects current at-risk packing, while other signals include history.
- Five-minute on-time buckets have no rate when no deliveries occurred. Disruption
  bars count order impact events, not necessarily distinct traffic zones.

## Verification

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/ -q
cd ..
npm run build
```

Optional live checks (isolated in-memory SQLite; do not touch a running database):

```powershell
backend/.venv/Scripts/python scripts/smoke_comparison.py
backend/.venv/Scripts/python scripts/smoke_browser.py
```

The browser script uses installed Chrome on Windows, ports 8012/5178/9225, faster
test-only packing/riders, and real configured Mapbox services. It creates a temporary
browser profile and screenshots under the OS temp directory. Failed readiness checks
write order/rider/page diagnostics. The comparison smoke uses port 8013 and verifies
that live WebSocket ticks continue during the actual replay subprocess.

## Architecture

`backend/app/world.py` is live state, not the database. Ticks perform no DB/network
I/O; dirty fields persist in batches every three seconds under the reset/write lock.
Directions requests run outside the tick. `world.events` combines loaded history
with immediately visible events. New mutable fields need a dirty marker and an entry
in the corresponding mutable-column list. SQLite datetimes require UTC normalization.

Customer `/ws/track/{id}` subscriptions receive only customer-safe order projections;
ops `/ws` carries fleet snapshots. REST bootstrap and reconnecting subscriptions
support tracking through terminal delivery. `HANDOVER.md` contains implementation
context, validation history and known limitations for continuing development.
