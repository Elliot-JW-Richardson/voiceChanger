"""Tests for loading a single Voice definition into a Voice (Slice 2).

Verification (from SLICES.md, Slice 2):
- Given a Voice definition describing an id, a name, and an ordered list of
  Effect Steps
- When it is loaded
- Then the resulting Voice exposes that same id, name, and ordered Effect
  Steps
"""
from pathlib import Path

from voice_engine.voice import EffectStep, LoadVoice, Voice


def test_VoiceLoadedFromDefinitionExposesIdNameAndOrderedChain(tmp_path: Path) -> None:
    voiceFilePath = tmp_path / "example.yaml"
    voiceFilePath.write_text(
        """
id: example
name: Example Voice
default: false
chain:
  - type: pitch_shift
    semitones: -6
  - type: ring_mod
    rate: 30
""",
        encoding="utf-8",
    )

    voice = LoadVoice(str(voiceFilePath))

    assert voice.id == "example"
    assert voice.name == "Example Voice"
    assert voice.default is False
    assert voice.chain == [
        EffectStep(type="pitch_shift", params={"semitones": -6}),
        EffectStep(type="ring_mod", params={"rate": 30}),
    ]


def test_VoiceLoadedFromDefinitionWithEmptyChainAndDefaultFlag(tmp_path: Path) -> None:
    voiceFilePath = tmp_path / "passthrough.yaml"
    voiceFilePath.write_text(
        """
id: passthrough
name: Passthrough
default: true
chain: []
""",
        encoding="utf-8",
    )

    voice = LoadVoice(str(voiceFilePath))

    assert voice == Voice(id="passthrough", name="Passthrough", default=True, chain=[])
