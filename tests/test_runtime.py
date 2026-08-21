"""Tests for the Active Voice holder (Slice 5).

Verification (from SLICES.md, Slice 5):
- Given a loaded Voice Bank
- When the active Voice holder is initialized from it and then set to a
  different Voice
- Then reading it right after initialization returns the default Voice,
  and reading it after the update returns the newly set Voice
"""
from voice_engine.bank import VoiceBank
from voice_engine.runtime import ActiveVoiceHolder
from voice_engine.voice import Voice


def test_active_voice_holder_initializes_from_default_and_can_be_updated() -> None:
    defaultVoice = Voice(id="passthrough", name="Passthrough", default=True, chain=[])
    otherVoice = Voice(id="example", name="Example Voice", default=False, chain=[])
    voiceBank = VoiceBank(voices=[defaultVoice, otherVoice], defaultVoice=defaultVoice)

    activeVoiceHolder = ActiveVoiceHolder(voiceBank)

    assert activeVoiceHolder.Get() == defaultVoice

    activeVoiceHolder.Set(otherVoice)

    assert activeVoiceHolder.Get() == otherVoice
