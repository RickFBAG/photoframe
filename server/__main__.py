from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .app import DEFAULT_HOST, DEFAULT_IMAGE_DIR, DEFAULT_PORT, ServerConfig, run_server


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inky photoframe server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host interface to bind to")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on")
    parser.add_argument(
        "--image-dir",
        type=Path,
        default=DEFAULT_IMAGE_DIR,
        help="Directory to store processed images",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    config = ServerConfig(host=args.host, port=args.port, image_dir=args.image_dir)
    run_server(config)


if __name__ == "__main__":  # pragma: no cover
    main()
