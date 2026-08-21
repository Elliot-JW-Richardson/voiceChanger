"""Tests for reading the current Master Volume level over HTTP (Slice 15).

Verification (from SLICES.md, Slice 15):
- Given the Master Volume is at its default level
- When the volume is requested
- Then the response reports 100%

Importing `app` loads the real, module-level `MASTER_VOLUME_HOLDER` (see
voice_engine/runtime.py's MasterVolumeHolder), which defaults to 100%
(unity gain -- see CONTEXT.md's Master Volume entry) until something sets
it, so this test doesn't need to set the volume explicitly to satisfy the
"Given" precondition. This test is read-only -- it never calls
MASTER_VOLUME_HOLDER.Set(), so it doesn't need the restore-in-finally
pattern CLAUDE.md's Testing notes describe for ACTIVE_VOICE_HOLDER (and,
by the same hazard, MASTER_VOLUME_HOLDER) -- that pattern is only needed
by tests that mutate the shared holder, e.g. Slice 17's "set volume" test.

Uses Flask's test client since this exercises an HTTP route, following
the precedent set in tests/test_list_voices.py.
"""
from typing import Any

from flask.testing import FlaskClient

from app import app


def test_GetVolumeReturnsDefaultLevel() -> None:
    client: FlaskClient = app.test_client()

    response = client.get("/volume")
    body: Any = response.get_json()

    assert body["level"] == 100
