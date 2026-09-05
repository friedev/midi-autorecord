"""Daemon orchestration.

Owns the single ALSA sequencer listener thread and the set of active
:class:`~midi_autorecord.session.RecordingSession` objects. The listener
thread:

* reads announce-port events to learn about device connect/disconnect,
* routes MIDI events from subscribed device ports to the matching session.
"""

from __future__ import annotations

import logging
import select
import threading
import time

from .alsa import SEQ, AlsaError, AlsaSeq, event_to_mido
from .config import Config, DeviceConfig
from .session import RecordingSession

log = logging.getLogger(__name__)


class Daemon:
    """Top-level controller; construct once per config, run and stop."""

    def __init__(self, config: Config) -> None:
        self.cfg = config
        self.seq = AlsaSeq()
        self.sessions_by_id: dict[str, RecordingSession] = {}
        self.sessions_by_addr: dict[tuple[int, int], RecordingSession] = {}
        self._stop = threading.Event()

    # PUBLIC API

    def run(self) -> None:
        """Block running the listener loop until :meth:`stop` is called."""
        self._spawn_online()
        try:
            self._listener_loop()
        finally:
            self._stop_sessions()

    def stop(self) -> None:
        """Ask the daemon to shut down (safe from a signal handler)."""
        self._stop.set()

    # STARTUP

    def _spawn_online(self) -> None:
        """Start sessions for configured devices that are already connected."""
        for client, port, device in self.seq.online_matches(self.cfg.devices):
            self._spawn(client, port, device)

    def _spawn(self, client: int, port: int, device: DeviceConfig) -> None:
        if device.id in self.sessions_by_id:
            return
        session = RecordingSession(
            device,
            client,
            port,
            self.cfg.silence_timeout_seconds,
            self.cfg.ticks_per_beat,
            self.cfg.tempo_microseconds_per_beat,
            self.cfg.output_dir,
        )
        self.sessions_by_id[device.id] = session
        self.sessions_by_addr[(client, port)] = session
        try:
            self.seq.connect_device(client, port)
        except AlsaError:
            log.error("failed to subscribe to %s (%d:%d)", device.id, client, port)
        log.info("device connected %s (client %d:%d)", device.id, client, port)

    # LISTENER LOOP

    def _listener_loop(self) -> None:
        poll = select.poll()
        self.seq.register_poll(poll)
        while not self._stop.is_set():
            poll.poll(1000)
            if self._stop.is_set():
                break
            self._drain()

    def _drain(self) -> None:
        try:
            events = self.seq.receive_events()
        except AlsaError as exc:
            log.error("sequencer read failed: %s", exc)
            return
        for event in events:
            try:
                self._handle_event(event)
            except Exception:
                log.exception("error handling sequencer event")

    def _handle_event(self, event) -> None:
        if event.type in (SEQ.SEQ_EVENT_PORT_START, SEQ.SEQ_EVENT_PORT_EXIT):
            addr = event.get_data()
            client, port = int(addr["addr.client"]), int(addr["addr.port"])
            if event.type == SEQ.SEQ_EVENT_PORT_START:
                self._on_port_start(client, port)
            else:
                self._on_port_exit(client, port)
            return

        source = event.source
        client, port = int(source[0]), int(source[1])
        session = self.sessions_by_addr.get((client, port))
        if session is None:
            return
        msg = event_to_mido(event)
        if msg is not None:
            session.handle_event(msg, time.monotonic())

    def _on_port_start(self, client: int, port: int) -> None:
        try:
            client_name, port_name = self.seq.port_names(client, port)
        except AlsaError:
            log.debug("could not resolve port %d:%d", client, port)
            return
        device = self._match(client_name, port_name)
        if device is not None:
            self._spawn(client, port, device)

    def _on_port_exit(self, client: int, port: int) -> None:
        session = self.sessions_by_addr.pop((client, port), None)
        if session is None:
            return
        self.sessions_by_id.pop(session.device.id, None)
        try:
            self.seq.disconnect_device(client, port)
        except AlsaError:
            pass
        log.info(
            "device disconnected %s (client %d:%d)",
            session.device.id,
            client,
            port,
        )
        session.stop()

    def _match(self, client_name: str, port_name: str) -> DeviceConfig | None:
        """Return the first configured device matching both names."""
        for device in self.cfg.devices.values():
            if device.client == client_name and device.port == port_name:
                return device
        return None

    # SHUTDOWN

    def _stop_sessions(self) -> None:
        for session in list(self.sessions_by_id.values()):
            session.stop()
        self.sessions_by_id.clear()
        self.sessions_by_addr.clear()
