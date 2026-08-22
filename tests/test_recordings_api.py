"""Tests for the recording HTTP routes (app.py) -- lets the frontend
start/stop recording the live audio callback's actual output, labeled
by whichever Voice is active, list/play back/clear recordings (not tied
to a SLICES.md slice; added for the Voice A/B testing workflow).

Uses Flask's test client, following the precedent set throughout
tests/ (e.g. test_select_voice.py). RECORDING_HOLDER is a shared
module-level global (see CLAUDE.md's Testing notes) -- tests that leave
a recording in progress must clean up after themselves, same hazard as
ACTIVE_VOICE_HOLDER/MASTER_VOLUME_HOLDER/NOISE_GATE_HOLDER.

CRITICAL: an earlier version of this file let these tests write to and
delete from the REAL `recordings/` directory (app.RECORDINGS_DIRECTORY_
PATH) -- running the test suite during development of this feature
accidentally deleted real recordings the user had just made on real
hardware, via test_ClearRecordingsDeletesAllWavFilesAndReportsCount
actually calling the real clear-all logic against the real folder. Every
test in this file now uses the `isolatedRecordingsDir` fixture below,
which monkeypatches app.RECORDINGS_DIRECTORY_PATH to a pytest tmp_path
for the duration of each test -- mirroring how tests/test_bank.py and
tests/test_voice.py already use tmp_path rather than touching the real
voices/ directory. NEVER remove this isolation; it is not optional
cleanliness, it is what stops this class of bug from recurring.
"""
from pathlib import Path
from typing import Any, Iterator

import json as jsonModule

import numpy as np
import pytest
from flask.testing import FlaskClient

import app as app_module
from app import RECORDING_HOLDER, app
from voice_engine.engine import AudioBlock


@pytest.fixture(autouse=True)
def isolatedRecordingsDir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect app.RECORDINGS_DIRECTORY_PATH to a fresh temp directory
    for the duration of one test, so nothing in this file can ever touch
    the real recordings/ folder -- see this module's docstring."""
    monkeypatch.setattr(app_module, "RECORDINGS_DIRECTORY_PATH", tmp_path)
    yield tmp_path
    # Belt-and-braces: whatever the app did during the test, make sure
    # no recording is left active for a LATER test file to inherit.
    RECORDING_HOLDER.Stop()


def test_StartRecordingReturnsActiveVoiceIdAndMarksRecordingActive() -> None:
    client: FlaskClient = app.test_client()

    response = client.post("/recordings/start")
    body: Any = response.get_json()

    assert body["status"] == "ok"
    assert body["voiceId"] == "passthrough"  # default active Voice
    assert RECORDING_HOLDER.IsActive() is True


def test_StopRecordingWithNoActiveRecordingReportsNotRecording() -> None:
    client: FlaskClient = app.test_client()

    response = client.post("/recordings/stop")
    body: Any = response.get_json()

    assert body["status"] == "not_recording"


def test_StopRecordingWritesAWavFileNamedAfterTheActiveVoice(isolatedRecordingsDir: Path) -> None:
    client: FlaskClient = app.test_client()

    client.post("/recordings/start")
    block: AudioBlock = np.zeros((100, 1), dtype=np.float32)
    RECORDING_HOLDER.AppendBlock(block)

    response = client.post("/recordings/stop")
    body: Any = response.get_json()

    assert body["status"] == "ok"
    assert body["filename"].startswith("passthrough_")
    assert body["filename"].endswith(".wav")
    assert (isolatedRecordingsDir / body["filename"]).exists()


def test_ListRecordingsReturnsWrittenFileWithSettingsSnapshot() -> None:
    client: FlaskClient = app.test_client()

    client.post("/recordings/start")
    RECORDING_HOLDER.AppendBlock(np.zeros((100, 1), dtype=np.float32))
    stopResponse = client.post("/recordings/stop")
    filename = stopResponse.get_json()["filename"]

    response = client.get("/recordings")
    body: Any = response.get_json()

    matching = next(r for r in body["recordings"] if r["filename"] == filename)
    assert matching["settings"]["voiceId"] == "passthrough"
    assert "masterVolume" in matching["settings"]
    assert "noiseGate" in matching["settings"]
    assert "chain" in matching["settings"]


def test_StopRecordingWritesASettingsSidecarCapturedAtStartTime(isolatedRecordingsDir: Path) -> None:
    client: FlaskClient = app.test_client()

    try:
        client.post("/volume", json={"level": 150})
        client.post("/noise_gate", json={"level": 20})
        client.post("/recordings/start")
        RECORDING_HOLDER.AppendBlock(np.zeros((100, 1), dtype=np.float32))
        stopResponse = client.post("/recordings/stop")
        filename = stopResponse.get_json()["filename"]

        settingsFilePath = (isolatedRecordingsDir / filename).with_suffix(".json")
        assert settingsFilePath.exists()

        settings = jsonModule.loads(settingsFilePath.read_text(encoding="utf-8"))
        assert settings["voiceId"] == "passthrough"
        assert settings["masterVolume"] == 150
        assert settings["noiseGate"] == 20
        assert settings["chain"] == []
    finally:
        # MASTER_VOLUME_HOLDER/NOISE_GATE_HOLDER are shared module-level
        # globals (see CLAUDE.md's Testing notes) -- restore defaults so
        # other test modules aren't affected by test ordering.
        client.post("/volume", json={"level": 100})
        client.post("/noise_gate", json={"level": 0})


def test_GetRecordingServesTheWrittenFile() -> None:
    client: FlaskClient = app.test_client()

    client.post("/recordings/start")
    RECORDING_HOLDER.AppendBlock(np.zeros((100, 1), dtype=np.float32))
    stopResponse = client.post("/recordings/stop")
    filename = stopResponse.get_json()["filename"]

    response = client.get(f"/recordings/{filename}")

    assert response.status_code == 200
    assert response.data[:4] == b"RIFF"  # WAV file header
    response.close()


def test_ClearRecordingsDeletesAllWavFilesAndReportsCount(isolatedRecordingsDir: Path) -> None:
    client: FlaskClient = app.test_client()

    client.post("/recordings/start")
    RECORDING_HOLDER.AppendBlock(np.zeros((100, 1), dtype=np.float32))
    client.post("/recordings/stop")
    client.post("/recordings/start")
    RECORDING_HOLDER.AppendBlock(np.zeros((100, 1), dtype=np.float32))
    client.post("/recordings/stop")

    response = client.post("/recordings/clear")
    body: Any = response.get_json()

    assert body["status"] == "ok"
    assert body["cleared"] >= 2
    assert list(isolatedRecordingsDir.glob("*.wav")) == []
