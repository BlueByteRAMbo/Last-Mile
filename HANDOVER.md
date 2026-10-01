# Handover — Last Mile Mission Control

Read this fully before touching code. It will save you from re-discovering three real bugs
someone already hit and fixed. Everything below is accurate as of commit `5bbf4c6`.

## What this is

Quick-commerce dispatch simulator for a hackathon (TechNext Minithon 4.0). FastAPI + SQLAlchemy
backend, React + Vite + Tailwind + Mapbox frontend. Neon Postgres in prod, SQLite fallback for
local dev. A deterministic simulator (seed 42) spawns orders, allocates them to dark
stores/riders, moves riders along real roads, and reacts to disruptions (traffic, rider dropout,
stockout, cancellation) — all broadcast live over WebSocket.

The master spec (6 phases) that's driving this build is pasted verbatim at the bottom of this
file. **Read "Remaining work" below first** — it tells you what's done vs not; the spec itself
doesn't know what's been built.

## Run it

```bash
cd backend && python -m venv .venv && .venv/Scripts/activate  # or source .venv/bin/activate on mac/linux
pip install -r requirements.txt
cp ../.env.example ../.env   # fill in your own DATABASE_URL + VITE_MAPBOX_TOKEN
python run.py                 # serves on :8000, auto-migrates schema, seeds if empty
```
```bash
npm install
npm run dev                   # serves on :5173
```
```bash
cd backend && python -m pytest tests/ -q   # 58 tests, should all pass, ~3s
npm run build                              # should be clean
```

No `DATABASE_URL` set → `db.py` falls back to local SQLite (`lastmile.db`) automatically, no setup
needed for quick iteration. Real Mapbox Directions calls need `VITE_MAPBOX_TOKEN` (or
`MAPBOX_TOKEN`) in the backend's env too — `routing.py` reads it, falls back to straight-line
haversine silently if missing or if any fetch fails.

**Credentials**: the Neon password in git history (pre-Phase-0 commits) is compromised — rotate it
if that hasn't happened. Current `.env` values are gitignored and fine as-is.

## Architecture — read this before changing anything in the tick loop

The single most important thing to understand: **`backend/app/world.py` is the source of truth,
not the database.** Everything the simulator touches every tick lives in-memory as plain detached
SQLAlchemy ORM objects (`world.stores`, `world.riders`, `world.orders`, `world.inventory`). The
tick loop (`simulator.tick_sync()`) does **zero** DB round trips — that's deliberate, not an
oversight. A separate background loop (`simulator.persist_loop()`, every 3s) batches whatever got
marked dirty and writes it to Postgres.

**If you add a new mutable field to Order/Rider/InventoryItem, you must also add it to the
`*_MUTABLE_COLUMNS` list in `world.py`** or it'll never get persisted. Read-after-write within a
tick works fine (same in-memory object); read-after-write across a server restart does not unless
you did this.

**Mutations always go through `world.mark_*_dirty(id)`** — plain attribute assignment doesn't
auto-track like a real ORM session would, because these objects aren't attached to a session.

**New endpoints must read from `world`, not from a DB query** — a DB read will be up to 3s stale
during the tick's lifetime and defeats the whole point of this architecture. Grep `main.py` for
`world.orders.values()` / `world.riders` for the pattern every existing endpoint uses.

**The tick loop must never `await` anything network-bound.** This was the single biggest
performance bug in the whole project (see "bugs already hit" below) — ticks were taking 30-40s
before this was fixed, now ~70-100ms. If you need real road routing data (Mapbox Directions),
follow the pattern in `routing.py`: a sync cache lookup (`get_cached_route`, safe in the tick) plus
an async fetch (`ensure_route`) fired as a **background task** from the async `tick()` wrapper, not
awaited inline. Same pattern for anything else that needs network I/O from the simulation.

**Schema changes need no manual migration.** `db.py:auto_migrate()` diffs every model's columns
against the live table and `ALTER TABLE ADD COLUMN`s whatever's missing, on every startup. Just
add the field to the model and restart — don't hand-write SQL for this.

## Bugs already hit and fixed — don't re-introduce these

1. **N+1 queries + reconnecting every tick.** Original tick() queried per-rider/per-store inside
   loops and opened a fresh DB connection every 2s (Neon's connect handshake alone was ~5s). Fixed
   by the world-state rewrite above. If you see tick times creeping back up, check you haven't
   added a query inside a loop or an `await session.execute(...)` inside `tick_sync()`.

2. **Deadlock between `/reset` and the persist loop.** Both were writing to the `orders` table
   concurrently from separate sessions/transactions → Postgres deadlock. Fixed with
   `world.db_write_lock` (an `asyncio.Lock`), held for the *entire* duration of both `/reset` and
   `persist_once()` — including the snapshot step, not just the write. If you add another endpoint
   that does a bulk DB write outside the normal dirty-tracking flow, wrap it in this same lock.

3. **Stale-snapshot race → FK violation.** `persist_once()` used to snapshot dirty state *then*
   acquire the lock; a persist that started just before a `/reset` could write `order_events`
   referencing orders the reset had just deleted. Fixed by moving the lock to wrap the whole
   function, snapshot included.

4. **`create_all` doesn't add columns to existing tables.** Only matters for Postgres, since Neon
   already had an `orders` table from an earlier phase when `customer_name` was added — crashed
   startup with `UndefinedColumnError`. This is why `auto_migrate()` exists; see above.

5. **Mapbox `model` source/layer crashes mapbox-gl 3.1.2.** Tried real 3D GLB models for
   warehouses via `map.addSource({type: 'model', ...})` — throws `getModels is not a function` on
   *every single render frame* when combined with the Standard style's shadow renderer. Confirmed
   by direct testing, not a config issue. Reverted to DOM markers
   (`src/components/RouteMap.jsx`). If you want 3D models, this needs a different approach
   (deck.gl `ScenegraphLayer` is what the master spec suggests as the fallback — untried) or a
   newer mapbox-gl version.

6. **SQLite round-trips strip tzinfo.** `Rider.shift_end` and similar datetime comparisons need a
   `.tzinfo is None` guard before comparing against a timezone-aware `datetime.now(timezone.utc)`,
   or you get `TypeError: can't compare offset-naive and offset-aware datetimes` — but only in
   tests (SQLite), not against real Postgres. See `dispatch.py:score_candidates_sync` for the
   pattern.

## What's actually done (Phases 0-3)

Don't take the phase headers in the pasted spec at face value — cross-check against this list,
which reflects what's real and tested, not what was asked for.

**Phase 0 (credentials, lifespan, world-state, code-splitting)** — fully done.
- `db.py`, `world.py` (new), lifespan handler in `main.py`, `AnalyticsPanel`/`RiderSimulation`
  lazy-loaded in `OperationsMap.jsx`.

**Phase 1 (catalog, inventory, customer identity)** — fully done.
- `catalog.py` (new, 22 SKUs), uneven inventory in `seed_data.py`, `customer_name`/`address_label`
  on Order, `GET /catalog/availability`, `POST /dark_stores/{id}/restock`, `StoresPanel.jsx` shows
  stock bars/low-stock badges/restock button.
- Shift-end and low-battery exclusions were also added here (small, opportunistic) —
  `dispatch.py:score_candidates_sync`, `LOW_BATTERY_PCT`.

**Phase 2 (allocation engine)** — fully done.
- Real batching feasibility (90s detour threshold + no-broken-promise check) —
  `dispatch.py:cheapest_insertion_cost`. This used to always return `feasible=True`; now it's a
  real constraint, caught by writing the test for it.
- `packing_wait` computed from real per-store queue depth (was hardcoded 0).
- `rolling_reoptimize_sync` only applies a resequence if it saves ≥60s or fixes a missed deadline;
  runs every 3rd tick (~6s), not every tick. Logs `ROUTE_CHANGED` with the reason.
- `/orders/{id}/explain` has a nearest-store ranking and chosen-vs-runner-up cost delta.
- `suggest_split_fulfillment()` — when no single store has the full cart, returns best-partial-store
  + a two-store split if one covers everything.

**Phase 3 (road routing)** — fully done, verified live against real Mapbox + Neon.
- `routing.py` (new): real Mapbox Directions, cached, haversine fallback, architected so the tick
  loop never awaits network I/O (see Architecture above).
- Riders move along real road polylines (`Rider.nav_origin_*`, `nav_target_*`,
  `route_progress_km` — persisted). Falls back to straight-line until the real route lands.
- Traffic zones slow only the polyline segment actually inside them, not the whole leg.
- `POST /disruptions/traffic` takes `lat`/`lng`/`radius_km`/`multiplier`/`duration_minutes`
  directly (for a future UI click-to-place — not wired up in Phase 5 yet, backend's ready).
- `evaluate_reroute()` in `main.py`: on a new zone, fetches real alternatives from the rider's
  *live* position, switches only if gain ≥ max(45s, 10%), else logs "kept current route" — both
  outcomes logged, verified live with real gain numbers.
- `stockout` now bounces pre-pickup orders at that store back to the pool (was a no-op for
  already-assigned orders before).

**Test count**: 58, all passing, ~3s. **Both builds clean** (`pytest`, `npm run build`).

## What's NOT done — Phases 4, 5, 6

### Phase 4 (Tracking, prioritisation, analytics) — implemented

Update (2026-10-01): `tracking.py` now supplies shared live ETA projections for
`build_snapshot()` and `/track/{id}`. Snapshot orders include customer name, ETA,
predicted lateness and route version; riders include remaining geometry, heading,
assigned order IDs and an approximate-route flag. Geometry hashes stay stable during
movement and change when the path changes. ETA includes packing, pickup-before-drop,
earlier deliveries, cached geometry and traffic; it remains an estimate (packing queue
contention and future route changes are not forecast). Unassigned/offline ETA is null.
Terminal orders remain excluded from ops snapshots; tracking HTTP returns delivered ETA 0.
64 backend tests pass; frontend production build passes with the existing chunk-size warning.
Live WebSocket, customer tracking HTTP and frontend HTTP smoke checks pass using isolated
in-memory SQLite. Real Neon/Mapbox integration has not been revalidated in this increment.
Next increment (2026-10-01): the Orders tab now defaults to a live priority queue
(urgency from ETA/deadline slack + 5 express points + overdue minutes), with an at-risk
filter, ETA and predicted-late labels. Per-order boost/reassign/cancel controls call
`POST /orders/{id}/intervene/{action}` and display failures instead of reporting false success.
Reassignment selects another feasible rider at the same store, preserves packing and stock,
updates rider loads and route sequence, and logs REASSIGNED. If no alternative is feasible,
the assignment is kept (HTTP 409); picked-up and terminal orders cannot be reassigned.
Boost is idempotent, logged, and persists through `ORDER_MUTABLE_COLUMNS` (priority was
previously missing). Cancel uses the existing stock/load release behavior. Queue scores are
in ops REST/WebSocket payloads but excluded from customer tracking HTTP.
69 tests pass; production build passes with the existing chunk-size warning. Live isolated
SQLite HTTP + WebSocket smoke checks pass for boost, reassignment and cancellation.
Analytics increment (2026-10-01): `/analytics` and `/kpis` now share an in-memory
projection with per-rider time utilization, workload Gini, separate failed/cancelled
and overdue counts, named nearest-hub catchment demand, distinct-order delay signals,
and five-minute on-time rates over the last hour with disruption impact events.
Rider `busy_seconds` and `observed_shift_seconds` auto-migrate and persist. The tick
samples simulated shift time: active assignment means busy, offline means idle,
expired shifts stop counting, and server downtime is excluded. Historical utilization
before these counters existed cannot be reconstructed and starts at zero.
`world.events` is loaded once and appended alongside pending persistence events; event
timestamps now record occurrence time, not flush time. Analytics never queries the DB.
Packing-wait signals are current at-risk packing orders, not historical causal proof;
other delay signals come from events and may overlap. Unallocated is intentionally not
labelled rider shortage because it can also mean stock constraints. Empty delivery
intervals have null rates. The Analytics tab charts these metrics and displays a
heatmap weighted at hub centers (catchment aggregates, not customer point density).
76 tests pass, including migration defaults and persistence/reload/reset behavior.
Live isolated SQLite analytics/disruption/reset HTTP checks pass. Production build
passes with the existing large-bundle warning; real Mapbox rendering and Neon have
not been revalidated. Phase 4 is not complete: baseline comparison remains next.

1. Implemented in the update above: per-order `eta_seconds`, `predicted_late` (bool), `customer_name`,
   route polyline version; per-rider `current polyline remaining`, `assigned order ids`, `heading`.
   `simulator.py:build_snapshot()` now sends this extended payload. The rider's
   real polyline is available via `routing.get_cached_route(rider.nav_origin_lat, ...)` if you want
   to send the actual remaining geometry, not just lat/lng.
2. Implemented: Orders tab priority queue, at-risk filter and per-order intervention buttons
   (reassign/boost priority/cancel). See the next-increment notes above for endpoint semantics.
3. Customer tracker (`#track/{id}`, `src/pages/CustomerTracker.jsx`) already exists from an earlier
   session — Phase 5 asks you to extend it with live map/timeline; see Phase 5 below.
4. Implemented: time utilization, named catchment demand and heatmap, delay-signal
   breakdown, on-time series with disruption impacts, and workload Gini. See analytics
   increment notes above for definitions and validation limits.
5. Baseline comparison is implemented. Analytics offers a live dispatch mode selector and
   an isolated 36-order, seed-42 replay of both modes using the real tick engine. The same
   initial inventory/riders and order stream are used, with deterministic straight-line routes
   and no external disruptions. Results include delivered-only and all-order on-time rates,
   average delivery time, failures and unfinished orders. `/analytics/comparison` caches the
   reproducible replay result; `/dispatch/mode` controls future live allocations. Nearest
   mode retains eligibility checks but ranks by pickup ETA and disables rolling optimization.
   Seed inventory now resets deterministically (the old module RNG drifted across resets).

### Phase 5 (the guided demo flow) — not started, this is the big one

This is explicitly "the demo" — probably the highest-value remaining work for a judged hackathon,
and currently entirely missing. Everything backend-side it needs mostly already exists (orders,
allocation, explain, tracking, routing); this is almost entirely frontend.

**Screen A — storefront (`#shop`)**: doesn't exist. Needs: product grid from `GET /catalog`
(already has category/price/emoji), cart, customer name + location picker (small Mapbox map or
preset addresses), priority toggle, "Place order" → `POST /orders` (already accepts
`customer_name`/`address_label`/`priority`) → navigate to dashboard with that order focused, plus
show the `#track/{id}` link.

**Screen B — the guided dashboard sequence**: doesn't exist — the current `OperationsMap.jsx` is
the general ops dashboard, not this focused step-by-step view. You'd build a new page/mode that,
given a focused order ID, walks through: stock-check glow (use `GET /catalog/availability`) →
nearest-store arc → rider shortlist + chosen-rider highlight with floating "Order #ID — Name"
label (use `GET /orders/{id}/explain`, already has candidates + reasons) → journey along the real
road polyline with a follow-camera (the Simulation tab's `FollowCamera.js`/`RiderModel.js` already
has camera-follow and GLB-with-DOM-fallback logic you can likely reuse/adapt, though it's wired to
the OLD canned `simulationData.js`, not live data — needs rewiring) → traffic-zone click tool (map
click → `POST /disruptions/traffic?lat=..&lng=..`, backend's ready) → reroute toast using
`evaluate_reroute`'s real response shape (`switched`, `gain_seconds`, `old_eta_seconds`,
`new_eta_seconds` — already exactly what the spec's toast wants).

**Screen C — customer tracker**: `CustomerTracker.jsx` exists and shows a timeline + ETA already,
but has **no map at all**. Needs: full-width map (reuse `RouteMap.jsx` patterns, simplified —
customer pin, store, rider with live path), and should switch from polling (`api.track`) to
WebSocket for true live updates. Never expose `/orders/{id}/explain`'s cost numbers on this page —
customer-facing, the `/track/{id}` endpoint is already deliberately scrubbed of internal scores,
keep using that one, not `/explain`.

**The old Simulation tab** (`src/components/simulation/*`, ~1450 lines) is explicitly meant to be
removed/rebuilt per the spec ("Remove or rebuild the current hard-coded Simulation tab so it is
driven by the backend") — it currently runs on canned `src/data/simulationData.js`, not live
state. Decide whether to delete it outright or cannibalize `FollowCamera.js`/`RiderModel.js` for
Screen B's journey view before deleting the rest.

### Phase 6 (optional extras) — not started, lowest priority

Chaos console buttons (mostly wiring existing disruption endpoints to UI buttons — backend-ready),
demand forecast, dynamic promise time at checkout, time-travel replay (`OrderEvent` log already has
the raw material, needs a replay endpoint + UI). Only touch this if 4 and 5 are solid.

## Working conventions this project has been following

- **Ponytail/lazy-first**: smallest correct implementation, no speculative abstraction, reuse
  before adding. Don't gold-plate Phase 6 if 4/5 aren't done.
- **Every new backend behavior gets a test** before moving on — the existing 58 are the safety net
  for the world-state architecture especially; don't skip this because it feels slow.
- **Verify live, not just unit tests**: several of the bugs above only showed up against real Neon
  + real Mapbox under real timing, not in the SQLite-backed test suite. Start both servers
  (`backend/run.py` + `npm run dev`) and actually hit the running app before calling something
  done, especially anything touching the tick loop or routing.
- **Commit after each phase** (not each file), with a commit message that states what broke and
  how it was found, not just what changed — the commit log for Phases 0-3 is itself useful context
  if you need more detail than this doc gives.
- Windows dev environment; line endings are CRLF-normalized by git, warnings about it on commit are
  expected and harmless.

## Full original spec (for reference — see "What's NOT done" above for what still applies)

<details>
<summary>Click to expand the full 6-phase spec as given</summary>

ROLE
You are a senior full-stack engineer finishing a hackathon project, "Last Mile Mission Control"
(quick-commerce dispatch). The repo already has a FastAPI + SQLAlchemy backend (backend/app) and a
React + Vite + Tailwind + Mapbox frontend (src). Read backend/app/*.py, src/pages, src/components
and .claude/CLAUDE.md first. Do not rewrite what works; extend it. Work in the phases below, in
order, and after each phase run `pytest` and `npm run build`, then commit.

PRIORITY RULE
Problem-statement coverage comes first (PHASE 0 to 4). The guided customer-to-delivery simulation
(PHASE 5) comes after. Polish and extras (PHASE 6) are last and optional.

PHASE 0: Hygiene and unblockers
1. Remove the Neon credentials from .env.example and .claude/CLAUDE.md. Use placeholders. Tell me
   to rotate the leaked password.
2. db.py: default to sqlite+aiosqlite:///./lastmile.db when DATABASE_URL is unset; only pass
   ssl=require for postgres URLs.
3. Replace @app.on_event with a lifespan handler. Make /reset also clear traffic zones and reset
   simulator state.
4. Make the in-memory world (stores, riders, active orders, inventory) the source of truth during
   ticks; persist changes in batched writes so a tick stays well under 500 ms.
5. Code-split AnalyticsPanel and the simulation view with React.lazy.

PHASE 1: Orders, catalog, inventory (Requirement 1 and 2)
1. Expand the catalog to about 20 SKUs with categories, price, image emoji, weight. Seed UNEVEN
   inventory per store (some SKUs zero or low at some stores) so that stock genuinely decides which
   store can serve an order.
2. Order gets customer_name and delivery address label. POST /orders accepts them. Keep priority
   (regular/express) and promise_minutes.
3. Add GET /catalog/availability?skus=a,b that returns, per store: has_all_items, per-item
   available qty, distance_km and road-ETA from the customer point. Highlight data for the UI.
4. Enforce rider shift_end in allocation. Add battery drain per km and a low-battery exclusion.
5. StoresPanel must show stock levels with low-stock warnings, packing queue and capacity bars.
   Add a restock button (POST /dark_stores/{id}/restock).

PHASE 2: Allocation engine (Requirement 3)
1. Store selection: first filter stores that have ALL items, then choose the NEAREST by road-ETA to
   the customer (tie-break by packing queue). Return the ranked store list with reasons. If none
   can fulfil everything, return a split-fulfilment or substitution suggestion.
2. Rider selection: score eligible riders using pickup ETA (road-based), current load, deadline
   slack, express weight, and batching bonus. Compute packing_wait from the store's real queue
   (queued orders * packing seconds / capacity). Respect capacity_kg and shift_end.
3. Real batching: allow a rider to carry multiple orders from the same store if the added detour
   per extra order is below a threshold (default 90 s) and no order's promised time is breached.
   Use cheapest insertion that includes pickup and drops.
4. Rolling reoptimisation every 5 to 10 s: re-solve assignment for orders that are not yet picked up
   (OR-Tools VRP with time windows, capacity, pickup-before-drop). Add a stability penalty and only
   reassign when the gain exceeds a threshold (default 60 s saved or a missed-deadline avoided). Log
   every reassignment as an OrderEvent with the reason.
5. Extend /orders/{id}/explain: nearest-store ranking, rider ranking with cost components (for
   horizontal bars in the UI), and chosen vs runner-up delta.

PHASE 3: Road routing and real-time adaptation (Requirement 4)
1. Add backend/app/routing.py: get_route(a, b) returns {polyline, distance_m, duration_s} using
   Mapbox Directions (token from env) or OSRM, with an LRU cache and a haversine fallback if the API
   fails. The matrix for the optimiser can use cached durations or a coarse grid approximation; keep
   solve time under 2 s.
2. Riders move along the road polyline at speed * traffic factor, per segment, not in a straight
   line. Persist progress as route_progress (distance along polyline) so position is deterministic
   and smooth.
3. Traffic simulation: POST /disruptions/traffic accepts lat, lng, radius_km, multiplier, duration
   (the UI will let the user click on the map or on a rider's path). Segments inside the zone are
   slowed, not the whole leg. Keep the old random option too.
4. Rider path re-evaluation: when a traffic zone appears, expires, or a rider deviates, recompute
   the remaining path for affected riders (alternative route that avoids the zone, e.g. Directions
   with waypoints around it or the alternatives=true option). Cache the current plan. Switch to the
   new route ONLY if it saves at least X seconds (default 45 s or 10 percent). Emit a ROUTE_CHANGED
   event with old ETA, new ETA, and reason. If the gain is small, keep the old path and record
   "kept current route".
5. Other triggers: rider_offline (pre-pickup orders returned to pool with raised priority),
   cancellation (release stock and rider load), stock-out (reallocate to another store), new order
   insertion. All must be demonstrable from the UI.
6. Wire the `failed` state: if an order exceeds promise by a configurable margin with no rider, or a
   drop fails, mark failed with failed_reason and release resources.

PHASE 4: Tracking, prioritisation, analytics (Requirement 5 and 6)
1. WebSocket tick payload must include for each order: status, risk, eta_seconds,
   predicted_late (boolean), rider_id, store_id, customer_name, and current route polyline version.
   For each rider: current polyline remaining, assigned order ids, heading.
2. Ops view: priority queue panel (score = urgency + express + delay age), at-risk list, per-order
   intervention buttons (reassign, boost priority, cancel).
3. Customer tracker (#track/{id}): see PHASE 5.
4. Analytics (new endpoints plus charts): average delivery time, on-time %, true rider utilisation
   (busy time / shift time), orders per zone (use named zones or H3 hexes with a heatmap layer),
   delayed/failed count, delay-reason breakdown (stock-out, rider shortage, traffic, packing wait),
   on-time % time series with disruption markers, rider workload fairness (Gini of orders per
   rider).
5. Baseline comparison: add a "naive nearest-rider" dispatch mode toggle, run the same seeded order
   stream through both, and show on-time % and average time side by side.

PHASE 5: The guided simulation flow (the demo)
Build this as one continuous experience, using live backend data (not hard-coded routes). Remove or
rebuild the current hard-coded Simulation tab so it is driven by the backend.

Screen A, Customer storefront (route #shop):
- Product grid with categories, price, add-to-cart, cart drawer.
- Customer name field and delivery location (click a pin on a small Mapbox map or choose a preset
  Mumbai address). Choose Regular or Express.
- "Place order" calls POST /orders, then navigates to the dashboard with the order focused (also
  give the customer a #track/{id} link).

Screen B, Dashboard (ops map, focused on the new order), in this exact sequence with short
animated steps:
1. STOCK CHECK: show all dark stores on the map. Stores that stock ALL cart items glow green and
   show a badge "has X, Y, Z"; stores missing items are dimmed with "missing: ...". A side card
   lists stores with availability and distance.
2. NEAREST STORE: draw an arc from the customer to the chosen (nearest eligible) store and
   highlight it; show the distance and ETA in the card.
3. RIDER ALLOCATION: show all riders as markers. Pulse the shortlisted ones, then highlight the
   chosen rider with a ring and animated arc from store to rider. Every assigned rider marker
   carries a floating label with "Order #ID - Customer name" above it. Unassigned riders stay small
   and neutral. The explain panel shows why (cost bars, runner-up).
4. JOURNEY: the chosen rider drives rider -> store (pickup) -> customer along the road polyline,
   drawn as a bright line with a faded completed portion and a moving rider marker (rotate to
   heading). Follow-camera toggle. Live ETA, distance remaining, and status chips (packing, picked
   up, out for delivery, delivered).
5. TRAFFIC CONTROL: a "Simulate traffic" tool lets the user click a spot on the map (or click
   directly on the rider's route) to drop a congestion zone (radius and severity sliders,
   duration). The zone renders on the map in red.
6. LIVE REROUTE: the system recomputes the remaining route in the background, shows a candidate
   alternative as a dashed line with "saves 2m 10s", and switches only if the gain exceeds the
   threshold; otherwise shows "Keeping current route (gain 12s)". On switch, flash the old route
   red and draw the new one green, update the ETA, and push a toast. A route-history list shows
   each decision with time saved.
7. Delivery completes, KPI cards update.

Screen C, Customer tracking page (#track/{id}), mirrors the same events in real time via WebSocket:
- Full-width map showing: customer pin, the allocated nearest store (with name), the assigned rider
  (name, vehicle, label), the live rider path, and the rider moving.
- A timeline: Order placed -> Store allocated (name, items confirmed) -> Rider allocated (name) ->
  Packed -> Picked up -> On the way -> Delivered, each with timestamps.
- Live ETA countdown, and a banner when traffic causes a delay or the rider is re-routed ("Your
  rider is taking a faster route, new ETA 11 min").
- Never expose internal scores to the customer.

PHASE 6: Optional extras (only if everything above is solid)
- Chaos console buttons: rain, IPL surge, 3 riders offline, store stock-out, bridge closed.
- Demand forecast (next 15 min per zone) and idle-rider pre-positioning.
- Dynamic promise time at checkout based on current load.
- Time-travel replay of the simulated day from logged events.

TECHNICAL RULES
- Rider and store markers: if Mapbox `model` sources crash (known issue in the comments), use DOM
  markers with labels or deck.gl ScenegraphLayer; never ship an error-per-frame.
- Use requestAnimationFrame interpolation between 1 s server ticks so riders glide instead of
  jumping.
- All new endpoints get pytest tests (use the existing in-memory SQLite fixtures). Keep the 25
  existing tests green.
- Keep seed 42 determinism for the order generator; the interactive customer orders must not break
  it.
- Colour language: green on track, amber at risk, red delayed. Keep Tailwind tokens already in
  tailwind.config.js.
- Handle failures: if Directions API fails, fall back to straight segments and show a small
  "approximate route" badge.
- At the end, update README with run steps (backend and frontend), env vars, and a 3-minute demo
  script that follows PHASE 5.

DEFINITION OF DONE
1. I can open #shop, add items, place an order, and land on the dashboard.
2. The dashboard visibly shows stock-based store highlighting, nearest store selection, rider
   shortlist and the highlighted chosen rider with an order/customer label.
3. The rider follows a real road path; I can drop a traffic zone on the path; the system re-routes
   only when the gain is meaningful and shows why.
4. The customer page shows the same story live on a map.
5. Analytics show all five required KPIs plus the baseline-vs-optimised comparison.
6. `pytest` and `npm run build` pass; no secrets in the repo.

</details>
