"""Isolated seeded replay using the actual tick engine, with an accelerated clock.

Run in a child process: it must never replace the live server's world or clock.
Road calls are intentionally disabled so both modes see identical route estimates.
"""
import datetime as dt
import hashlib
import json
import random
from types import SimpleNamespace


def run_comparison(seed=42, count=36):
    from . import simulator, dispatch, analytics, tracking, seed_data, routing
    from .world import world, World
    from .models import Order
    from .catalog import CATALOG
    start = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)

    class Clock(dt.datetime):
        current = start

        @classmethod
        def now(cls, tz=None):
            return cls.current if tz else cls.current.replace(tzinfo=None)

    clock_module = SimpleNamespace(datetime=Clock, timedelta=dt.timedelta, timezone=dt.timezone)
    originals = {m: m.dt for m in (simulator, dispatch, analytics, tracking, seed_data)}
    rng = random.Random(seed)
    demand = []
    for i in range(count):
        store = rng.choice(seed_data.STORES)
        product = rng.choice(CATALOG)
        demand.append({'id': f'BENCH-{i:03}', 'arrival': i * 15,
                       'lat': store[2] + rng.uniform(-.018, .018),
                       'lng': store[3] + rng.uniform(-.018, .018),
                       'sku': product['sku'], 'weight': product['weight_kg'],
                       'promise': rng.choice([8, 12, 20]), 'priority': rng.random() < .2})
    results = {}
    try:
        for module in originals:
            module.dt = clock_module
        for mode in ('nearest', 'optimized'):
            Clock.current = start
            world.__dict__.update(World().__dict__)
            stores, inventory, riders = seed_data.build_seed_entities()
            world.stores, world.riders = stores, riders
            world.store_by_id = {s.id: s for s in stores}
            world.rider_by_id = {r.id: r for r in riders}
            world.inventory = {(v.store_id, v.sku): v for v in inventory}
            routing.clear_cache()
            dispatch.clear_traffic_zones()
            simulator.state.update(order_spawn_rate=0, dispatch_mode=mode)
            simulator._tick_count = 0
            simulator.reset_rng()
            next_order = 0
            horizon = demand[-1]['arrival'] + 3600
            for seconds in range(0, horizon + 1, 2):
                Clock.current = start + dt.timedelta(seconds=seconds)
                while next_order < count and demand[next_order]['arrival'] <= seconds:
                    spec = demand[next_order]
                    created = start + dt.timedelta(seconds=spec['arrival'])
                    world.add_new_order(Order(id=spec['id'], customer_lat=spec['lat'], customer_lng=spec['lng'],
                        items=[{'sku': spec['sku'], 'qty': 1, 'weight_kg': spec['weight']}],
                        weight_kg=spec['weight'], priority=spec['priority'], customer_name='Replay',
                        created_at=created, promised_at=created + dt.timedelta(minutes=spec['promise']),
                        status='created', risk='LOW'))
                    next_order += 1
                simulator.tick_sync()
                simulator._pending_route_fetches.clear()
                if next_order == count and not world.active_orders():
                    break
            metrics = analytics.build_analytics(Clock.current)
            results[mode] = {key: metrics[key] for key in ('on_time_rate_pct', 'avg_delivery_minutes',
                'delivered_count', 'failure_count', 'active_orders', 'workload_gini')}
            results[mode]['on_time_of_all_orders_pct'] = round(
                sum(o.status == 'delivered' and o.delivered_at <= o.promised_at for o in world.orders.values()) * 100 / count, 1)
        return {'seed': seed, 'order_count': count,
                'stream_hash': hashlib.sha256(json.dumps(demand, sort_keys=True).encode()).hexdigest()[:16],
                'basis': 'Same seeded orders, inventory and riders; actual tick engine; deterministic straight-line routes; no external disruptions',
                'results': results}
    finally:
        for module, original in originals.items():
            module.dt = original


if __name__ == '__main__':
    print(json.dumps(run_comparison()))
