"""Unit tests for the finalizer: trimming and SMF building."""

from __future__ import annotations

import mido

from midi_autorecord.finalize import (
    build_midi,
    trim,
    write_midi,
)

TICKS = 480
TEMPO = 500000


def _note(msg_type: str, note: int, t: float):
    if msg_type == "control_change":
        return (t, mido.Message(msg_type, channel=0, control=note, value=64))
    velocity = 90 if msg_type == "note_on" else 0
    return (t, mido.Message(msg_type, channel=0, note=note, velocity=velocity))


def test_trim_leading_and_trailing():
    events = [
        _note("control_change", 1, 0.0),
        _note("note_on", 60, 1.0),
        _note("note_off", 60, 2.0),
        _note("note_on", 64, 3.0),
        _note("note_off", 64, 4.0),
        _note("control_change", 2, 5.0),
    ]
    trimmed = trim(events)
    # leading controller dropped, first event is the first note at t=1.0
    assert trimmed[0][1].type == "note_on"
    assert trimmed[0][0] == 1.0
    # trailing controller dropped; last event is the last note_off
    assert trimmed[-1][1].type == "note_off"


def test_write_midi_and_read_back(tmp_path):
    events = [_note("note_on", 60, 0.0), _note("note_off", 60, 0.5)]
    path = tmp_path / "x.mid"
    assert write_midi(events, path, TICKS, TEMPO)
    midi = mido.MidiFile(str(path))
    assert midi.type == 1
    assert midi.ticks_per_beat == TICKS
    assert any(getattr(m, "type", "") == "note_on" for m in midi.tracks[0])


def test_no_notes_returns_false(tmp_path):
    events = [_note("control_change", 1, 0.0)]
    assert not write_midi(events, tmp_path / "y.mid", TICKS, TEMPO)


def test_build_midi_first_note_at_zero():
    events = [
        _note("note_on", 60, 5.0),
        _note("note_on", 64, 5.5),
        _note("note_off", 60, 6.0),
    ]
    midi = build_midi(events, TICKS, TEMPO)
    first = midi.tracks[0][1]  # after set_tempo
    assert first.type == "note_on"
    assert first.time == 0
