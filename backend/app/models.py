import datetime as dt
from sqlalchemy import String, Float, Integer, Boolean, ForeignKey, DateTime, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class DarkStore(Base):
    __tablename__ = "dark_stores"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    packing_capacity: Mapped[int] = mapped_column(Integer, default=6)  # concurrent packing slots
    packing_seconds_per_order: Mapped[int] = mapped_column(Integer, default=90)


class InventoryItem(Base):
    __tablename__ = "inventory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("dark_stores.id"))
    sku: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    reserved_qty: Mapped[int] = mapped_column(Integer, default=0)


class Rider(Base):
    __tablename__ = "riders"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    vehicle: Mapped[str] = mapped_column(String, default="Delivery bike")
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    home_store_id: Mapped[str] = mapped_column(ForeignKey("dark_stores.id"))
    capacity_kg: Mapped[float] = mapped_column(Float, default=15.0)
    current_load_kg: Mapped[float] = mapped_column(Float, default=0.0)
    speed_kmh: Mapped[float] = mapped_column(Float, default=28.0)
    battery_pct: Mapped[float] = mapped_column(Float, default=100.0)
    status: Mapped[str] = mapped_column(String, default="AVAILABLE")  # AVAILABLE/ON_DELIVERY/OFFLINE
    shift_end: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    busy_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    observed_shift_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    # current navigation leg: origin is where this leg started (stable, so the route cache key
    # doesn't change every tick as lat/lng move), target is the destination, progress_km is how
    # far along that leg's polyline the rider has travelled. Reset whenever the target changes.
    nav_origin_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    nav_origin_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    nav_target_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    nav_target_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    route_progress_km: Mapped[float] = mapped_column(Float, default=0.0)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_lat: Mapped[float] = mapped_column(Float)
    customer_lng: Mapped[float] = mapped_column(Float)
    customer_name: Mapped[str] = mapped_column(String, default="Customer")
    address_label: Mapped[str] = mapped_column(String, default="")
    items: Mapped[list] = mapped_column(JSON)  # [{sku, qty, weight_kg}]
    weight_kg: Mapped[float] = mapped_column(Float, default=1.0)
    priority: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    promised_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, default="created")
    store_id: Mapped[str | None] = mapped_column(ForeignKey("dark_stores.id"), nullable=True)
    rider_id: Mapped[str | None] = mapped_column(ForeignKey("riders.id"), nullable=True)
    route_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)  # stop position in rider's route
    eta: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    risk: Mapped[str] = mapped_column(String, default="LOW")  # LOW/AT_RISK/DELAYED/SEVERE
    assigned_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    packed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    picked_up_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    assignment_reason: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON explain payload
    stock_check: Mapped[list | None] = mapped_column(JSON, nullable=True)


class OrderEvent(Base):
    __tablename__ = "order_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    type: Mapped[str] = mapped_column(String)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
