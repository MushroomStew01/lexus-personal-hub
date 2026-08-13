from lexus_hub import __version__
from lexus_hub.config import Settings


def test_package_version():
    assert __version__ == "0.1.0"


def test_location_storage_is_opt_in():
    settings = Settings(_env_file=None)
    assert settings.store_location is False
    assert setttings.show_exact_location is False
