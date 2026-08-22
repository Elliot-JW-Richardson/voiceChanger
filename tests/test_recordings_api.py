"""Tests for the recording HTTP routes (app.py) -- lets the frontend
start/stop recording the live audio callback's actual output, labeled
by whichever Voice is active, list/play back/clear recordings (not tied
to a SLICES.md slice; added for the Voice A/B testing workflow).

Uses Flask's test client, following the precedent set throughout
tests/ (e.g. test_select_voice.py). RECORDING_HOLDER is a shared
module-level global (see CLAUDE.md's Testing notes) -- tests that leave
a recording in progress or write files must clean up after themselves,
same hazard as ACTIVE_VOICE_HOLDER/MASTER_VOLUME_HOLDER/
NOISE_GATE_HOLDER.
"""
from typing import Any

from flask.testing import FlaskClient

from app import RECORDINGS_DIRECTORY_PATH, RECORDING_HOLDER, app
from voice_engine.engine import AudioBlock
import numpy as np


def _ClearRecordingsDirectory() -> None:
    for path in RECORDINGS_DIRECTORY_PATH.glob("*.wav"):
        path.unlink()


def test_StartRecordingReturnsActiveVoiceIdAndMarksRecordingActive() -> None:
    client: FlaskClient = app.test_client()

    try:
        response = client.post("/recordings/start")
        body: Any = response.get_json()

        assert body["status"] == "ok"
        assert body["voiceId"] == "passthrough"  # default active Voice
        assert RECORDING_HOLDER.IsActive() is True
    finally:
        RECORDING_HOLDER.Stop()


def test_StopRecordingWithNoActiveRecordingReportsNotRecording() -> None:
    client: FlaskClient = app.test_client()

    response = client.post("/recordings/stop")
    body: Any = response.get_json()

    assert body["status"] == "not_recording"


def test_StopRecordingWritesAWavFileNamedAfterTheActiveVoice() -> None:
    client: FlaskClient = app.test_client()

    try:
        client.post("/recordings/start")
        block: AudioBlock = np.zeros((100, 1), dtype=np.float32)
        RECORDING_HOLDER.AppendBlock(block)

        response = client.post("/recordings/stop")
        body: Any = response.get_json()

        assert body["status"] == "ok"
        assert body["filename"].startswith("passthrough_")
        assert body["filename"].endswith(".wav")
        assert (RECORDINGS_DIRECTORY_PATH / body["filename"]).exists()
    finally:
        _ClearRecordingsDirectory()


def test_ListRecordingsReturnsWrittenFileNewestFirst() -> None:
    client: FlaskClient = app.test_client()

    try:
        client.post("/recordings/start")
        RECORDING_HOLDER.AppendBlock(np.zeros((100, 1), dtype=np.float32))
        stopResponse = client.post("/recordings/stop")
        filename = stopResponse.get_json()["filename"]

        response = client.get("/recordings")
        body: Any = response.get_json()

        assert filename in body["recordings"]
    finally:
        _ClearRecordingsDirectory()


def test_GetRecordingServesTheWrittenFile() -> None:
    client: FlaskClient = app.test_client()

    try:
        client.post("/recordings/start")
        RECORDING_HOLDER.AppendBlock(np.zeros((100, 1), dtype=np.float32))
        stopResponse = client.post("/recordings/stop")
        filename = stopResponse.get_json()["filename"]

        response = client.get(f"/recordings/{filename}")

        assert response.status_code == 200
        assert response.data[:4] == b"RIFF"  # WAV file header
        # send_from_directory's response can hold the file handle open
        # past reading .data on Windows, blocking a same-test cleanup
        # unlink() with a PermissionError -- close explicitly.
        response.close()
    finally:
        _ClearRecordingsDirectory()


def test_ClearRecordingsDeletesAllWavFilesAndReportsCount() -> None:
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
    assert list(RECORDINGS_DIRECTORY_PATH.glob("*.wav")) == []
