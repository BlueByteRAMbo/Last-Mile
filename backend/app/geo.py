"""Coarse land mask for the Mumbai service area, so generated/accepted points never land in the
Arabian Sea, Mahim Bay or Thane Creek. ponytail: hand-traced polygon with ~300m inland margin;
swap for a real coastline geometry (or Mapbox Tilequery) if the service area grows."""

# (lng, lat), clockwise from the north-west corner
_LAND = [
    (72.832, 19.16), (72.828, 19.12), (72.826, 19.08), (72.826, 19.05), (72.832, 19.035),
    (72.822, 19.00), (72.817, 18.98), (72.808, 18.955), (72.815, 18.93), (72.838, 18.94),
    (72.846, 18.96), (72.852, 19.00), (72.862, 19.02), (72.90, 19.04), (72.935, 19.06),
    (72.955, 19.10), (72.965, 19.16),
]


def is_on_land(lat: float, lng: float) -> bool:
    inside = False
    j = len(_LAND) - 1
    for i, (xi, yi) in enumerate(_LAND):
        xj, yj = _LAND[j]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside
