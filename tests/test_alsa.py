"""Tests for the pyalsa/ALSA integration layer (requires a live sequencer)."""

from __future__ import annotations

import pyalsa.alsaseq as SEQ

from midi_autorecord.alsa import AlsaSeq, event_to_mido
from tests.conftest import requires_alsa


def _event(ev_type: int, data: dict):
    event = SEQ.SeqEvent(ev_type, timestamp=SEQ.SEQ_TIME_STAMP_REAL)
    event.set_data(data)
    return event


@requires_alsa
def test_event_to_mido_note():
    msg = event_to_mido(
        _event(
            SEQ.SEQ_EVENT_NOTEON,
            {"note.channel": 2, "note.note": 60, "note.velocity": 90},
        )
    )
    assert msg.type == "note_on"
    assert msg.channel == 2
    assert msg.note == 60
    assert msg.velocity == 90


@requires_alsa
def test_event_to_mido_noteon_velocity_zero_is_note_off():
    msg = event_to_mido(
        _event(
            SEQ.SEQ_EVENT_NOTEON,
            {"note.channel": 0, "note.note": 60, "note.velocity": 0},
        )
    )
    assert msg.type == "note_off"


@requires_alsa
def test_event_to_mido_ignores_clock():
    assert event_to_mido(_event(SEQ.SEQ_EVENT_CLOCK, {})) is None


@requires_alsa
def test_online_matches_finds_fake_device(fake_device):
    from midi_autorecord.config import DeviceConfig

    alsa = AlsaSeq()
    devices = {
        "testdev": DeviceConfig(id="testdev", client="FakeDev", port="FakeDev Port")
    }
    matches = alsa.online_matches(devices)
    assert (fake_device.client_id, fake_device.port_id) in [
        (c, p) for c, p, _ in matches
    ]


@requires_alsa
def test_connect_and_receive(fake_device):
    alsa = AlsaSeq()
    alsa.connect_device(fake_device.client_id, fake_device.port_id)
    fake_device.note(on=True)
    fake_device.drain()
    import time

    time.sleep(0.2)
    events = alsa.receive_events()
    assert any(e.type == SEQ.SEQ_EVENT_NOTEON for e in events)
