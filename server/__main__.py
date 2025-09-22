from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import uvicorn

from .app import (
    DEFAULT_ADMIN_RATE_LIMIT,
    DEFAULT_HOST,
    DEFAULT_IMAGE_DIR,
    DEFAULT_PORT,
    ServerConfig,
    create_app,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inky photoframe FastAPI server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host interface to bind to")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on")
    parser.add_argument(
        "--image-dir",
        type=Path,
        default=DEFAULT_IMAGE_DIR,
        help="Directory to store processed images",
    )
    parser.add_argument("--admin-token", default=None, help="Token required for administrative endpoints")
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=DEFAULT_ADMIN_RATE_LIMIT,
        help="Maximum number of administrative requests per minute (0 to disable)",
    )
    parser.add_argument("--log-file", type=Path, default=None, help="Path to the server log file")
    parser.add_argument("--log-level", default="info", help="Uvicorn log level")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    config = ServerConfig(
        host=args.host,
        port=args.port,
        image_dir=args.image_dir,
        admin_token=args.admin_token,
        rate_limit_per_minute=args.rate_limit,
        log_path=args.log_file,
    )
    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port, log_level=args.log_level)


if __name__ == "__main__":  # pragma: no cover
    main()
