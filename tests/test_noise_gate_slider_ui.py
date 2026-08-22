"""Tests for the Noise Gate slider appearing on the page (Slice 29).

Verification (from SLICES.md, Slice 29):
- Given the page is opened
- When it loads
- Then a noise gate slider is shown, positioned at the current Noise Gate
  level

There's no JS test runner in this project (and adding one is out of
scope -- see CLAUDE.md/CONTEXT.md), so this is tested at the HTML/
structural level via Flask's test client: it fetches the raw page HTML
and asserts on the string contents rather than executing the JS in a
real browser. This is a static/structural proxy for "will render the
slider positioned at the current Noise Gate level when loaded in a real
browser" -- same approach as tests/test_volume_slider_ui.py (Slice 16):
- A `#noiseGateSlider` range input must be present for the rendering JS
  to position.
- The page's JS source must contain a fetch call to `/noise_gate`,
  which is what makes reading the current Noise Gate level (and
  positioning the slider) possible once a browser actually executes it.

This slice is read-only: it does not wire up a change/input listener
that POSTs a new level back (that's Slice 30/31), so there is nothing
to assert here about outgoing noise gate updates.
"""
from typing import Any

from flask.testing import FlaskClient

from app import app


def test_PageShowsNoiseGateSliderFetchingCurrentLevel() -> None:
    client: FlaskClient = app.test_client()

    response: Any = client.get("/")
    html: str = response.get_data(as_text=True)

    assert 'id="noiseGateSlider"' in html
    assert 'type="range"' in html
    assert "fetch('/noise_gate')" in html or 'fetch("/noise_gate")' in html
    # Master Volume and Voice selection markup must still be present --
    # this slice adds the noise gate slider alongside them, not in
    # place of them.
    assert 'id="volumeSlider"' in html
    assert 'id="voiceList"' in html
