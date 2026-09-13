"""Per-device recording sessions.

One :class:`RecordingSession` runs per connected, configured device. It owns a
watchdog thread and accumulates incoming MIDI events in memory as a *take* --
an ordered list of time-stamped :class:`mido.Message` objects.

Takes are finalized (see :mod:`midi_autorecord.finalize`) after a configurable
silence timeout, or immediately when the device disconnects or the daemon
shuts down. After a take is finalized the session stays alive, ready to start
a fresh take if more input arrives before the device is unplugged.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime

import mido

from .config import DeviceConfig
from .finalize import write_midi

log = logging.getLogger(__name__)


class RecordingTake:
    """A single recording: an ordered list of time-stamped MIDI messages."""

    def __init__(self, stem: str, start_mono: float) -> None:
        self.stem = stem
        self.start_mono = start_mono
        self.last_note_mono = start_mono
        self.messages: list[tuple[float, mido.Message]] = []


class RecordingSession:
    """Accumulates MIDI events from one device into finalized SMF takes."""

    def __init__(
        self,
        device: DeviceConfig,
        client: int,
        port: int,
        silence_timeout: float,
        ticks_per_beat: int,
        tempo_us: int,
        output_dir,
    ) -> None:
        self.device = device
        self.client = client
        self.port = port
        self._silence = silence_timeout
        self._ticks = ticks_per_beat
        self._tempo = tempo_us
        self._output_dir = output_dir

        self._cv = threading.Condition()
        self._stop = threading.Event()
        self._take: RecordingTake | None = None

        self._thread = threading.Thread(
            target=self._watchdog,
            name=f"session-{device.id}",
            daemon=True,
        )
        self._thread.start()

    # CALLED FROM THE SEQUENCER LISTENER THREAD

    def handle_event(self, msg: mido.Message, mono: float) -> None:
        """Record a MIDI message that arrived at monotonic time *mono*."""
        with self._cv:
            take = self._take
            if take is None:
                # No active take: only a note starts one.
                if not (msg.type == "note_on" and msg.velocity > 0):  # type: ignore
                    return
                take = self._start_take(mono)
            rel_t = mono - take.start_mono
            take.messages.append((rel_t, msg))
            if msg.type in ("note_on", "note_off"):  # type: ignore
                take.last_note_mono = mono
            self._cv.notify_all()

    def _start_take(self, mono: float) -> RecordingTake:
        # Local wall-clock time without a timezone specifier, e.g.
        # "2026-09-05T20:41:50__piano".
        wall = datetime.now(UTC).astimezone().replace(tzinfo=None)
        stem = wall.replace(microsecond=0).isoformat().replace(":", "-")
        take = RecordingTake(stem, mono)
        self._take = take
        log.info(
            f"take start {self.device.id}/{stem} (client {self.client}:{self.port})"
        )
        return take

    # WATCHDOG THREAD

    def _watchdog(self) -> None:
        while True:
            with self._cv:
                while self._take is None and not self._stop.is_set():
                    self._cv.wait()
                if self._stop.is_set():
                    if self._take is not None:
                        self._finalize_take()
                    break
                take = self._take
                assert take is not None
                while self._take is take and not self._stop.is_set():
                    remaining = self._silence - (time.monotonic() - take.last_note_mono)
                    if remaining <= 0:
                        self._finalize_take()
                        break
                    self._cv.wait(timeout=remaining)

    def _finalize_take(self) -> None:
        take = self._take
        assert take is not None
        self._take = None
        out = self._output_dir / self.device.id / (take.stem + ".mid")
        wrote = write_midi(take.messages, out, self._ticks, self._tempo)
        if wrote:
            log.info(f"take finalized {self.device.id}/{take.stem} -> {out}")
        else:
            log.info(f"take finalized {self.device.id}/{take.stem}: no notes, dropped")

    # CONTROL

    def stop(self) -> None:
        """Signal the session to finalize its active take and exit."""
        with self._cv:
            self._stop.set()
            self._cv.notify_all()
        self._thread.join(timeout=5.0)
