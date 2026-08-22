"""Tests for setting the Noise Gate level over HTTP (Slice 30).

Verification (from SLICES.md, Slice 30):
- Given a request sets the Noise Gate to a specific level within the
  valid range
- When the level is read back
- Then it reflects the new level

Importing `app` loads the real, module-level `NOISE_GATE_HOLDER` (see
voice_engine/runtime.py's NoiseGateHolder), which is a shared
module-level global that persists across the whole pytest process (see
CLAUDE.md's Testing notes). This test mutates it via POST /noise_gate, so
it follows the same save-before/restore-in-finally pattern
tests/test_set_volume.py uses for MASTER_VOLUME_HOLDER, to avoid leaking
a non-default level into tests/test_get_noise_gate.py (which assumes the
default 0%) depending on pytest's run order.

Uses Flask's test client since this exercises an HTTP route, following
the precedent set in tests/test_set_volume.py.
"""
from typing import Any

from flask.testing import FlaskClient

from app import NOISE_GATE_HOLDER, app


def test_SetNoiseGateUpdatesTheLevel() -> None:
    client: FlaskClient = app.test_client()
    previouslySetLevel = NOISE_GATE_HOLDER.Get()

    try:
        response = client.post("/noise_gate", json={"level": 50})
        body: Any = response.get_json()

        assert body["status"] == "ok"
        assert body["level"] == 50
        assert NOISE_GATE_HOLDER.Get() == 50

        readBackResponse = client.get("/noise_gate")
        readBackBody: Any = readBackResponse.get_json()

        assert readBackBody["level"] == 50
    finally:
        # NOISE_GATE_HOLDER is a shared module-level global (see
        # CLAUDE.md's Testing notes) that outlives this test within the
        # pytest process -- restore it so other test modules that assume
        # the default level (e.g. test_get_noise_gate.py) aren't affected
        # by test ordering.
        NOISE_GATE_HOLDER.Set(previouslySetLevel)
