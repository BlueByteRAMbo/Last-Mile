from app.dispatch import allocate_sync
from .conftest import make_order, make_rider, make_store, make_inventory


def test_optimized_chooses_nearest_stock_eligible_store_before_rider_cost():
    near = make_store(id='NEAR', lat=19.1, lng=72.85)
    far = make_store(id='FAR', lat=19.12, lng=72.85)
    order = make_order(lat=19.1001, lng=72.85)
    rider = make_rider(lat=far.lat, lng=far.lng)
    inventory = {(s.id, 'SKU-A'): make_inventory(store_id=s.id) for s in [near, far]}
    chosen = allocate_sync(order, [far, near], [rider], {}, inventory)['chosen']
    assert chosen['store_id'] == 'NEAR'
    inventory[('NEAR', 'SKU-A')].qty = 0
    assert allocate_sync(order, [far, near], [rider], {}, inventory)['chosen']['store_id'] == 'FAR'
