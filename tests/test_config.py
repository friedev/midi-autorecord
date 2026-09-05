"""Unit tests for config loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from midi_autorecord.config import ConfigError, load_config


def test_defaults_and_devices(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "output_dir = '~/o'\n[devices.kbd]\nclient = 'A'\nport = 'B'\n",
        encoding="utf-8",
    )
    config = load_config(cfg)
    assert config.silence_timeout_seconds == 30
    assert config.ticks_per_beat == 480
    assert config.tempo_microseconds_per_beat == 500000
    assert str(config.output_dir) == str(Path("~/o").expanduser())
    assert config.devices["kbd"].client == "A"
    assert config.devices["kbd"].port == "B"


def test_missing_file(tmp_path: Path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.toml")


def test_invalid_silence(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("silence_timeout_seconds = -1\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(cfg)


def test_device_missing_fields(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[devices.x]\nclient = 'A'\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(cfg)
