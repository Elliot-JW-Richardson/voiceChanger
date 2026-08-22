"""Tests for the Voice `test` flag, used to cluster diagnostic/WIP
Voices separately from finished ones in the UI (see CONTEXT.md's
"Diagnostic Voices" note and index.html's `renderVoiceList`).

Not tied to a SLICES.md slice -- added directly in response to real
feedback that the Voice list was "hard to see what's what" once
diagnostic Voices existed alongside finished ones.
"""
from pathlib import Path
from typing import Any

import pytest
from flask.testing import FlaskClient

from app import VOICE_BANK, app
from voice_engine.voice import LoadVoice, Voice


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


def test_ListVoicesIncludesTestFlag(monkeypatch: pytest.MonkeyPatch) -> None:
    # No test: true Voice ships permanently (see CONTEXT.md's
    # "Diagnostic Voices" note -- they're temporary by design, added for
    # one investigation and removed once it concludes), so a synthetic
    # one is injected into the real VOICE_BANK for the duration of this
    # test rather than depending on whichever happens to exist right now.
    syntheticTestVoice = Voice(id="synthetic_test_voice", name="Synthetic", default=False, chain=[], test=True)
    monkeypatch.setattr(VOICE_BANK, "voices", VOICE_BANK.voices + [syntheticTestVoice])

    client: FlaskClient = app.test_client()

    response = client.get("/voices")
    body: Any = response.get_json()

    voicesById = {voice["id"]: voice for voice in body["voices"]}

    # A known finished (non-test) Voice reports False...
    assert voicesById["passthrough"]["test"] is False
    # ...and the injected diagnostic/WIP Voice reports True -- confirms
    # the flag is actually wired through GET /voices, not just present
    # and always False.
    assert voicesById["synthetic_test_voice"]["test"] is True
