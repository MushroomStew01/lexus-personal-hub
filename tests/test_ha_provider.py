import pytest

from lexus_hub.config import Settings
from lexus_hub.providers.ha import HAProvider


def test_distance_and_speed_unit_conversion():
    provider = HAProvider(Settings(_env_file=None))
    distance = {
        "state": "100",
        "attributes": {"unit_of_measurement": "mi"},
    }
    speed = {
        "state": "10",
        "attributes": {"unit_of_measurement": "mph"},
    }
    assert provider._distance_km(distance) == pytest.approx(160.9344)
    assert provider._speed_kph(speed) == pytest.approx(16.09344)


def test_entity_lookup_prefers_vehicle_display_name():
    settings = Settings(_env_file=None, vehicle_display_name="Lexus IS")
    provider = HAProvider(settings)
    states = [
        {
            "entity_id": "sensor.odometer_other",
            "state": "10",
            "attributes": {"friendly_name": "Odometer Other Car"},
        },
        {
            "entity_id": "sensor.odometer_lexus",
            "state": "20",
            "attributes": {"friendly_name": "Odometer Lexus IS"},
        },
    ]
    found = provider._find(states, None, ("odometer",))
    assert found is not None
    assert found["entity_id"] == "sensor.odometer_lexus"


def test_home_assistant_binary_opening_semantics():
    provider = HAProvider(Settings(_env_file=None))
    assert provider._binary_label("off", "opening") == "Closed"
    assert provider._binary_label("on", "opening") == "Open"
    assert provider._binary_label("closed", "opening") == "Closed"
    assert provider._binary_label("open", "opening") == "Open"


def test_home_assistant_binary_lock_semantics():
    provider = HAProvider(Settings(_env_file=None))
    assert provider._binary_label("off", "lock") == "Locked"
    assert provider._binary_label("on", "lock") == "Unlocked"
    assert provider._binary_label("locked", "lock") == "Locked"
    assert provider._binary_label("unlocked", "lock") == "Unlocked"
