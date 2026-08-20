"""Voice Bank loader: discovers every Voice definition file in a
directory and loads each one into a single in-memory Voice Bank (see
CONTEXT.md's Voice Bank entry and ADR 0001).

This reuses `voice_engine.voice.LoadVoice` to parse each discovered file
-- it does not duplicate that YAML-parsing logic, per that function's
docstring. Only the directory scan and collection into a `VoiceBank` are
added here.
"""
from dataclasses import dataclass
from pathlib import Path

from voice_engine.voice import LoadVoice, Voice


@dataclass
class VoiceBank:
    """All Voices loaded from a `voices/`-style directory, plus the one
    marked as the default Voice."""

    voices: list[Voice]
    defaultVoice: Voice


def LoadVoiceBank(voicesDirectoryPath: str) -> VoiceBank:
    """Scan `voicesDirectoryPath` for Voice definition files (`*.yaml`),
    load each one via `LoadVoice`, and collect them into a VoiceBank that
    also identifies the Voice marked as default."""
    voiceFilePaths = sorted(Path(voicesDirectoryPath).glob("*.yaml"))
    voices = [LoadVoice(str(voiceFilePath)) for voiceFilePath in voiceFilePaths]
    defaultVoice = next(voice for voice in voices if voice.default)

    return VoiceBank(voices=voices, defaultVoice=defaultVoice)
