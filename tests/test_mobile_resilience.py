import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import lexus_hub.mobile_resilience as mobile_resilience


def test_as_utc_normalizes_naive_and_aware_datetimes():
    naive = datetime(2026, 8, 18, 0, 0, 0)
    aware = datetime(2026, 8, 17, 20, 0, 0, tzinfo=UTC)

    assert mobile_resilience._as_utc(naive) == datetime(2026, 8, 18, 0, 0, 0, tzinfo=UTC)
    assert mobile_resilience._as_utc(aware) == aware


def test_refresh_handles_naive_sqlite_timestamp_against_aware_toyota_timestamp(monkeypatch):
    settings = SimpleNamespace(ha_refresh_settle_seconds=0)
    before = datetime(2026, 8, 18, 0, 0, 0, tzinfo=UTC)

    async def fake_source_timestamp():
        return before

    async def fake_refresh(_settings):
        return {"requested": True, "source": "home_assistant_service", "service": "toyota_na.refresh"}

    async def fake_poll(_settings):
        # SQLite snapshots are stored UTC-naive, which used to raise TypeError when compared
        # with the timezone-aware Toyota/Home Assistant timestamp above.
        return {"source_updated_at": "2026-08-18T00:01:00"}

    monkeypatch.setattr(mobile_resilience, "get_settings", lambda: settings)
    monkeypatch.setattr(mobile_resilience, "_provider_source_timestamp", fake_source_timestamp)
    monkeypatch.setattr(mobile_resilience, "request_vehicle_refresh", fake_refresh)
    monkeypatch.setattr(mobile_resilience, "poll_once", fake_poll)

    result = asyncio.run(mobile_resilience.api_vehicle_refresh())

    assert result["verification"]["fresh_data_received"] is True
    assert result["verification"]["state"] == "fresh_vehicle_data_received"
    assert result["verification"]["before_source_updated_at"].endswith("+00:00")
    assert result["verification"]["after_source_updated_at"].endswith("+00:00")
