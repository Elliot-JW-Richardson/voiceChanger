"""Tests for loading every Voice definition in a directory into a Voice
Bank (Slice 3).

Verification (from SLICES.md, Slice 3):
- Given several Voice definitions are present, one of them marked as
  default
- When the Voice Bank is loaded
- Then it contains one Voice per definition and correctly identifies the
  default Voice
"""
from pathlib import Path

from voice_engine.bank import LoadVoiceBank
from voice_engine.voice import Voice


def test_voice_bank_loads_every_definition_and_identifies_default(tmp_path: Path) -> None:
    (tmp_path / "passthrough.yaml").write_text(
        """
id: passthrough
name: Passthrough
default: true
chain: []
""",
        encoding="utf-8",
    )
    (tmp_path / "example.yaml").write_text(
        """
id: example
name: Example Voice
default: false
chain:
  - type: pitch_shift
    semitones: -6
""",
        encoding="utf-8",
    )

    voiceBank = LoadVoiceBank(str(tmp_path))

    assert len(voiceBank.voices) == 2
    assert {voice.id for voice in voiceBank.voices} == {"passthrough", "example"}
    assert voiceBank.defaultVoice == Voice(
        id="passthrough", name="Passthrough", default=True, chain=[]
    )
