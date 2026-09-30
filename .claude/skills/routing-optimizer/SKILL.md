---
name: routing-optimizer
description: Implement route sequencing, batching insertion, travel-time handling and rolling OR-Tools optimization.
---

# Routing Optimizer

For a new order, try feasible insertion positions in compatible rider routes. Calculate incremental travel time and deadline impact. Accept only if capacity and all time windows remain feasible.

Periodically run an OR-Tools rolling-horizon VRP with time windows, capacity, travel-time matrix, lateness penalties and stability penalties. Use a strict solve-time limit.

Re-route on new order/batch insertion, cancellation, rider offline, meaningful traffic changes or predicted deadline miss.

Abstract travel times behind a routing interface so OSRM can be used when available with a precomputed/grid fallback for demos.

Return ordered stops with stop type, order ID, ETA, cumulative load, deadline/slack and route version.
