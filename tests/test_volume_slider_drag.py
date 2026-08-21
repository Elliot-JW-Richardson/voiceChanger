"""Tests for dragging the volume slider updating Master Volume (Slice 18).

Verification (from SLICES.md, Slice 18):
- Given the volume slider is shown on the page
- When it is moved to a new level
- Then the new level is sent to set the Master Volume

There's no JS test runner in this project (and adding one is out of
scope -- see CLAUDE.md/CONTEXT.md), so -- following the precedent set by
tests/test_voice_selection_click.py (Slice 10) -- this is tested at the
HTML/structural level via Flask's test client: it fetches the raw page
HTML and asserts on the string contents rather than executing the JS in
a real browser. This is a static/structural proxy for "dragging the
slider actually sends the new level to POST /volume":
- The page's JS source must contain a POST fetch call to `/volume`,
  which is what SetVolume (app.py) expects in order to change the
  Master Volume level.
- That fetch call must appear textually after `id="volumeSlider"` is
  referenced and after a `change` event is registered via
  `addEventListener('change'` on it -- `change` (not `input`) is used
  deliberately so the request fires once the user releases the slider
  rather than flooding the server on every pixel of drag movement.
"""
from typing import Any

from flask.testing import FlaskClient

from app import app


def test_PageWiresSliderChangeToSetVolumeEndpoint() -> None:
    client: FlaskClient = app.test_client()

    response: Any = client.get("/")
    html: str = response.get_data(as_text=True)

    assert "fetch('/volume'" in html or 'fetch("/volume"' in html

    scriptStart: int = html.index("<script>")
    scriptEnd: int = html.index("</script>")
    script: str = html[scriptStart:scriptEnd]

    volumeSliderIndex: int = script.index("volumeSlider")
    changeWiringIndex: int = script.index("addEventListener('change'", volumeSliderIndex)
    volumeFetchIndex: int = (
        script.index("fetch('/volume'", changeWiringIndex)
        if "fetch('/volume'" in script
        else script.index('fetch("/volume"', changeWiringIndex)
    )

    # The POST-volume fetch must come after both the slider is known
    # about and a change listener is registered relative to it -- not
    # merely appear anywhere unrelated in the file (e.g. the pre-existing
    # GET /volume call inside renderVolumeSlider from Slice 16).
    assert volumeSliderIndex < changeWiringIndex < volumeFetchIndex

    # Must be a POST (not the pre-existing GET used to render the
    # initial slider position in renderVolumeSlider).
    postFetchSnippet: str = script[volumeFetchIndex:volumeFetchIndex + 200]
    assert "method: 'POST'" in postFetchSnippet or 'method: "POST"' in postFetchSnippet
