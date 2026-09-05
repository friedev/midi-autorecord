"""End-to-end test: a fake device drives the daemon to a finished .mid file."""

from __future__ import annotations

import time

import mido

from midi_autorecord.daemon import Daemon
from tests.conftest import requires_alsa


@requires_alsa
def test_daemon_records_and_finalizes(tmp_config, fake_device):
    daemon = Daemon(tmp_config)

    # Device is already online when the daemon starts.
    daemon._spawn_online()
    assert daemon.sessions_by_id.get("testdev") is not None

    # Device plays: a little motif.
    for note, on in [(60, True), (60, False), (64, True), (64, False)]:
        fake_device.note(on=on, note=note)
        fake_device.drain()
        time.sleep(0.05)

    # Feed events to the session (the listener loop does this in production).
    for _ in range(5):
        daemon._drain()
        time.sleep(0.1)

    # Wait for the silence watchdog to finalize the take.
    deadline = time.time() + 3.0
    while time.time() < deadline:
        daemon._drain()
        if list(tmp_config.output_dir.glob("*.mid")):
            break
        time.sleep(0.05)

    midis = list(tmp_config.output_dir.glob("testdev__*.mid"))
    assert midis, "expected a finalized .mid file"
    midi = mido.MidiFile(str(midis[0]))
    messages = list(midi.tracks[0])
    note_ons = [m for m in messages if m.type == "note_on"]
    assert note_ons, "expected note_on messages in the recorded file"

    # Session stays alive ready for a new take.
    daemon._stop_sessions()
