import datetime as dt
import random
from .models import DarkStore, InventoryItem, Rider
from .catalog import CATALOG

STORES = [
    ("DS-1", "Andheri Hub", 19.1136, 72.8697),
    ("DS-2", "Bandra Hub", 19.0596, 72.8295),
    ("DS-3", "Powai Hub", 19.1176, 72.9060),
    ("DS-4", "Lower Parel Hub", 18.9953, 72.8300),
    ("DS-5", "Dadar Hub", 19.0178, 72.8478),
]

# Deterministic (seed 42) but genuinely uneven stock per store: every store carries most of the
# catalog comfortably, but each one also has a couple of SKUs at zero or near-zero — so which
# store can actually fulfil a given cart is a real decision, not a formality.
_inv_rng = random.Random(42)
STOCK_LEVELS = [0, 0, 3, 8, 40, 80, 150, 200]  # weighted toward well-stocked, with real gaps


def build_seed_entities():
    now = dt.datetime.now(dt.timezone.utc)
    stores = [DarkStore(id=i, name=n, lat=lat, lng=lng, packing_capacity=6, packing_seconds_per_order=75)
              for i, n, lat, lng in STORES]
    inventory = []
    for s in stores:
        for product in CATALOG:
            qty = _inv_rng.choice(STOCK_LEVELS)
            inventory.append(InventoryItem(store_id=s.id, sku=product["sku"], name=product["name"], qty=qty, reserved_qty=0))
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
