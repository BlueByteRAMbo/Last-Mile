---
name: simulator
description: Build the deterministic live quick-commerce simulator and disruption scenarios.
---

# Simulator

Model dark stores, riders, customers and orders. Use a configurable tick to move riders, advance packing, generate orders, update statuses, emit WebSocket diffs and update metrics.

Support a deterministic seed so the same scenario produces the same workload.

Implement real backend scenario events:
- rain / traffic slowdown
- traffic jam or blocked zone
- demand surge
- riders offline
- SKU/store stockout
- cancellation

Maintain timestamped domain events such as ORDER_CREATED, STOCK_RESERVED, ASSIGNED, PACKING_STARTED, PACKED, PICKED_UP, ROUTE_CHANGED, RIDER_OFFLINE, DELAY_RISK, DELIVERED and FAILED.

Provide reset and reproducible demo presets. Never depend on random luck during judging.
