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

NoiseGateHolder (Slice 26) tracks the single global Noise Gate
sensitivity level (see CONTEXT.md's Noise Gate entry) -- the mirror
image of MasterVolumeHolder, applied to the raw microphone input
BEFORE a Voice's Effect Step chain instead of after it. The same
cross-thread hazard applies once Slice 27 reads it from the audio
callback while a Flask request thread sets it, so it follows the same
lock-guarded pattern.

RecordingHolder (added for A/B testing workflow, not a SLICES.md slice)
tracks whether a recording of the LIVE OUTPUT (the exact audio sent to
the speaker, post-Voice-chain and post-Master-Volume) is in progress,
buffering blocks in memory rather than writing to disk -- disk I/O
inside the real-time audio callback risks exactly the kind of glitching
CLAUDE.md's "Real-time performance" notes warn against elsewhere in
this project, so `AppendBlock` only ever does a cheap, lock-guarded
list append; actual WAV-file writing happens later, on a Flask request
thread, once recording stops (see voice_engine/recording.py).

Deliberately minimal: no pub/sub, no callbacks-on-change -- just
thread-safe get/set holders (RecordingHolder buffers in memory while
active, which is its own limited form of state, but still exposes a
plain start/append/stop interface, not a persistence layer).
"""
import threading
from typing import Optional

from numpy.typing import NDArray
import numpy as np

from voice_engine.bank import VoiceBank
from voice_engine.voice import Voice

AudioBlock = NDArray[np.float32]


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
    """Holds the single global Master Volume level (a percentage, 0-400%,
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


class NoiseGateHolder:
    """Holds the single global Noise Gate sensitivity level (a
    percentage, later range-validated 0-100% in Slice 30 -- see
    CONTEXT.md's Noise Gate entry), guarded by a lock so it can be
    safely read and set from different threads.

    Defaults to 0% (gate fully open, no gating), matching this
    project's convention of a "no effect" default -- the mirror image
    of MasterVolumeHolder's 100% (unity gain) default. Deliberately
    does no range validation/clamping here -- that's Slice 30's job,
    not this one, mirroring MasterVolumeHolder's own precedent (Slice
    17 owns its range validation)."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.level = 0

    def Get(self) -> int:
        """Return the current Noise Gate level."""
        with self.lock:
            return self.level

    def Set(self, level: int) -> None:
        """Set the current Noise Gate level."""
        with self.lock:
            self.level = level


class RecordingHolder:
    """Buffers the live audio callback's final output blocks in memory
    while a recording is in progress, labeled with whichever Voice was
    active when recording started (see this module's docstring for why
    buffering in memory, not writing to disk here).

    Also carries an arbitrary `settings` snapshot (Master Volume level,
    Noise Gate level, the active Voice's full id/name/chain, sample
    rate -- whatever app.py decides is worth recording) captured at the
    same moment as `voiceLabel`. Added after real-hardware testing
    (Noise Gate at 0% during a set of otherwise-unrelated recordings)
    made it clear a filename alone doesn't capture enough to correctly
    interpret a recording later, especially given how many times this
    project's Voice chains have already changed mid-investigation --
    without a durable settings snapshot, a recording's filename could
    describe a Voice whose actual chain parameters no longer match what
    was true when the recording was made.

    Inactive (not recording) by default. `Start` clears any previous
    buffer -- only one recording is tracked at a time, matching this
    project's single-Voice/single-Stream simplicity elsewhere (no
    concurrent recordings)."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.active = False
        self.voiceLabel: Optional[str] = None
        self.settings: dict = {}
        self.blocks: list[AudioBlock] = []

    def Start(self, voiceLabel: str, settings: dict) -> None:
        """Begin a new recording labeled with `voiceLabel` (the active
        Voice's id at the moment recording starts) and carrying
        `settings` (an arbitrary, JSON-serializable snapshot of whatever
        else is worth recording alongside it -- see this class's
        docstring), discarding any previously buffered blocks."""
        with self.lock:
            self.active = True
            self.voiceLabel = voiceLabel
            self.settings = settings
            self.blocks = []

    def IsActive(self) -> bool:
        """Return whether a recording is currently in progress."""
        with self.lock:
            return self.active

    def AppendBlock(self, block: AudioBlock) -> None:
        """Append one audio block to the in-progress recording, if one
        is active. A no-op (cheap to call unconditionally every block
        from the real-time audio callback) when not recording."""
        with self.lock:
            if self.active:
                self.blocks.append(block.copy())

    def Stop(self) -> tuple[bool, Optional[str], dict, list[AudioBlock]]:
        """Stop the current recording (if any), returning
        `(wasActive, voiceLabel, settings, blocks)` -- `wasActive` is
        False (and `voiceLabel`/`settings`/`blocks` empty) if no
        recording was in progress. Resets to the inactive/empty state
        regardless."""
        with self.lock:
            wasActive = self.active
            voiceLabel = self.voiceLabel
            settings = self.settings
            blocks = self.blocks
            self.active = False
            self.voiceLabel = None
            self.settings = {}
            self.blocks = []
        return wasActive, voiceLabel, settings, blocks
