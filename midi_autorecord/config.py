"""Configuration loading.

Reads a TOML file (path from CLI or the XDG default) and validates it into a
typed :class:`Config`. Config is only read once at startup; reloading requires
a daemon restart.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILE_NAME = "config.toml"


class ConfigError(ValueError):
    """Raised when the configuration file is missing or invalid."""


@dataclass(frozen=True)
class DeviceConfig:
    """A MIDI input device to watch, matched against ALSA client and port names."""

    id: str
    client: str
    port: str


@dataclass(frozen=True)
class Config:
    """Validated daemon configuration."""

    output_dir: Path
    silence_timeout_seconds: float
    ticks_per_beat: int
    tempo_microseconds_per_beat: int
    devices: dict[str, DeviceConfig] = field(default_factory=dict)


def default_config_path() -> Path:
    """Return the XDG-default config path, expanding ``~``."""
    base = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    return Path(base).expanduser() / "midi-autorecord" / CONFIG_FILE_NAME


def _read_devices(raw: dict) -> dict[str, DeviceConfig]:
    devices: dict[str, DeviceConfig] = {}
    for dev_id, spec in raw.items():
        if not isinstance(spec, dict):
            raise ConfigError(f"[devices.{dev_id}] must be a table")
        client = spec.get("client")
        port = spec.get("port")
        if not isinstance(client, str) or not client.strip():
            raise ConfigError(f"[devices.{dev_id}].client must be a non-empty string")
        if not isinstance(port, str) or not port.strip():
            raise ConfigError(f"[devices.{dev_id}].port must be a non-empty string")
        devices[dev_id] = DeviceConfig(id=dev_id, client=client, port=port)
    return devices


def load_config(path: Path | None = None) -> Config:
    """Load and validate the configuration from *path*.

    Defaults to :func:`default_config_path` when *path* is ``None``.
    """
    cfg_path = path or default_config_path()
    if not cfg_path.is_file():
        raise ConfigError(f"config file not found: {cfg_path}")
    try:
        with cfg_path.open("rb") as fh:
            cfg = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"failed to parse {cfg_path}: {exc}") from exc

    silence = cfg.get("silence_timeout_seconds", 30)
    if not isinstance(silence, (int, float)) or silence < 0:
        raise ConfigError("silence_timeout_seconds must be a non-negative number")

    ticks = cfg.get("ticks_per_beat", 480)
    if not isinstance(ticks, int) or ticks <= 0:
        raise ConfigError("ticks_per_beat must be a positive integer")

    tempo = cfg.get("tempo_microseconds_per_beat", 500000)
    if not isinstance(tempo, int) or tempo <= 0:
        raise ConfigError("tempo_microseconds_per_beat must be a positive integer")

    return Config(
        output_dir=Path(cfg.get("output_dir", "~/midi-autorecord")).expanduser(),
        silence_timeout_seconds=float(silence),
        ticks_per_beat=ticks,
        tempo_microseconds_per_beat=tempo,
        devices=_read_devices(cfg.get("devices", {}) or {}),
    )
