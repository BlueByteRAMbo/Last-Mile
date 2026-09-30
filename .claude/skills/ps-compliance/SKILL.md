---
name: ps-compliance
description: Audit the project against all six mandatory Last Mile problem-statement requirements.
---

# PS Compliance

Official PS coverage is the highest priority.

Inspect actual implementation, not filenames or mock screens. Classify every requirement as PASS, PARTIAL, or MISSING and cite concrete files/functions/endpoints/components.

Check:
1. Order & Demand Mapping: location, items, timestamp, promised window, priority, stock-aware store feasibility and stock reservation.
2. Resource Management: live rider location/capacity/load/status/shift and store inventory/location/packing capacity/queue.
3. Dynamic Allocation: store+rider evaluation, proximity, load, deadline/slack, batching, feasibility, fast assignment and rolling re-optimization.
4. Route Optimization: sequencing plus new order, cancellation, rider dropout and traffic adaptation.
5. Tracking & Prioritization: lifecycle, customer/ops visibility, delayed/at-risk handling and express prioritization.
6. Analytics: average delivery time, on-time rate, rider utilization, zone density, delayed and failed counts from actual data.

Output:
Requirement | Status | Evidence | Missing | Next action

Do not recommend optional features until all six requirements are PASS.
