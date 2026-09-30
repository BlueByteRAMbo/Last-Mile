---
name: frontend-design
description: Design and implement the Last Mile Mission Control, customer tracker, rider view and analytics UI.
---

# Frontend Design

Build a premium real-time logistics command center, not a generic admin dashboard.

## Non-negotiable
UI beauty must never hide or replace a mandatory PS feature. Every major backend capability must have a visible, demonstrable state.

## Mission Control
- Center: live MapLibre/deck.gl map.
- Left: incoming orders and priority queue.
- Right: selected entity and “Why this rider?” inspector.
- Bottom: KPI strip/timeline.
- Top: scenario controls.

## Map
Show dark stores, packing pressure, moving riders, routes, order locations, demand heatmap, assignment arcs and delayed/at-risk indicators. Add layer toggles to prevent clutter.

## Explainable dispatch
For a selected order show chosen store/rider, ranked alternatives, ETA components, load, packing wait, deadline slack/risk, batching benefit and concise selection reason.

## Customer tracker
Show live ETA, moving rider and lifecycle:
placed → accepted/packing → packed → out for delivery → delivered.
Clearly show at-risk/delayed states.

## Analytics
Expose average delivery time, on-time %, rider utilization, order density by zone and delayed/failed deliveries.

## Visual direction
Dark operations-center aesthetic; dense but readable; map-first; strong hierarchy; restrained motion; consistent semantic states. Avoid generic card grids, excessive gradients, decorative glassmorphism and meaningless animations.

Use reusable React + TypeScript components, accessible focus/keyboard states, responsive layouts, and real backend/simulator state. Optimize map updates so every simulation tick does not rerender the whole app.

Before declaring a screen done ask:
1. Which PS requirement does it expose?
2. Is the data real?
3. Can a judge understand what changed and why?
4. Does it work during disruption scenarios?
