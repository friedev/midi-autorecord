"""Headless MIDI auto-recorder daemon.

Watches for named ALSA sequencer devices, records their MIDI input into
takes, and finalizes each take as a Standard MIDI File after a configurable
silence timeout (or on device disconnect / shutdown).
"""

__version__ = "0.1.0"
