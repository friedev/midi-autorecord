"""Take finalization: trimming and SMF writing.

A "take" is an ordered list of ``(relative_seconds, mido.Message)`` events,
where *relative_seconds* is the time since the take started. This module turns
such an event list into a tidy Standard MIDI File:

* leading silence is trimmed so the first note starts at time 0,
* trailing non-note events after the last note are dropped.
"""

from __future__ import annotations

import logging
from pathlib import Path

import mido

log = logging.getLogger(__name__)


def _is_note(msg: mido.Message) -> bool:
    return msg.type in ("note_on", "note_off")  # type: ignore


def _is_note_on(msg: mido.Message) -> bool:
    return msg.type == "note_on" and msg.velocity > 0  # type: ignore


def trim(events: list[tuple[float, mido.Message]]) -> list[tuple[float, mido.Message]]:
    """Strip leading and trailing silence from an event list."""
    if not events:
        return events

    first_note = next(
        (i for i, (_, msg) in enumerate(events) if _is_note_on(msg)), None
    )
    start = first_note if first_note is not None else 0
    trimmed = events[start:]

    last_note = next(
        (i for i in range(len(trimmed) - 1, -1, -1) if _is_note(trimmed[i][1])), None
    )
    if last_note is not None:
        trimmed = trimmed[: last_note + 1]
    return trimmed


def build_midi(
    events: list[tuple[float, mido.Message]],
    ticks_per_beat: int,
    tempo_us: int,
) -> mido.MidiFile:
    """Convert a trimmed (or raw) event list into a :class:`mido.MidiFile`."""
    trimmed = trim(events)
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("set_tempo", tempo=tempo_us, time=0))

    if trimmed:
        t0 = trimmed[0][0]
        ticks_per_sec = ticks_per_beat * 1_000_000.0 / tempo_us
        prev_tick = 0
        for rel_t, msg in trimmed:
            tick = round((rel_t - t0) * ticks_per_sec)
            delta = tick - prev_tick
            prev_tick = tick
            m = msg.copy(time=delta)
            track.append(m)
        track.append(mido.MetaMessage("end_of_track", time=0))

    midi = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)
    midi.tracks.append(track)
    return midi


def write_midi(
    events: list[tuple[float, mido.Message]],
    path: Path,
    ticks_per_beat: int,
    tempo_us: int,
) -> bool:
    """Write *events* to a ``.mid`` file at *path*.

    Returns ``False`` if the take contained no notes (nothing worth writing).
    """
    trimmed = trim(events)
    if not trimmed or not any(_is_note(msg) for _, msg in trimmed):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    build_midi(trimmed, ticks_per_beat, tempo_us).save(path)
    return True
