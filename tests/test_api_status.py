import sys
import types
from importlib.machinery import ModuleSpec
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "server" not in sys.modules:
    server_module = types.ModuleType("server")
    server_module.__path__ = [str(ROOT / "server")]
    server_module.__spec__ = ModuleSpec("server", loader=None, is_package=True)
    sys.modules["server"] = server_module

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


def _create_client(tmp_path: Path) -> TestClient:
    config = ServerConfig(image_dir=tmp_path)
    app = create_app(config)
    return TestClient(app)


def test_status_endpoint_returns_latest_state(tmp_path: Path) -> None:
    client = _create_client(tmp_path)
    app = client.app
    state = app.state.photoframe

    image = tmp_path / "sample.jpg"
    image.write_bytes(b"data")
    state.last_rendered = image.name

    response = client.get("/status")
    assert response.status_code == 200
    payload = response.json()

    assert payload["ok"] is True
    assert payload["display_ready"] is True
    assert payload["target_size"] == [600, 448]
    assert payload["carousel"]["minutes"] == state.runtime_config.carousel_minutes
    assert payload["carousel"]["current_file"] == image.name
    assert payload["carousel"]["current_index"] == 0


def test_status_endpoint_handles_display_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _create_client(tmp_path)

    def _raise() -> bool:
        raise RuntimeError("boom")

    display_module = sys.modules["server.inky.display"]
    monkeypatch.setattr(display_module, "is_ready", _raise)

    response = client.get("/status")
    assert response.status_code == 503
    assert response.json() == {"detail": "Display status unavailable"}
