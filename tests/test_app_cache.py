from __future__ import annotations

import sys
import types
from importlib.machinery import ModuleSpec
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "server" not in sys.modules:
    server_module = types.ModuleType("server")
    server_module.__path__ = [str(ROOT / "server")]
    server_module.__spec__ = ModuleSpec("server", loader=None, is_package=True)
    sys.modules["server"] = server_module

# Provide a lightweight stub for the Inky display module so tests do not
# attempt to access hardware-specific functionality.
if "server.inky" not in sys.modules:
    inky_module = types.ModuleType("server.inky")
    inky_module.__path__ = [str(ROOT / "server" / "inky")]
    inky_module.__spec__ = ModuleSpec("server.inky", loader=None, is_package=True)
    sys.modules["server.inky"] = inky_module

if "server.inky.display" not in sys.modules:
    display_stub = types.ModuleType("server.inky.display")
    display_stub.set_rotation = lambda enabled: None  # type: ignore[arg-type]
    display_stub.is_ready = lambda: True
    display_stub.target_size = lambda: (600, 448)
    display_stub.panel_size = lambda: (600, 448)
    display_stub.display_image = lambda img: None
    sys.modules["server.inky.display"] = display_stub

from server.app import ServerConfig, create_app


def test_create_app_uses_cache_configuration(tmp_path: Path) -> None:
    cache_config = tmp_path / "cache.yaml"
    cache_config.write_text(
        """
memory:
  enabled: true
  max_items: 10
  default_ttl: 42
files:
  enabled: true
  directory: ./png
  default_ttl: 84
sqlite:
  enabled: true
  path: ./cache/db.sqlite
  default_ttl: 126
        """.strip(),
        encoding="utf-8",
    )

    config = ServerConfig(image_dir=tmp_path, cache_config_path=Path("cache.yaml"))
    app = create_app(config)
    state = app.state.photoframe

    assert state.cache_config_path == cache_config.resolve()
    assert state.cache_settings.memory.max_items == 10
    assert state.cache_settings.memory.default_ttl == 42
    assert state.cache_settings.files.directory == (cache_config.parent / "png").resolve()
    assert state.cache_settings.files.default_ttl == 84
    assert state.cache_settings.sqlite.path == (cache_config.parent / "cache" / "db.sqlite").resolve()
    assert state.cache_settings.sqlite.default_ttl == 126

    payload = b"test-payload"
    state.caches.store("widgets", "message", payload, ttl=60, metadata={"foo": "bar"})

    memory_entry = state.caches.memory.get("widgets", "message")
    assert memory_entry is not None and memory_entry.payload == payload

    file_entry = state.caches.files.get("widgets", "message")
    assert file_entry is not None
    assert file_entry.payload.exists()

    sqlite_entry = state.caches.sqlite.get("widgets", "message")
    assert sqlite_entry is not None
    assert state.cache_settings.sqlite.path and state.cache_settings.sqlite.path.exists()

    assert state.caches.read("widgets", "message") == payload


def test_create_app_with_missing_cache_config_uses_defaults(tmp_path: Path) -> None:
    config = ServerConfig(image_dir=tmp_path, cache_config_path=Path("missing.yaml"))
    app = create_app(config)
    state = app.state.photoframe

    expected_config_path = (tmp_path / "missing.yaml").resolve()
    assert state.cache_config_path == expected_config_path

    default_files_dir = (tmp_path / "cache" / "png").resolve()
    default_sqlite_path = (tmp_path / "cache" / "metadata.sqlite").resolve()

    assert state.cache_settings.files.directory == default_files_dir
    assert state.cache_settings.sqlite.path == default_sqlite_path

    assert state.caches.memory.enabled
    assert state.caches.files.enabled
    assert state.caches.sqlite.enabled
