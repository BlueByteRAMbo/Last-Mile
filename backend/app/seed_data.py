import datetime as dt
from .models import DarkStore, InventoryItem, Rider
from .simulator import SKU_CATALOG

STORES = [
    ("DS-1", "Andheri Hub", 19.1136, 72.8697),
    ("DS-2", "Bandra Hub", 19.0596, 72.8295),
    ("DS-3", "Powai Hub", 19.1176, 72.9060),
    ("DS-4", "Lower Parel Hub", 18.9953, 72.8300),
    ("DS-5", "Dadar Hub", 19.0178, 72.8478),
]


def build_seed_entities():
    now = dt.datetime.now(dt.timezone.utc)
    stores = [DarkStore(id=i, name=n, lat=lat, lng=lng, packing_capacity=6, packing_seconds_per_order=75)
              for i, n, lat, lng in STORES]
    inventory = []
    for s in stores:
        for sku, name, _w in SKU_CATALOG:
            inventory.append(InventoryItem(store_id=s.id, sku=sku, name=name, qty=200, reserved_qty=0))
    riders = []
    for i in range(1, 16):
        store = stores[(i - 1) % len(stores)]
        riders.append(Rider(
            id=f"RX-{100 + i}", name=f"Rider {100 + i}",
            lat=store.lat + (i % 3 - 1) * 0.01, lng=store.lng + (i % 3 - 1) * 0.01,
            home_store_id=store.id, capacity_kg=15.0, current_load_kg=0.0,
            speed_kmh=26.0 + (i % 5), battery_pct=100, status="AVAILABLE",
            shift_end=now + dt.timedelta(hours=8),
        ))
    return stores, inventory, riders
