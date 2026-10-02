import asyncio
import datetime as dt
import time
import pytest

from app import ws as ws_module
from app.analytics import build_analytics
from app.simulator import advance_packing
from app.tracking import customer_snapshot
from app.world import world
from .conftest import make_store, make_order, utcnow
from .test_api import client  # noqa: F401  (fixture)
from .test_high_fixes import isolated_world  # noqa: F401  (fixture)

pytestmark = pytest.mark.asyncio


async def test_basket_heavier_than_any_rider_can_carry_is_rejected(client):  # noqa: F811
    cat = {p["sku"]: p for p in (await client.get("/catalog")).json()}
    heavy = max(cat.values(), key=lambda p: p["weight_kg"])
    body = {"customer_lat": 19.1, "customer_lng": 72.85, "items": [{"sku": heavy["sku"], "name": "x", "qty": 20}]}
    r = await client.post("/orders", json=body)
    assert r.status_code == 422 and "kg" in r.json()["detail"]
    body["items"][0]["qty"] = 1
    assert (await client.post("/orders", json=body)).status_code == 200


async def test_disruption_parameters_are_validated(client):  # noqa: F811
    assert (await client.post("/disruptions/traffic?multiplier=0")).status_code == 422   # would freeze riders
    assert (await client.post("/disruptions/traffic?multiplier=3")).status_code == 422   # would speed them up
    assert (await client.post("/disruptions/traffic?radius_km=-1")).status_code == 422
    assert (await client.post("/disruptions/traffic?lat=19.05")).status_code == 422      # lat without lng
    assert (await client.post("/disruptions/traffic?lat=19.05&lng=72.85&multiplier=0.4")).status_code == 200


async def test_order_waiting_for_a_packing_slot_does_not_pack_instantly(isolated_world):  # noqa: F811
    store = make_store(packing_capacity=1, packing_seconds=60)
    world.stores, world.store_by_id = [store], {store.id: store}
    order = make_order()
    order.store_id, order.status = store.id, "assigned"
    order.assigned_at = utcnow() - dt.timedelta(minutes=10)  # queued a long time before getting a slot
    advance_packing([order])
    assert order.status == "packing"
    advance_packing([order])
    assert order.status == "packing"  # 60s of packing has not elapsed since it took the slot


async def test_customer_timeline_follows_current_state_not_history(isolated_world):  # noqa: F811
    order = make_order()
    world.orders = {order.id: order}
    world.log_event(order.id, "ORDER_CREATED")
    world.log_event(order.id, "ASSIGNED")
    world.log_event(order.id, "PACKING_STARTED")
    order.status = "created"  # bounced back to the pool by a stock-out
    done = {s["key"]: s["done"] for s in customer_snapshot(order)["stages"]}
    assert done["created"] and not done["store"] and not done["rider"] and not done["packing"]


async def test_kpis_report_no_data_instead_of_made_up_numbers(isolated_world):  # noqa: F811
    result = build_analytics()
    assert result["on_time_rate_pct"] is None and result["avg_delivery_minutes"] is None
    assert result["sla_breach_rate_pct"] is None


async def test_operator_cancellations_are_not_sla_breaches(isolated_world):  # noqa: F811
    now = utcnow()
    done, cancelled = make_order(id="ORD-OK"), make_order(id="ORD-CX")
    done.status, done.created_at, done.delivered_at, done.promised_at = "delivered", now - dt.timedelta(minutes=10), now, now + dt.timedelta(minutes=5)
    cancelled.status = "cancelled"
    world.orders = {done.id: done, cancelled.id: cancelled}
    result = build_analytics(now)
    assert result["sla_breach_rate_pct"] == 0.0 and result["on_time_rate_pct"] == 100.0


async def test_one_stalled_websocket_does_not_block_the_broadcast(monkeypatch):
    monkeypatch.setattr(ws_module, "SEND_TIMEOUT_SECONDS", 0.2)

    class Fast:
        got = None

        async def send_json(self, m):
            self.got = m

    class Stalled:
        async def send_json(self, m):
            await asyncio.sleep(30)

    manager = ws_module.ConnectionManager()
    fast, stalled = Fast(), Stalled()
    manager.active = [stalled, fast]
    started = time.perf_counter()
    await manager.broadcast({"type": "tick"})
    assert time.perf_counter() - started < 2
    assert fast.got == {"type": "tick"} and manager.active == [fast]
