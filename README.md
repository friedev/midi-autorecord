# midi-autorecord

A headless background daemon (Linux, ALSA sequencer) that watches for named
external MIDI devices, records their input, and writes each take to a
Standard MIDI File after a configurable silence timeout (or on device
disconnect / shutdown).

## Features

- Matches devices by **name** (ALSA client + port), not by unstable client
  numbers, so reconnects and reboots are handled automatically.
- One independent recording session per connected device; each session emits
  its own `.mid` files.
- Takes start on the first note and finalize after a silence timeout, with
  leading/trailing silence trimmed and the first note anchored at time 0.
- Runs as a `systemd --user` service, started at login.

## Dependencies

- `mido`
- [`pyalsa`](https://github.com/alsa-project/alsa-python)

The official `pyalsa` is not published to PyPI, so it is pulled from the ALSA
project's git tag. Building it requires a C compiler and `libasound` development
headers at install time.

## Install

```sh
uv sync
uv build
uv pip install .
```

## Configure

```sh
mkdir -p ~/.config/midi-autorecord
cp config.example.toml ~/.config/midi-autorecord/config.toml
# edit device names (see `aconnect -l`)
```

See [`config.example.toml`](config.example.toml). Paths support `~` expansion.
Devices are matched against the ALSA client and port name (first match wins).

## Run as a user service

```sh
mkdir -p ~/.config/systemd/user
cp systemd/midi-autorecord.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now midi-autorecord
journalctl --user -u midi-autorecord -f
```

Restart the daemon to reload config:

```sh
systemctl --user restart midi-autorecord
```

## Development

```sh
uv sync
uv run ruff format .
uv run ruff check --fix .
uv run ty check .
```
