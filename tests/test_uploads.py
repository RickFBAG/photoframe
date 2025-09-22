import io
import sys
import types
from importlib.machinery import ModuleSpec
from pathlib import Path

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


def _create_client(tmp_path: Path) -> TestClient:
    config = ServerConfig(image_dir=tmp_path)
    app = create_app(config)
    return TestClient(app)


def _make_image_bytes(color: str) -> bytes:
    image = Image.new("RGB", (800, 600), color=color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_upload_multiple_images_success(tmp_path: Path) -> None:
    client = _create_client(tmp_path)

    files = [
        ("file", ("one.png", _make_image_bytes("red"), "image/png")),
        ("file", ("two.jpeg", _make_image_bytes("blue"), "image/jpeg")),
    ]

    response = client.post("/upload", files=files)
    assert response.status_code == 200

    payload = response.json()
    assert payload["ok"] is True
    assert payload["errors"] == []
    assert len(payload["saved"]) == 2

    saved_files = {entry["file"] for entry in payload["saved"]}
    on_disk = {path.name for path in tmp_path.iterdir()}
    assert saved_files <= on_disk


def test_upload_partial_success(tmp_path: Path) -> None:
    client = _create_client(tmp_path)

    files = [
        ("file", ("valid.png", _make_image_bytes("green"), "image/png")),
        ("file", ("invalid.txt", b"not-an-image", "text/plain")),
    ]

    response = client.post("/upload", files=files)
    assert response.status_code == 207

    payload = response.json()
    assert payload["ok"] is False
    assert len(payload["saved"]) == 1
    assert len(payload["errors"]) == 1
    assert payload["errors"][0]["file"] == "invalid.txt"
    assert "Unsupported file type" in payload["errors"][0]["error"]

    saved_files = [entry["file"] for entry in payload["saved"]]
    for name in saved_files:
        assert (tmp_path / name).exists()


def test_upload_invalid_payload(tmp_path: Path) -> None:
    client = _create_client(tmp_path)

    response = client.post("/upload", data={"foo": "bar"})
    assert response.status_code == 400

    payload = response.json()
    assert payload["ok"] is False
    assert payload["saved"] == []
    assert len(payload["errors"]) == 1
    assert payload["errors"][0]["error"] == "Content-Type must be multipart/form-data"
    assert payload["error"] == "Content-Type must be multipart/form-data"
