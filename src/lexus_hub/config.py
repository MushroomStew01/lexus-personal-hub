from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_name: str = "Lexus Personal Hub"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_url: str = "sqlite:///.data/lexus_hub.db"
    timezone: str = "America/Toronto"
    dashboard_refresh_seconds: int = Field(default=60, ge=15, le=3600)
    dashboard_url: str | None = None
    local_dashboard_url: str | None = None
    map_router_url: str = "https://router.project-osrm.org"
    geoapify_api_key: str | None = None

    provider: Literal["mock", "home_assistant"] = "mock"
    poll_interval_minutes: int = Field(default=15, ge=5, le=1440)
    trip_idle_close_minutes: int = Field(default=30, ge=5, le=1440)
    min_trip_delta_km: float = Field(default=0.2, ge=0)
    max_snapshot_gap_hours: float = Field(default=6, gt=0)
    store_location: bool = False
    show_exact_location: bool = False
    named_location_default_radius_m: float = Field(default=250, ge=25, le=5000)
    parking_speed_threshold_kph: float = Field(default=1.0, ge=0, le=20)

    vehicle_display_name: str = "My Lexus"
    last_service_odometer_km: float | None = None
    service_interval_km: float = Field(default=8000, gt=0)
    fuel_tank_capacity_liters: float | None = Field(default=None, gt=0, le=200)
    low_fuel_percent: float = Field(default=20, ge=0, le=100)
    low_range_km: float = Field(default=80, ge=0)
    low_tire_psi: float = Field(default=30, ge=0, le=100)
    alert_openings: bool = False
    alert_unlocked: bool = False
    stale_telemetry_minutes: int = Field(default=180, ge=30, le=10080)
    trip_summary_enabled: bool = True
    weekly_report_enabled: bool = True
    weekly_report_weekday: int = Field(default=6, ge=0, le=6)
    weekly_report_hour: int = Field(default=19, ge=0, le=23)

    ha_base_url: str = "http://homeassistant.local:8123"
    ha_token: str | None = None
    ha_verify_ssl: bool = True
    ha_odometer_entity: str | None = None
    ha_fuel_entity: str | None = None
    ha_range_entity: str | None = None
    ha_location_entity: str | None = None
    ha_speed_entity: str | None = None
    ha_last_update_entity: str | None = None
    ha_refresh_button_entity: str | None = None
    ha_refresh_settle_seconds: int = Field(default=15, ge=0, le=120)
    post_stop_refresh_enabled: bool = False
    post_stop_refresh_delay_seconds: int = Field(default=30, ge=0, le=600)

    discord_webhook_url: str | None = None
    discord_bot_token: str | None = None
    discord_guild_id: int | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
