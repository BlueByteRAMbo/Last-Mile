import asyncio
from fastapi import WebSocket

SEND_TIMEOUT_SECONDS = 2.0


async def _send(ws: WebSocket, message: dict) -> bool:
    """True if delivered. A client that errors or can't take the frame within the timeout is dropped."""
    try:
        await asyncio.wait_for(ws.send_json(message), SEND_TIMEOUT_SECONDS)
        return True
    except Exception:
        return False


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []
        self.tracking: dict[WebSocket, str] = {}

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.tracking.pop(ws, None)
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict):
        # Concurrent + time-boxed: sending one-by-one let a single stalled client freeze every tick.
        clients = list(self.active)
        results = await asyncio.gather(*(_send(ws, message) for ws in clients))
        for ws, ok in zip(clients, results):
            if not ok:
                self.disconnect(ws)

    async def broadcast_tracking(self):
        from .world import world
        from .tracking import customer_snapshot
        snapshots = {}
        targets = list(self.tracking.items())
        for _, order_id in targets:
            if order_id not in snapshots:
                order = world.orders.get(order_id)
                snapshots[order_id] = customer_snapshot(order) if order else {'type': 'not_found'}
        results = await asyncio.gather(*(_send(ws, snapshots[order_id]) for ws, order_id in targets))
        for (ws, _), ok in zip(targets, results):
            if not ok:
                self.disconnect(ws)


manager = ConnectionManager()
