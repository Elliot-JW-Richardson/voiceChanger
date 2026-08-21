"""Runtime holders: thread-safe get/set state shared between the Flask
request thread(s) and sounddevice's real-time audio callback thread.

ActiveVoiceHolder tracks exactly one currently active Voice (see
CONTEXT.md's Relationships section -- "exactly one Voice is active in
the engine at a time"), safely readable and settable from two different
threads.

This anticipates Slice 6, where the real-time audio callback thread
reads the active Voice while a Flask request thread sets it (see
CLAUDE.md's Architecture notes on `audio_callback` running on
sounddevice's own thread, not the Flask request thread). A
`threading.Lock` guards every read and write so that hazard is safe
here, even though this slice does not yet wire the holder into either
thread.

MasterVolumeHolder (Slice 13) tracks the single global Master Volume
level (see CONTEXT.md's Master Volume entry and ADR 0002) -- the same
cross-thread hazard applies once Slice 14 reads it from the audio
callback while a Flask request thread sets it, so it follows the same
lock-guarded pattern.

Deliberately minimal: no pub/sub, no callbacks-on-change, no
persistence -- just thread-safe get/set holders.
"""
import threading

from voice_engine.bank import VoiceBank
from voice_engine.voice import Voice


class ActiveVoiceHolder:
    """Holds exactly one currently-active Voice, guarded by a lock so it
    can be safely read and set from different threads."""

    def __init__(self, voiceBank: VoiceBank) -> None:
        self.lock = threading.Lock()
        self.activeVoice = voiceBank.defaultVoice

    def Get(self) -> Voice:
        """Return the currently active Voice."""
        with self.lock:
            return self.activeVoice

    def Set(self, voice: Voice) -> None:
        """Set the currently active Voice."""
        with self.lock:
            self.activeVoice = voice


class MasterVolumeHolder:
    """Holds the single global Master Volume level (a percentage, 0-200%,
    100% = unity gain -- see CONTEXT.md's Master Volume entry), guarded by
    a lock so it can be safely read and set from different threads.

    Defaults to 100% (unchanged output). Deliberately does no range
    validation/clamping here -- that's Slice 17's job, not this one,
    mirroring how ActiveVoiceHolder also does no validation on what
    Voice it's set to."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.level = 100

    def Get(self) -> int:
        """Return the current Master Volume level."""
        with self.lock:
            return self.level

    def Set(self, level: int) -> None:
        """Set the current Master Volume level."""
        with self.lock:
            self.level = level
