"""Active Voice holder: tracks exactly one currently active Voice (see
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

Deliberately minimal: no pub/sub, no callbacks-on-change, no
persistence -- just a thread-safe get/set holder initialized from a
VoiceBank's defaultVoice.
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
