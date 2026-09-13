# midi-autorecord

A headless background daemon that watches for named external MIDI input devices and automatically records their input to Standard MIDI Files.
Written in Python for Linux + ALSA, with systemd support.

> [!WARNING]
> **Slop alert!**
> The initial version of this project was entirely vibe coded.
> Although I have reviewed the code myself and used it without issue, your mileage may vary.

## Motivation

I like to spontaneously noodle around on the piano, but I rarely bother to start a recording.
Sometimes, though, I'll play something I think is neat and wish I'd recorded it.

That's where this project comes in!
Now every take gets automatically saved as MIDI file I can play back or even import straight into a DAW.

## Features

- Matches devices by **name** (ALSA client + port identifiers), not by client/port *numbers*, which are unstable in my experience.
- Gracefully handles device disconnects/reconnects and service interruptions.
- Simultaneous recording of takes on all connected devices.
- Takes start on the first note and finalize after a silence timeout, with leading/trailing silence trimmed.

## Dependencies

- `mido`
- [`pyalsa`](https://github.com/alsa-project/alsa-python)

The official `pyalsa` is not published to PyPI, so it is pulled from the ALSA project's git tag.
Building it requires a C compiler and `libasound` development headers at install time.

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

See [`config.example.toml`](config.example.toml).
Paths support `~` expansion.
Devices are matched against the ALSA client and port name (first match wins).

## Run as a systemd user service

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

## See also

- [listen](https://github.com/danieljweinberg/listen): a very similar project, written in Bash
- `arecordmidi`: the absolute bare-bones, zero-dependency alternative to this, without all the conveniences
