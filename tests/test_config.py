from smart_display.config import AppConfig, CalendarSource, ConfigManager


def test_load_and_update(tmp_path):
    config_path = tmp_path / "config.json"
    manager = ConfigManager(config_path)
    config = manager.load()
    assert isinstance(config, AppConfig)
    assert config.refresh_minutes == 15

    config.agenda.calendars.append(CalendarSource(name="Test", url="https://example.com"))
    manager.save(config)

    loaded = manager.load()
    assert loaded.agenda.calendars[0].name == "Test"

    manager.update({"refresh_minutes": 5})
    assert manager.load().refresh_minutes == 5
