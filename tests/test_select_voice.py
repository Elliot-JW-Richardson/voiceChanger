"""Tests for selecting the active Voice over HTTP (Slice 9).

Verification (from SLICES.md, Slice 9):
- Given the Voice Bank contains Passthrough
- When a request selects Passthrough by id
- Then the active Voice becomes Passthrough and the response confirms it

Importing `app` loads the real `voices/` directory shipped with the
project into a module-level Voice Bank and Active Voice holder, following
the precedent set in tests/test_list_voices.py. This test posts a
selection request for Passthrough's id and checks both the response body
and `ACTIVE_VOICE_HOLDER` directly (imported from `app`, as
tests/test_app.py-style tests do) to confirm the active Voice actually
changed, not just that the response claims it did.
"""
from typing import Any

from flask.testing import FlaskClient

from app import ACTIVE_VOICE_HOLDER, app


def test_SelectVoiceSetsPassthroughAsActive() -> None:
    client: FlaskClient = app.test_client()

    response = client.post("/voices/select", json={"id": "passthrough"})
    body: Any = response.get_json()

    assert body["status"] == "ok"
    assert body["activeVoiceId"] == "passthrough"
    assert ACTIVE_VOICE_HOLDER.Get().id == "passthrough"
