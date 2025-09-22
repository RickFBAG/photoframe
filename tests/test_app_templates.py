from __future__ import annotations

import sys
import types
from importlib.machinery import ModuleSpec
from pathlib import Path

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


def test_index_page_includes_static_assets(tmp_path: Path) -> None:
    config = ServerConfig(image_dir=tmp_path)
    app = create_app(config)

    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert '<link rel="stylesheet" href="/static/style.css">' in html
    assert '<script src="/static/main.js" defer></script>' in html
