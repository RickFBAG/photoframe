"""Lightweight configuration server."""
from __future__ import annotations

import logging
import threading
from http import HTTPStatus
from typing import Callable, Optional

from flask import Flask, Response, jsonify, request

from ..config import ConfigManager, WebSettings

_LOGGER = logging.getLogger(__name__)

INDEX_HTML = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Smart Display Control</title>
    <style>
      body { font-family: "Segoe UI", sans-serif; margin: 2rem; background: #f7f7f5; color: #222; }
      header { margin-bottom: 1.5rem; }
      textarea { width: 100%; min-height: 20rem; font-family: monospace; padding: 1rem; border-radius: 8px; border: 1px solid #ccc; }
      button { padding: 0.6rem 1.4rem; margin-right: 1rem; border: none; border-radius: 999px; background: #222; color: #fff; cursor: pointer; }
      button.secondary { background: #e24f48; }
      .status { margin-top: 1rem; }
    </style>
  </head>
  <body>
    <header>
      <h1>Smart Display Configuration</h1>
      <p>Edit the JSON below to adjust widgets, data sources, and refresh cadence.</p>
    </header>
    <main>
      <textarea id="configArea"></textarea>
      <div class="controls">
        <button onclick="saveConfig()">Save</button>
        <button class="secondary" onclick="triggerRefresh()">Refresh Display</button>
      </div>
      <div class="status" id="status"></div>
    </main>
    <script>
      async function loadConfig() {
        const response = await fetch('/api/config');
        const config = await response.json();
        document.getElementById('configArea').value = JSON.stringify(config, null, 2);
      }
      async function saveConfig() {
        try {
          const payload = JSON.parse(document.getElementById('configArea').value);
          const response = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });
          if (!response.ok) throw new Error('Save failed');
          document.getElementById('status').innerText = 'Configuration saved.';
        } catch (err) {
          document.getElementById('status').innerText = 'Error: ' + err.message;
        }
      }
      async function triggerRefresh() {
        await fetch('/api/refresh', { method: 'POST' });
        document.getElementById('status').innerText = 'Refresh requested.';
      }
      loadConfig();
    </script>
  </body>
</html>
"""


def create_app(
    config_manager: ConfigManager,
    refresh_callback: Optional[Callable[[], None]] = None,
) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index() -> Response:
        return Response(INDEX_HTML, mimetype="text/html")

    @app.get("/api/config")
    def get_config():
        return jsonify(config_manager.load_dict())

    @app.post("/api/config")
    def update_config():
        payload = request.get_json(force=True, silent=False)
        config_manager.update(payload)
        return ("", HTTPStatus.NO_CONTENT)

    @app.post("/api/refresh")
    def refresh():
        if refresh_callback is not None:
            refresh_callback()
        return ("", HTTPStatus.NO_CONTENT)

    return app


def launch_config_server(
    settings: WebSettings,
    config_manager: ConfigManager,
    refresh_callback: Optional[Callable[[], None]] = None,
) -> threading.Thread:
    """Start the Flask development server in a daemon thread."""

    app = create_app(config_manager, refresh_callback=refresh_callback)

    def _run() -> None:
        _LOGGER.info("Starting config server on %s:%s", settings.host, settings.port)
        app.run(host=settings.host, port=settings.port, debug=False, use_reloader=False)

    thread = threading.Thread(target=_run, name="config-server", daemon=True)
    thread.start()
    return thread


__all__ = ["create_app", "launch_config_server"]
