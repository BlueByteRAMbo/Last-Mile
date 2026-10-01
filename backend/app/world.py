"""In-memory world state: the single source of truth during simulation ticks.

Loaded from Postgres once at startup, mutated purely in memory every tick (zero DB round trips —
this is what gets tick time from seconds down to low milliseconds), and flushed back to the DB
periodically in the background by persist_loop() so a tick is never blocked on a Neon round trip.
API endpoints read from this same state so they're consistent with what the simulator just did,
not whatever Postgres had a few hundred ms ago.
"""
import asyncio
import datetime as dt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .db import SessionLocal
from .models import DarkStore, Rider, Order, OrderEvent, InventoryItem

# Held by persist_once() for its whole DB write, and by /reset, so a periodic background flush
# can never run concurrently with a reset's DELETE — two transactions touching the same rows at
# once is exactly how a Postgres deadlock happens (hit this directly: persist_once's bulk UPDATE
# on `orders` racing /reset's `DELETE FROM orders`).
db_write_lock = asyncio.Lock()

NON_TERMINAL_STATUSES = ["created", "assigned", "packing", "packed", "out_for_delivery"]
ACTIVE_STATUSES = ["assigned", "packing", "packed", "out_for_delivery"]

ORDER_MUTABLE_COLUMNS = ["status", "risk", "priority", "store_id", "rider_id", "route_seq",
                          "assigned_at", "packed_at", "picked_up_at", "delivered_at",
                          "assignment_reason", "failed_reason"]
RIDER_MUTABLE_COLUMNS = ["lat", "lng", "status", "current_load_kg", "battery_pct",
                          "busy_seconds", "observed_shift_seconds",
                          "nav_origin_lat", "nav_origin_lng", "nav_target_lat", "nav_target_lng", "route_progress_km"]
INVENTORY_MUTABLE_COLUMNS = ["qty", "reserved_qty"]


class World:
    def __init__(self):
        self.stores: list[DarkStore] = []
        self.store_by_id: dict[str, DarkStore] = {}
        self.riders: list[Rider] = []
        self.rider_by_id: dict[str, Rider] = {}
        self.orders: dict[str, Order] = {}
        self.inventory: dict[tuple, InventoryItem] = {}
        self.catalog: list[tuple] = []  # (sku, name, weight_kg) — set by simulator at import time

        self.pending_events: list[OrderEvent] = []
        self.events: list[OrderEvent] = []
        self.pending_new_orders: list[Order] = []
        self.dirty_order_ids: set[str] = set()
        self.dirty_rider_ids: set[str] = set()
        self.dirty_inventory_keys: set[tuple] = set()
        self.loaded = False

    # -- mutation helpers used by the tick loop and by disruption/order endpoints --
    def log_event(self, order_id: str, type_: str, payload: dict | None = None):
        event = OrderEvent(order_id=order_id, type=type_, payload=payload or {}, ts=dt.datetime.now(dt.timezone.utc))
        self.pending_events.append(event)
        self.events.append(event)

    def mark_order_dirty(self, order_id: str):
        self.dirty_order_ids.add(order_id)

    def mark_rider_dirty(self, rider_id: str):
        self.dirty_rider_ids.add(rider_id)

    def mark_inventory_dirty(self, key: tuple):
        self.dirty_inventory_keys.add(key)

    def add_new_order(self, order: Order):
        self.orders[order.id] = order
        self.pending_new_orders.append(order)

    def active_orders(self) -> list[Order]:
        return [o for o in self.orders.values() if o.status in NON_TERMINAL_STATUSES]

    def reserve_stock(self, store_id: str, items: list):
        for it in items:
            key = (store_id, it["sku"])
            row = self.inventory.get(key)
            if row:
                row.reserved_qty += it["qty"]
                self.mark_inventory_dirty(key)

    def release_stock(self, store_id: str, items: list):
        for it in items:
            key = (store_id, it["sku"])
            row = self.inventory.get(key)
            if row:
                row.reserved_qty = max(0, row.reserved_qty - it["qty"])
                self.mark_inventory_dirty(key)

    def reassign_rider_orders(self, rider_id: str) -> list[str]:
        """Rider just went offline: free their pre-pickup orders so the next tick reallocates them."""
        rider = self.rider_by_id.get(rider_id)
        freed = []
        for o in self.orders.values():
            if o.rider_id != rider_id or o.status not in ("assigned", "packing", "packed"):
                continue
            if o.store_id:
                self.release_stock(o.store_id, o.items)
            if rider:
                rider.current_load_kg = max(0.0, rider.current_load_kg - o.weight_kg)
            o.status = "created"
            o.store_id = None
            o.rider_id = None
            o.route_seq = None
            o.assigned_at = None
            o.packed_at = None
            self.mark_order_dirty(o.id)
            freed.append(o.id)
        if rider:
            self.mark_rider_dirty(rider_id)
        return freed

    def cancel_order(self, order: Order) -> bool:
        if order.status in ("delivered", "failed", "cancelled"):
            return False
        if order.store_id:
            self.release_stock(order.store_id, order.items)
        if order.rider_id:
            rider = self.rider_by_id.get(order.rider_id)
            if rider:
                rider.current_load_kg = max(0.0, rider.current_load_kg - order.weight_kg)
                self.mark_rider_dirty(rider.id)
        order.status = "cancelled"
        self.mark_order_dirty(order.id)
        return True

    def fail_order(self, order: Order, reason: str):
        if order.store_id:
            self.release_stock(order.store_id, order.items)
        if order.rider_id:
            rider = self.rider_by_id.get(order.rider_id)
            if rider:
                rider.current_load_kg = max(0.0, rider.current_load_kg - order.weight_kg)
                self.mark_rider_dirty(rider.id)
        order.status = "failed"
        order.failed_reason = reason
        self.mark_order_dirty(order.id)


world = World()


async def load_world():
    async with SessionLocal() as session:
        stores = (await session.execute(select(DarkStore))).scalars().all()
        riders = (await session.execute(select(Rider))).scalars().all()
        orders = (await session.execute(select(Order))).scalars().all()
        inventory = (await session.execute(select(InventoryItem))).scalars().all()
        events = (await session.execute(select(OrderEvent).order_by(OrderEvent.ts))).scalars().all()
        session.expunge_all()

    world.stores = list(stores)
    world.store_by_id = {s.id: s for s in world.stores}
    world.riders = list(riders)
    world.rider_by_id = {r.id: r for r in world.riders}
    world.orders = {o.id: o for o in orders}
    world.inventory = {(i.store_id, i.sku): i for i in inventory}
    world.pending_events = []
    world.events = list(events)
    world.pending_new_orders = []
    world.dirty_order_ids = set()
    world.dirty_rider_ids = set()
    world.dirty_inventory_keys = set()
    world.loaded = True


async def persist_once(session: AsyncSession | None = None):
    """One batched flush of whatever's currently dirty. Safe to call on its own short-lived session
    (default) or an injected one (tests). Never called from inside the tick's hot path.

    The WHOLE function — snapshotting dirty state AND writing it — runs under db_write_lock, not
    just the write. Snapshotting outside the lock let a persist that started just before /reset
    capture order/event references that /reset then deleted before the (lock-blocked) write
    finally ran, producing an order_events FK violation on order IDs that no longer existed.
    """
    async with db_write_lock:
        if not (world.dirty_order_ids or world.dirty_rider_ids or world.dirty_inventory_keys
                or world.pending_events or world.pending_new_orders):
            return

        order_ids, world.dirty_order_ids = world.dirty_order_ids, set()
        rider_ids, world.dirty_rider_ids = world.dirty_rider_ids, set()
        inv_keys, world.dirty_inventory_keys = world.dirty_inventory_keys, set()
        events, world.pending_events = world.pending_events, []
        new_orders, world.pending_new_orders = world.pending_new_orders, []

        order_rows = [
            {"id": oid, **{c: getattr(world.orders[oid], c) for c in ORDER_MUTABLE_COLUMNS}}
            for oid in order_ids if oid in world.orders
        ]
        rider_rows = [
            {"id": rid, **{c: getattr(world.rider_by_id[rid], c) for c in RIDER_MUTABLE_COLUMNS}}
            for rid in rider_ids if rid in world.rider_by_id
        ]
        inv_rows = [
            {"id": world.inventory[key].id, **{c: getattr(world.inventory[key], c) for c in INVENTORY_MUTABLE_COLUMNS}}
            for key in inv_keys if key in world.inventory
        ]
        # events/new_orders may reference ids that existed in world at dirty-mark time but have
        # since been reset away; only keep ones still present now (we're still holding the lock,
        # so "now" can't race a concurrent reset).
        new_order_ids = {o.id for o in new_orders}
        valid_order_ids = set(world.orders.keys())
        events = [e for e in events if e.order_id in valid_order_ids or e.order_id in new_order_ids]
        new_orders = [o for o in new_orders if o.id in valid_order_ids]

        from sqlalchemy import update as sa_update

        async def _run(s):
            for o in new_orders:
                s.add(Order(**{col.name: getattr(o, col.name) for col in Order.__table__.columns}))
            for e in events:
                s.add(OrderEvent(order_id=e.order_id, type=e.type, payload=e.payload, ts=e.ts))
            if order_rows:
                await s.execute(sa_update(Order), order_rows)
            if rider_rows:
                await s.execute(sa_update(Rider), rider_rows)
            if inv_rows:
                await s.execute(sa_update(InventoryItem), inv_rows)
            await s.commit()

        if session is not None:
            await _run(session)
        else:
            async with SessionLocal() as s:
                await _run(s)
