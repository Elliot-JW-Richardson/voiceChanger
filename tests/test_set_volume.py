"""Tests for setting the Master Volume level over HTTP (Slice 17).

Verification (from SLICES.md, Slice 17):
- Given a request sets the Master Volume to a specific level within the
  valid range
- When the volume is read back
- Then it reflects the new level

Importing `app` loads the real, module-level `MASTER_VOLUME_HOLDER` (see
voice_engine/runtime.py's MasterVolumeHolder), which is a shared
module-level global that persists across the whole pytest process (see
CLAUDE.md's Testing notes). This test mutates it via POST /volume, so it
follows the same save-before/restore-in-finally pattern
tests/test_deep_voice.py::test_SelectDeepVoiceSetsItAsActive uses for
ACTIVE_VOICE_HOLDER, to avoid leaking a non-default level into
tests/test_get_volume.py (which assumes the default 100%) depending on
pytest's run order.

Uses Flask's test client since this exercises an HTTP route, following
the precedent set in tests/test_select_voice.py.
"""
from typing import Any

from flask.testing import FlaskClient

from app import MASTER_VOLUME_HOLDER, app


def test_SetVolumeUpdatesTheLevel() -> None:
    client: FlaskClient = app.test_client()
    previouslySetLevel = MASTER_VOLUME_HOLDER.Get()

    try:
        response = client.post("/volume", json={"level": 150})
        body: Any = response.get_json()

        assert body["status"] == "ok"
        assert body["level"] == 150
        assert MASTER_VOLUME_HOLDER.Get() == 150

        readBackResponse = client.get("/volume")
        readBackBody: Any = readBackResponse.get_json()

        assert readBackBody["level"] == 150
    finally:
        # MASTER_VOLUME_HOLDER is a shared module-level global (see
        # CLAUDE.md's Testing notes) that outlives this test within the
        # pytest process -- restore it so other test modules that assume
        # the default level (e.g. test_get_volume.py) aren't affected by
        # test ordering.
        MASTER_VOLUME_HOLDER.Set(previouslySetLevel)
