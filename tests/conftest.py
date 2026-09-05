"""Pytest fixtures shared across the test suite."""

from __future__ import annotations

from pathlib import Path

import pytest


def _alsa_available() -> bool:
    """Best-effort check that pyalsa can open the ALSA sequencer."""
    try:
        import pyalsa.alsaseq  # noqa: F401

        return True
    except ImportError, OSError:
        return False


requires_alsa = pytest.mark.skipif(
    not _alsa_available(), reason="pyalsa / ALSA sequencer not available"
)


@pytest.fixture
def tmp_config(tmp_path: Path):
    """Write a minimal config and return the parsed :class:`Config`."""
    from midi_autorecord.config import load_config

    output = tmp_path / "out"
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        f"output_dir = {str(output)!r}\n"
        "silence_timeout_seconds = 0.3\n"
        "ticks_per_beat = 480\n"
        "tempo_microseconds_per_beat = 500000\n"
        "[devices]\n"
        "[devices.testdev]\n"
        'client = "FakeDev"\n'
        'port = "FakeDev Port"\n',
        encoding="utf-8",
    )
    return load_config(config_file)


@pytest.fixture
def fake_device():
    """An in-process ALSA sequencer client that acts as a fake MIDI device.

    Yields a small object with ``client_id``, ``port_id`` and a
    ``send(message_bytes_or_seqevent)`` helper.
    """
    import pyalsa.alsaseq as SEQ

    class FakeDevice:
        def __init__(self) -> None:
            self.seq = SEQ.Sequencer(
                clientname="FakeDev",
                streams=SEQ.SEQ_OPEN_DUPLEX,
                mode=SEQ.SEQ_NONBLOCK,
            )
            caps = (
                SEQ.SEQ_PORT_CAP_READ
                | SEQ.SEQ_PORT_CAP_WRITE
                | SEQ.SEQ_PORT_CAP_SUBS_READ
                | SEQ.SEQ_PORT_CAP_SUBS_WRITE
            )
            self.port_id = self.seq.create_simple_port(
                "FakeDev Port", SEQ.SEQ_PORT_TYPE_MIDI_GENERIC, caps
            )

        @property
        def client_id(self) -> int:
            return self.seq.client_id

        def note(self, on: bool, note: int = 60, velocity: int = 90) -> None:
            event = SEQ.SeqEvent(
                SEQ.SEQ_EVENT_NOTEON if on else SEQ.SEQ_EVENT_NOTEOFF,
                timestamp=SEQ.SEQ_TIME_STAMP_REAL,
            )
            event.source = (self.client_id, self.port_id)
            event.set_data(
                {
                    "note.channel": 0,
                    "note.note": note,
                    "note.velocity": velocity if on else 0,
                }
            )
            self.seq.output_event(event)

        def drain(self) -> None:
            self.seq.drain_output()

    device = FakeDevice()
    yield device
