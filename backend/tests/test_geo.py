from app.geo import is_on_land
from app.seed_data import STORES


def test_stores_on_land():
    assert all(is_on_land(lat, lng) for _, _, lat, lng in STORES)


def test_sea_and_creek_rejected():
    assert not is_on_land(19.05, 72.79)   # Arabian Sea off Bandra
    assert not is_on_land(18.99, 72.80)   # sea off Worli
    assert not is_on_land(19.00, 72.90)   # harbour east of Sewri
