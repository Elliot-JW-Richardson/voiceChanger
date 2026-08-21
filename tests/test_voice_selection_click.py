"""Tests for selecting a Voice from the page (Slice 10).

Verification (from SLICES.md, Slice 10):
- Given the Voice list is shown on the page
- When a Voice option is clicked
- Then the page shows that Voice as the active one

There's no JS test runner in this project (and adding one is out of
scope -- see CLAUDE.md/CONTEXT.md), so -- following the precedent set by
tests/test_voice_list_ui.py (Slice 8) -- this is tested at the HTML/
structural level via Flask's test client: it fetches the raw page HTML
and asserts on the string contents rather than executing the JS in a
real browser. This is a static/structural proxy for "clicking a
voice-option button actually selects it":
- The page's JS source must contain a POST fetch call to
  `/voices/select`, which is what SelectVoice (app.py) expects in order
  to change the active Voice.
- That fetch call must appear textually after the `voice-option` class
  is assigned to the rendered buttons, and after a `click` event is
  registered via `addEventListener('click'` -- true whether the click
  handler is attached inline inside the `renderVoiceList()` forEach loop
  or via delegation on the `#voiceList` container, the two wiring
  approaches allowed by the slice's scope notes.
"""
from typing import Any

from flask.testing import FlaskClient

from app import app


def test_PageWiresVoiceOptionClicksToSelectEndpoint() -> None:
    client: FlaskClient = app.test_client()

    response: Any = client.get("/")
    html: str = response.get_data(as_text=True)

    assert "fetch('/voices/select'" in html or 'fetch("/voices/select"' in html

    scriptStart: int = html.index("<script>")
    scriptEnd: int = html.index("</script>")
    script: str = html[scriptStart:scriptEnd]

    voiceOptionIndex: int = script.index("voice-option")
    clickWiringIndex: int = script.index("addEventListener('click'", voiceOptionIndex)
    selectFetchIndex: int = (
        script.index("fetch('/voices/select'")
        if "fetch('/voices/select'" in script
        else script.index('fetch("/voices/select"')
    )

    # The select fetch must come after both the voice-option buttons are
    # known about and a click listener is registered relative to them --
    # not merely appear anywhere unrelated in the file.
    assert voiceOptionIndex < clickWiringIndex < selectFetchIndex
