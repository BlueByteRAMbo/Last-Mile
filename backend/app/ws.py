from fastapi import WebSocket


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
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_tracking(self):
        from .world import world
        from .tracking import customer_snapshot
        snapshots = {}
        for ws, order_id in list(self.tracking.items()):
            try:
                if order_id not in snapshots:
                    order = world.orders.get(order_id)
                    snapshots[order_id] = customer_snapshot(order) if order else {'type': 'not_found'}
                await ws.send_json(snapshots[order_id])
            except Exception:
                self.disconnect(ws)


manager = ConnectionManager()
