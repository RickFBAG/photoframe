from __future__ import annotations

import sys
import types
from importlib.machinery import ModuleSpec
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

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
from server.storage.files import list_images_sorted


def _create_client(tmp_path: Path) -> TestClient:
    config = ServerConfig(image_dir=tmp_path)
    app = create_app(config)
    return TestClient(app)


def _create_image(path: Path, color: str = "red") -> None:
    image = Image.new("RGB", (32, 32), color=color)
    image.save(path, format="JPEG")


def test_list_images_returns_metadata(tmp_path: Path) -> None:
    first = tmp_path / "alpha.jpg"
    second = tmp_path / "bravo.png"
    first.write_bytes(b"data")
    second.write_bytes(b"other")

    client = _create_client(tmp_path)

    response = client.get("/list")
    assert response.status_code == 200
    payload = response.json()

    assert payload["ok"] is True
    names = [item["name"] for item in payload["items"]]
    assert names == sorted(names)
    urls = {item["url"] for item in payload["items"]}
    assert f"/image/{first.name}" in urls
    assert f"/image/{second.name}" in urls


def test_display_missing_file_returns_404(tmp_path: Path) -> None:
    client = _create_client(tmp_path)

    response = client.post("/display", params={"file": "missing.jpg"})
    assert response.status_code == 404
    assert response.json() == {"ok": False, "error": "Image not found"}


def test_display_handles_offline_display(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_path = tmp_path / "sample.jpg"
    _create_image(image_path)

    client = _create_client(tmp_path)

    display_module = sys.modules["server.inky.display"]
    monkeypatch.setattr(display_module, "is_ready", lambda: False)

    response = client.post("/display", params={"file": image_path.name})
    assert response.status_code == 503
    assert response.json() == {"ok": False, "error": "Inky display not available"}


def test_delete_removes_file_and_updates_state(tmp_path: Path) -> None:
    first = tmp_path / "alpha.jpg"
    second = tmp_path / "bravo.jpg"
    _create_image(first, color="blue")
    _create_image(second, color="green")

    client = _create_client(tmp_path)
    state = client.app.state.photoframe

    # display the first image to seed the carousel state
    response = client.post("/display", params={"file": first.name})
    assert response.status_code == 200

    response = client.post("/delete", params={"file": first.name})
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    assert not first.exists()
    remaining = list(list_images_sorted(state.image_dir))
    assert remaining and remaining[0].name == second.name

    snapshot = state.carousel.snapshot(
        remaining,
        last_rendered=state.last_rendered,
        default_minutes=state.runtime_config.carousel_minutes,
    )
    assert snapshot.current_file == second.name
    assert snapshot.current_index == 0
