"""Tests for listing available Voices over HTTP (Slice 7).

Verification (from SLICES.md, Slice 7):
- Given the Voice Bank contains Passthrough
- When the voice list is requested
- Then the response lists Passthrough by id and name and marks it as the
  active Voice

Importing `app` loads the real `voices/` directory shipped with the
project into a module-level Voice Bank and Active Voice holder; the
active Voice defaults to Passthrough because `voices/passthrough.yaml`
is marked `default: true` (see tests/test_passthrough_voice.py), so this
test doesn't need to select a Voice explicitly to satisfy the "Given"
precondition. Uses Flask's test client since this exercises an HTTP
route, following the precedent set in tests/test_app.py.
"""
from typing import Any

from flask.testing import FlaskClient

from app import app


def test_ListVoicesReturnsPassthroughAsActive() -> None:
    client: FlaskClient = app.test_client()

    response = client.get("/voices")
    body: Any = response.get_json()

    voiceIds = [voice["id"] for voice in body["voices"]]
    voiceNames = [voice["name"] for voice in body["voices"]]

    assert "passthrough" in voiceIds
    assert "Passthrough" in voiceNames
    assert body["activeVoiceId"] == "passthrough"
