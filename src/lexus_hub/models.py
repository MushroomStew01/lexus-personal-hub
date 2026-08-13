from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .timeutil import utcnow


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    provider_vehicle_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    make: Mapped[str | None] = mapped_column(String(60), nullable=True)
    model: Mapped[str | None] = mapped_column(String(60), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=utcnow)

    snapshots: Mapped[list[Snapshot]] = relationship(
        back_populates="vehicle",
        cascade="all, delete-orphan",
    )
    trips: Mapped[list[Trip]] = relationship(
        back_populates="vehicle",
        cascade="all, delete-orphan",
    )


class Snapshot(Base):
    __tablename__ = "snapshots"
    __table_args__ = (Index("ix_snapshot_vehicle_observed", "vehicle_id", "observed_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        index=True,
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), index=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    odometer_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    fuel_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    range_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_kph: Mapped[float | None] = mapped_column(Float, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    vehicle: Mapped[Vehicle] = relationship(back_populates="snapshots")


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (Index("ix_trip_vehicle_started", "vehicle_id", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_movement_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    start_odometer_km: Mapped[float] = mapped_column(Float)
    end_odometer_km: Mapped[float] = mapped_column(Float)
    distance_km: Mapped[float] = mapped_column(Float, default=0)
    start_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    vehicle: Mapped[Vehicle] = relationship(back_populates="trips")


class FuelFill(Base):
    __tablename__ = "fuel_fills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        index=True,
    )
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), index=True)
    liters: Mapped[float] = mapped_column(Float)
    total_cost: Mapped[float] = mapped_column(Float)
    odometer_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    station: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(250), nullable=True)


class NotificationLog(Base):
    __tablename__ = "notification_log"
    __table_args__ = (Index("ix_notification_event_created", "event_key", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_key: Mapped[str] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), index=True)
    channel: Mapped[str] = mapped_column(String(40), default="discord")
    message: Mapped[str] = mapped_column(String(500))
