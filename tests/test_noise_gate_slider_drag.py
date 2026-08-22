"""Tests for dragging the noise gate slider updating the Noise Gate (Slice 31).

Verification (from SLICES.md, Slice 31):
- Given the noise gate slider is shown on the page
- When it is moved to a new level
- Then the new level is sent to set the Noise Gate

There's no JS test runner in this project (and adding one is out of
scope -- see CLAUDE.md/CONTEXT.md), so -- following the precedent set by
tests/test_volume_slider_drag.py (Slice 18), of which this slice is the
Noise Gate mirror (see SLICES.md's Band 6 banner) -- this is tested at
the HTML/structural level via Flask's test client: it fetches the raw
page HTML and asserts on the string contents rather than executing the
JS in a real browser. This is a static/structural proxy for "dragging
the slider actually sends the new level to POST /noise_gate":
- The page's JS source must contain a POST fetch call to `/noise_gate`,
  which is what SetNoiseGate (app.py) expects in order to change the
  Noise Gate level.
- That fetch call must appear textually after `id="noiseGateSlider"` is
  referenced and after a `change` event is registered via
  `addEventListener('change'` on it -- `change` (not `input`) is used
  deliberately so the request fires once the user releases the slider
  rather than flooding the server on every pixel of drag movement.
"""
from typing import Any

from flask.testing import FlaskClient

from app import app


def test_PageWiresSliderChangeToSetNoiseGateEndpoint() -> None:
    client: FlaskClient = app.test_client()

    response: Any = client.get("/")
    html: str = response.get_data(as_text=True)

    assert "fetch('/noise_gate'" in html or 'fetch("/noise_gate"' in html

    scriptStart: int = html.index("<script>")
    scriptEnd: int = html.index("</script>")
    script: str = html[scriptStart:scriptEnd]

    noiseGateSliderIndex: int = script.index("noiseGateSlider")
    changeWiringIndex: int = script.index("addEventListener('change'", noiseGateSliderIndex)
    noiseGateFetchIndex: int = (
        script.index("fetch('/noise_gate'", changeWiringIndex)
        if "fetch('/noise_gate'" in script
        else script.index('fetch("/noise_gate"', changeWiringIndex)
    )

    # The POST-noise_gate fetch must come after both the slider is known
    # about and a change listener is registered relative to it -- not
    # merely appear anywhere unrelated in the file (e.g. the pre-existing
    # GET /noise_gate call inside renderNoiseGateSlider from Slice 29).
    assert noiseGateSliderIndex < changeWiringIndex < noiseGateFetchIndex

    # Must be a POST (not the pre-existing GET used to render the
    # initial slider position in renderNoiseGateSlider).
    postFetchSnippet: str = script[noiseGateFetchIndex:noiseGateFetchIndex + 200]
    assert "method: 'POST'" in postFetchSnippet or 'method: "POST"' in postFetchSnippet
