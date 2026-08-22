"""Tests for the recording controls appearing on the page (index.html) --
not tied to a SLICES.md slice; added for the Voice A/B testing workflow.

There's no JS test runner in this project (see CLAUDE.md/CONTEXT.md), so
this is tested at the HTML/structural level via Flask's test client,
following the precedent set throughout tests/ (e.g.
test_volume_slider_ui.py, test_noise_gate_slider_ui.py): fetches the raw
page HTML and asserts on markup/script text rather than executing the JS
in a real browser.
"""
from typing import Any

from flask.testing import FlaskClient

from app import app


def test_PageShowsRecordingControlsAlongsideExistingControls() -> None:
    client: FlaskClient = app.test_client()

    response: Any = client.get("/")
    html: str = response.get_data(as_text=True)

    assert 'id="recordBtn"' in html
    assert 'id="clearRecordingsBtn"' in html
    assert 'id="recordingList"' in html
    # Existing controls must still be present -- this adds a section
    # alongside them, not in place of them.
    assert 'id="voiceList"' in html
    assert 'id="volumeSlider"' in html
    assert 'id="noiseGateSlider"' in html


def test_PageWiresRecordButtonToStartAndStopRecordingEndpoints() -> None:
    client: FlaskClient = app.test_client()

    response: Any = client.get("/")
    html: str = response.get_data(as_text=True)

    assert "fetch('/recordings/start'" in html or 'fetch("/recordings/start"' in html
    assert "fetch('/recordings/stop'" in html or 'fetch("/recordings/stop"' in html

    scriptStart: int = html.index("<script>")
    scriptEnd: int = html.index("</script>")
    script: str = html[scriptStart:scriptEnd]

    recordBtnIndex: int = script.index("recordBtn")
    clickWiringIndex: int = script.index("addEventListener('click'", recordBtnIndex)
    startFetchIndex: int = (
        script.index("fetch('/recordings/start'")
        if "fetch('/recordings/start'" in script
        else script.index('fetch("/recordings/start"')
    )

    # The start-recording fetch must come after the button is known
    # about and a click listener is registered relative to it -- not
    # merely appear anywhere unrelated in the file.
    assert recordBtnIndex < clickWiringIndex < startFetchIndex


def test_PageWiresClearButtonToClearRecordingsEndpoint() -> None:
    client: FlaskClient = app.test_client()

    response: Any = client.get("/")
    html: str = response.get_data(as_text=True)

    assert "fetch('/recordings/clear'" in html or 'fetch("/recordings/clear"' in html

    scriptStart: int = html.index("<script>")
    scriptEnd: int = html.index("</script>")
    script: str = html[scriptStart:scriptEnd]

    clearBtnIndex: int = script.index("clearRecordingsBtn")
    clickWiringIndex: int = script.index("addEventListener('click'", clearBtnIndex)
    clearFetchIndex: int = (
        script.index("fetch('/recordings/clear'")
        if "fetch('/recordings/clear'" in script
        else script.index('fetch("/recordings/clear"')
    )

    assert clearBtnIndex < clickWiringIndex < clearFetchIndex
