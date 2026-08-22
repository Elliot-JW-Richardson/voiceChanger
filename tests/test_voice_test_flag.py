"""Tests for the Voice `test` flag, used to cluster diagnostic/WIP
Voices separately from finished ones in the UI (see CONTEXT.md's
"Diagnostic Voices" note and index.html's `renderVoiceList`).

Not tied to a SLICES.md slice -- added directly in response to real
feedback that the Voice list was "hard to see what's what" once
diagnostic Voices existed alongside finished ones.
"""
from pathlib import Path
from typing import Any

from flask.testing import FlaskClient

from app import app
from voice_engine.voice import LoadVoice


def test_VoiceWithTestFlagTrueParsesAsTest(tmp_path: Path) -> None:
    voiceFilePath = tmp_path / "example.yaml"
    voiceFilePath.write_text(
        """
id: example
name: Example
default: false
test: true
chain: []
""",
        encoding="utf-8",
    )

    voice = LoadVoice(str(voiceFilePath))

    assert voice.test is True


def test_VoiceWithoutTestFlagDefaultsToFalse(tmp_path: Path) -> None:
    voiceFilePath = tmp_path / "example.yaml"
    voiceFilePath.write_text(
        """
id: example
name: Example
default: false
chain: []
""",
        encoding="utf-8",
    )

    voice = LoadVoice(str(voiceFilePath))

    assert voice.test is False


def test_ListVoicesIncludesTestFlag() -> None:
    client: FlaskClient = app.test_client()

    response = client.get("/voices")
    body: Any = response.get_json()

    # Every shipped Voice today is a finished (non-test) Voice -- this
    # just confirms the field is present and correctly False, not that a
    # test Voice exists (none currently ship, see CONTEXT.md).
    for voice in body["voices"]:
        assert voice["test"] is False
