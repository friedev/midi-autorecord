"""Command-line entry point and logging setup."""

from __future__ import annotations

import argparse
import logging
import signal
import sys

from .config import ConfigError, load_config
from .daemon import Daemon

log = logging.getLogger("midi_autorecord")


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler()
    # Match systemd log format
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    # Keep third-party modules quiet unless we're debugging.
    for name in ("mido", "pyalsa"):
        logging.getLogger(name).setLevel(level if verbose else logging.WARNING)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="midi-autorecord",
        description=(
            "Watch named ALSA MIDI devices and record their input into "
            "Standard MIDI Files."
        ),
    )
    parser.add_argument(
        "-c",
        "--config",
        default=None,
        help="path to the TOML config file (default: XDG config location)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="enable debug logging",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _setup_logging(args.verbose)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        log.error("configuration error: %s", exc)
        return 1

    if not config.devices:
        log.warning("no devices configured; nothing to watch")

    daemon = Daemon(config)
    log.info("midi-autorecord starting (devices: %d)", len(config.devices))

    def _shutdown(signum, _frame):
        log.info("received signal %s, shutting down", signum)
        daemon.stop()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        daemon.run()
    except Exception:
        log.exception("fatal error")
        return 1

    log.info("midi-autorecord stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
