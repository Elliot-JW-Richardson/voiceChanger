"""Tests for reading the current Noise Gate level over HTTP (Slice 28).

Verification (from SLICES.md, Slice 28):
- Given the Noise Gate is at its default level
- When the level is requested
- Then the response reports 0%

Importing `app` loads the real, module-level `NOISE_GATE_HOLDER` (see
voice_engine/runtime.py's NoiseGateHolder), which defaults to 0% (gate
fully open, no gating -- see CONTEXT.md's Noise Gate entry) until
something sets it, so this test doesn't need to set the level explicitly
to satisfy the "Given" precondition. This test is read-only -- it never
calls NOISE_GATE_HOLDER.Set(), so it doesn't need the restore-in-finally
pattern CLAUDE.md's Testing notes describe for ACTIVE_VOICE_HOLDER (and,
by the same hazard, MASTER_VOLUME_HOLDER/NOISE_GATE_HOLDER) -- that
pattern is only needed by tests that mutate the shared holder, e.g.
Slice 30's "set noise gate" test.

Uses Flask's test client since this exercises an HTTP route, following
the precedent set in tests/test_get_volume.py.
"""
from typing import Any

from flask.testing import FlaskClient

from app import app


def test_GetNoiseGateReturnsDefaultLevel() -> None:
    client: FlaskClient = app.test_client()

    response = client.get("/noise_gate")
    body: Any = response.get_json()

    assert body["level"] == 0
