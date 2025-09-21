from __future__ import annotations

import json
import mimetypes
import re
import sys
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080
DEFAULT_IMAGE_DIR = Path("/image")


@dataclass
class ServerConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    image_dir: Path = DEFAULT_IMAGE_DIR


@dataclass
class ServerContext:
    config: ServerConfig
    template_dir: Path
    static_dir: Path

    @property
    def image_dir(self) -> Path:
        return self.config.image_dir


class HTTPError(Exception):
    def __init__(self, status: int, message: str = "Error") -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class Response:
    def __init__(
        self,
        body: bytes,
        status: int = 200,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.body = body
        self.status = status
        self.headers = headers or {}

    def send(self, handler: BaseHTTPRequestHandler) -> None:
        handler.send_response(self.status)
        for key, value in self.headers.items():
            handler.send_header(key, value)
        handler.end_headers()
        if self.body:
            handler.wfile.write(self.body)


class JsonResponse(Response):
    def __init__(self, payload: Any, status: int = 200, headers: Optional[Dict[str, str]] = None) -> None:
        data = json.dumps(payload).encode("utf-8")
        base_headers = {"Content-Type": "application/json; charset=utf-8", "Content-Length": str(len(data))}
        if headers:
            base_headers.update(headers)
        super().__init__(data, status=status, headers=base_headers)


class HtmlResponse(Response):
    def __init__(self, html: str, status: int = 200, headers: Optional[Dict[str, str]] = None) -> None:
        data = html.encode("utf-8")
        base_headers = {"Content-Type": "text/html; charset=utf-8", "Content-Length": str(len(data))}
        if headers:
            base_headers.update(headers)
        super().__init__(data, status=status, headers=base_headers)


class TextResponse(Response):
    def __init__(self, text: str, status: int = 200, headers: Optional[Dict[str, str]] = None) -> None:
        data = text.encode("utf-8")
        base_headers = {"Content-Type": "text/plain; charset=utf-8", "Content-Length": str(len(data))}
        if headers:
            base_headers.update(headers)
        super().__init__(data, status=status, headers=base_headers)


class FileResponse(Response):
    def __init__(self, data: bytes, content_type: str, status: int = 200, headers: Optional[Dict[str, str]] = None) -> None:
        base_headers = {"Content-Type": content_type, "Content-Length": str(len(data))}
        if headers:
            base_headers.update(headers)
        super().__init__(data, status=status, headers=base_headers)


RouteHandler = Callable[["Request", Dict[str, str]], Response]


PARAM_RE = re.compile(r"<(?:(?P<type>[a-zA-Z_][a-zA-Z0-9_]*)\:)?(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)>")


def _compile_path(path: str) -> re.Pattern[str]:
    if not path.startswith("/"):
        raise ValueError("Route paths must start with '/'")

    def replacer(match: re.Match[str]) -> str:
        param_type = match.group("type")
        name = match.group("name")
        if param_type == "path":
            return f"(?P<{name}>.+)"
        return f"(?P<{name}>[^/]+)"

    compiled = ""
    last = 0
    for match in PARAM_RE.finditer(path):
        compiled += re.escape(path[last:match.start()])
        compiled += replacer(match)
        last = match.end()
    compiled += re.escape(path[last:])
    regex = f"^{compiled}$"
    return re.compile(regex)


class Router:
    def __init__(self) -> None:
        self._routes: Dict[str, list[Tuple[re.Pattern[str], RouteHandler]]] = {}

    def add_route(self, method: str, path: str, handler: RouteHandler) -> None:
        method = method.upper()
        pattern = _compile_path(path)
        self._routes.setdefault(method, []).append((pattern, handler))

    def resolve(self, method: str, path: str) -> Tuple[Optional[RouteHandler], Dict[str, str]]:
        method = method.upper()
        for pattern, handler in self._routes.get(method, []):
            match = pattern.match(path)
            if match:
                return handler, match.groupdict()
        return None, {}

    def get(self, path: str) -> Callable[[RouteHandler], RouteHandler]:
        def decorator(func: RouteHandler) -> RouteHandler:
            self.add_route("GET", path, func)
            return func

        return decorator

    def post(self, path: str) -> Callable[[RouteHandler], RouteHandler]:
        def decorator(func: RouteHandler) -> RouteHandler:
            self.add_route("POST", path, func)
            return func

        return decorator


class Request:
    def __init__(self, handler: BaseHTTPRequestHandler, context: ServerContext, path_params: Dict[str, str]) -> None:
        parsed = urlparse(handler.path)
        self.raw_path = handler.path
        self.path = parsed.path
        self.query = parse_qs(parsed.query, keep_blank_values=True)
        self.headers = handler.headers
        self.method = handler.command
        self.rfile = handler.rfile
        self.handler = handler
        self.context = context
        self.path_params = path_params

    def get_query(self, name: str, default: Optional[str] = None) -> Optional[str]:
        values = self.query.get(name)
        if not values:
            return default
        return values[0]


def render_template(context: ServerContext, template_name: str, **vars: Any) -> str:
    layout_path = context.template_dir / "layout.html"
    template_path = context.template_dir / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"Template '{template_name}' not found")
    layout_html = layout_path.read_text(encoding="utf-8")
    template_html = template_path.read_text(encoding="utf-8")
    html = layout_html.replace("{{ content }}", template_html)
    replacements = {"title": "Inky Photoframe"}
    replacements.update({k: str(v) for k, v in vars.items()})
    for key, value in replacements.items():
        html = html.replace(f"{{{{ {key} }}}}", value)
    return html


def _safe_join(base: Path, *paths: str) -> Path:
    candidate = base.joinpath(*paths).resolve()
    try:
        base_resolved = base.resolve()
    except FileNotFoundError:
        base_resolved = base
    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise HTTPError(404, "Not found") from exc
    return candidate


def _serve_static(request: Request, params: Dict[str, str]) -> Response:
    resource = params.get("resource", "")
    if not resource:
        raise HTTPError(404, "Not found")
    static_path = _safe_join(request.context.static_dir, resource)
    if not static_path.exists() or not static_path.is_file():
        raise HTTPError(404, "Not found")
    data = static_path.read_bytes()
    content_type = mimetypes.guess_type(static_path.name)[0] or "application/octet-stream"
    return FileResponse(data, content_type)


def _serve_index(request: Request, params: Dict[str, str]) -> Response:
    html = render_template(request.context, "index.html")
    return HtmlResponse(html)


def _register_base_routes(router: Router, context: ServerContext) -> None:
    router.get("/")(_serve_index)
    router.get("/index.html")(_serve_index)
    router.get("/static/<path:resource>")(_serve_static)


def create_handler(router: Router, context: ServerContext) -> type[BaseHTTPRequestHandler]:
    class RequestHandler(BaseHTTPRequestHandler):
        server_version = "InkyPhotoframe/2.0"

        def _handle(self) -> None:
            handler, params = router.resolve(self.command, urlparse(self.path).path)
            if handler is None:
                response = JsonResponse({"ok": False, "error": "Not found"}, status=404)
                response.send(self)
                return
            request = Request(self, context, params)
            try:
                response = handler(request, params)
                if not isinstance(response, Response):
                    raise TypeError("Route handlers must return Response instances")
            except HTTPError as exc:
                response = JsonResponse({"ok": False, "error": exc.message}, status=exc.status)
            except Exception as exc:
                print(f"Unhandled error: {exc}", file=sys.stderr)
                response = JsonResponse({"ok": False, "error": "Internal Server Error"}, status=500)
            response.send(self)

        def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            self._handle()

        def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            self._handle()

        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), fmt % args))

    return RequestHandler


def create_server(config: Optional[ServerConfig] = None) -> ThreadingHTTPServer:
    config = config or ServerConfig()
    base_dir = Path(__file__).resolve().parent
    context = ServerContext(config=config, template_dir=base_dir / "templates", static_dir=base_dir / "static")
    router = Router()
    _register_base_routes(router, context)

    from .routes import calendar, images

    calendar.register(router, context)
    images.register(router, context)

    handler_cls = create_handler(router, context)
    server = ThreadingHTTPServer((config.host, config.port), handler_cls)
    return server


def run_server(config: Optional[ServerConfig] = None) -> None:
    from .inky import display as inky_display
    from .routes.images import stop_carousel
    from .storage.files import ensure_image_dir
    from .utils import now_iso

    config = config or ServerConfig()
    ensure_image_dir(config.image_dir)
    if not inky_display.is_ready():
        print(
            "WARNING: Inky display is not ready. Upload/list works, display actions will fail.",
            file=sys.stderr,
        )
    server = create_server(config)
    print(f"[{now_iso()}] Server running on http://{config.host}:{config.port}  (images in {config.image_dir})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_carousel()
        server.server_close()
        print("\nStopped.")


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_IMAGE_DIR",
    "ServerConfig",
    "create_server",
    "run_server",
    "JsonResponse",
    "HtmlResponse",
    "TextResponse",
    "FileResponse",
    "HTTPError",
    "render_template",
    "ServerContext",
    "Request",
]
