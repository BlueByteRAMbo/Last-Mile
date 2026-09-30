---
name: dispatch-engine
description: Implement and review real-time dark-store and rider allocation.
---

# Dispatch Engine

## Goal
Select a feasible dark store and rider for each order while minimizing delivery risk/cost and considering batching.

## Feasibility first
Reject candidates violating stock, rider capacity, rider availability/shift, delivery time window, or route/pickup constraints.

## Fast scoring
Use a configurable transparent model:

cost =
  w_eta * total_eta
+ w_pack * packing_wait
+ w_load * workload_penalty
+ w_deadline * deadline_risk
- w_batch * batching_benefit
+ w_stability * reassignment_penalty

Return the selected assignment plus candidate scores and reasons.

## Rolling optimization
Periodically optimize not-yet-picked-up orders with OR-Tools using time windows and capacity. Avoid thrashing with a stability penalty.

## Batching
Batch only when rider capacity allows, pickup is compatible, detour is below threshold, and every promised window remains feasible. Use cheapest insertion for fast decisions.

## Tests
Cover out-of-stock stores, overloaded/offline riders, express deadlines, useful/harmful batches, dropout recovery and assignment stability.
