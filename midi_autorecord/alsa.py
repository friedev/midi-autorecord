"""Thin wrapper around the official ``pyalsa`` ``alsaseq`` module.

Exposes the small slice of the ALSA sequencer API the daemon needs:

* subscribing to the system announce port to learn about port start/exit,
* resolving ALSA client/port names, and matching them against config,
* connecting a matched device port to our input port,
* translating raw sequencer events into :class:`mido.Message` objects.

``pyalsa``'s ``receive_events()`` uses a slightly inconsistent poll setup, so
the caller drives the read loop via :meth:`AlsaSeq.register_poll` with a
``select.poll()`` object instead of relying on its internal timeout handling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import mido
from pyalsa import alsaseq  # type: ignore

if TYPE_CHECKING:
    import select

    from .config import DeviceConfig

SEQ = alsaseq

_PORT_CAPS = (
    SEQ.SEQ_PORT_CAP_READ
    | SEQ.SEQ_PORT_CAP_SUBS_READ
    | SEQ.SEQ_PORT_CAP_WRITE
    | SEQ.SEQ_PORT_CAP_SUBS_WRITE
)

# Sequencer event types that map cleanly onto mido channel messages. Anything
# not listed here (clock, sensing, sysex, etc.) is dropped.
_NOTE_EVENTS = (SEQ.SEQ_EVENT_NOTEON, SEQ.SEQ_EVENT_NOTEOFF)
_CONTROL_EVENTS = (SEQ.SEQ_EVENT_CONTROLLER, SEQ.SEQ_EVENT_PGMCHANGE)
_PRESSURE_EVENTS = (SEQ.SEQ_EVENT_CHANPRESS, SEQ.SEQ_EVENT_KEYPRESS)


class AlsaError(RuntimeError):
    """Raised when an ALSA sequencer operation fails."""


def event_to_mido(event) -> mido.Message | None:
    """Translate a ``pyalsa`` ``SeqEvent`` into a :class:`mido.Message`.

    Returns ``None`` for events that are not relevant to final playback
    (clock, sensing, system, sysex, ...).
    """
    typ = event.type
    data = event.get_data()

    if typ in _NOTE_EVENTS:
        channel = data["note.channel"]
        note = data["note.note"]
        velocity = data["note.velocity"]
        if typ == SEQ.SEQ_EVENT_NOTEON:
            # Velocity 0 is the conventional way to send a note off.
            if velocity == 0:
                return mido.Message(
                    "note_off",
                    channel=channel,
                    note=note,
                    velocity=0,
                )
            return mido.Message(
                "note_on",
                channel=channel,
                note=note,
                velocity=velocity,
            )
        return mido.Message(
            "note_off",
            channel=channel,
            note=note,
            velocity=data.get("note.off_velocity", 0),
        )

    if typ in _PRESSURE_EVENTS:
        channel = data["note.channel"]
        if typ == SEQ.SEQ_EVENT_KEYPRESS:
            return mido.Message(
                "polytouch",
                channel=channel,
                note=data["note.note"],
                value=data["note.velocity"],
            )
        return mido.Message(
            "aftertouch",
            channel=channel,
            value=data["note.velocity"],
        )

    if typ == SEQ.SEQ_EVENT_CONTROLLER:
        return mido.Message(
            "control_change",
            channel=data["control.channel"],
            control=data["control.param"],
            value=data["control.value"],
        )

    if typ == SEQ.SEQ_EVENT_PGMCHANGE:
        return mido.Message(
            "program_change",
            channel=data["control.channel"],
            program=data["control.value"],
        )

    if typ == SEQ.SEQ_EVENT_PITCHBEND:
        # ALSA reports pitchbend as an unsigned 14-bit value (0..16383,
        # center 8192); mido wants signed -8192..8191.
        pitch = data["control.value"] - 8192
        return mido.Message(
            "pitchwheel",
            channel=data["control.channel"],
            pitch=pitch,
        )

    return None


class AlsaSeq:
    """A duplex ALSA sequencer client subscribed to the announce port."""

    def __init__(self, client_name: str = "midi-autorecord") -> None:
        try:
            self.seq = SEQ.Sequencer(
                clientname=client_name,
                streams=SEQ.SEQ_OPEN_DUPLEX,
                mode=SEQ.SEQ_NONBLOCK,
            )
            self.seq_port = self.seq.create_simple_port(
                client_name, SEQ.SEQ_PORT_TYPE_APPLICATION, _PORT_CAPS
            )
            self.seq.connect_ports(
                (SEQ.SEQ_CLIENT_SYSTEM, SEQ.SEQ_PORT_SYSTEM_ANNOUNCE),
                (self.client_id, self.seq_port),
            )
        except SEQ.SequencerError as exc:
            raise AlsaError(str(exc)) from exc

    @property
    def client_id(self) -> int:
        return self.seq.client_id

    def register_poll(self, poll: select.poll) -> None:
        """Register the sequencer input fd with the caller's poll object."""
        self.seq.register_poll(poll, input=True)

    def receive_events(self) -> list:
        """Non-blocking drain of any pending sequencer events."""
        try:
            return self.seq.receive_events()
        except SEQ.SequencerError as exc:
            raise AlsaError(str(exc)) from exc

    def port_names(self, client: int, port: int) -> tuple[str, str]:
        """Return ``(client_name, port_name)`` for an ALSA address."""
        try:
            client_name = self.seq.get_client_info(client)["name"]
            port_name = self.seq.get_port_info(port, client)["name"]
        except SEQ.SequencerError as exc:
            raise AlsaError(str(exc)) from exc
        return client_name, port_name

    def connect_device(self, client: int, port: int) -> None:
        """Subscribe a device output port to our input port."""
        try:
            self.seq.connect_ports((client, port), (self.client_id, self.seq_port))
        except SEQ.SequencerError as exc:
            raise AlsaError(str(exc)) from exc

    def disconnect_device(self, client: int, port: int) -> None:
        """Unsubscribe a device output port from our input port."""
        try:
            self.seq.disconnect_ports((client, port), (self.client_id, self.seq_port))
        except SEQ.SequencerError:
            # Unplugging a device removes its port, so unsubscribing may fail.
            pass

    def online_matches(
        self, devices: dict[str, DeviceConfig]
    ) -> list[tuple[int, int, DeviceConfig]]:
        """Find already-online ports matching *devices*.

        Returns a list of ``(client, port, device_config)`` tuples. Config
        ordering is respected (first match wins), and each configured device
        is reported at most once.
        """
        found: list[tuple[int, int, DeviceConfig]] = []
        matched: set[str] = set()
        for client_name, client_id, ports in self.seq.connection_list():
            for port_name, port_id, _ in ports:
                for dev_id, device in devices.items():
                    if dev_id in matched:
                        continue
                    if device.client == client_name and device.port == port_name:
                        found.append((client_id, port_id, device))
                        matched.add(dev_id)
                        break
        return found
