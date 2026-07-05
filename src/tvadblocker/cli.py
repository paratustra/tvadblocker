"""Command-line entry point."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from . import __version__
from .config import ConfigError, load_config

_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tvadblocker",
        description="Switch OBS scenes by detecting a channel logo over NDI.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.ini"),
        help="Path to the configuration file (default: config.ini)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=_LOG_LEVELS,
        help="Logging verbosity (default: INFO)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        logging.error("Configuration error: %s", exc)
        return 2

    # Imported lazily so --help/--version and config validation work without the
    # native NDI/OBS bindings installed.
    from .app import run

    try:
        return run(config)
    except (FileNotFoundError, RuntimeError, OSError) as exc:
        logging.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
