---
name: demo-audit
description: Audit and prepare a reliable Minithon demo with visible adaptive behavior and complete PS coverage.
---

# Demo Audit

Use one clear story:
normal operations → disruption → automatic adaptation → measurable result.

Suggested sequence:
1. Show live orders/riders/stores.
2. Trigger rain/traffic plus rider dropout.
3. Show affected ETAs and at-risk orders.
4. Show reassignment/re-routing.
5. Open “Why this rider?”.
6. Show KPI changes.

Verify all six PS requirements are visible, simulator resets, scenario is reproducible, routing has fallback, optimizer has timeout/fallback heuristic, WebSocket reconnect works, analytics use real events and no essential feature needs manual DB edits.

If baseline comparison exists, run the same seeded workload through nearest-feasible-rider and optimized dispatch and compare factual metrics.

Produce a 3–5 minute click-by-click demo plan, expected result after each action, fallback plan and final PS checklist.
