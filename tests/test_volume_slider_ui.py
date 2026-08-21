"""Tests for the Volume slider appearing on the page (Slice 16).

Verification (from SLICES.md, Slice 16):
- Given the page is opened
- When it loads
- Then a volume slider is shown, positioned at the current Master Volume
  level

There's no JS test runner in this project (and adding one is out of
scope -- see CLAUDE.md/CONTEXT.md), so this is tested at the HTML/
structural level via Flask's test client: it fetches the raw page HTML
and asserts on the string contents rather than executing the JS in a
real browser. This is a static/structural proxy for "will render the
slider positioned at the current Master Volume level when loaded in a
real browser" -- same approach as tests/test_voice_list_ui.py (Slice 8):
- A `#volumeSlider` range input must be present for the rendering JS to
  position.
- The page's JS source must contain a fetch call to `/volume`, which is
  what makes reading the current Master Volume level (and positioning
  the slider) possible once a browser actually executes it.

This slice is read-only: it does not wire up a change/input listener
that POSTs a new volume back (that's Slice 18), so there is nothing to
assert here about outgoing volume updates.
"""
from typing import Any

from flask.testing import FlaskClient

from app import app


def test_PageShowsVolumeSliderFetchingCurrentLevel() -> None:
    client: FlaskClient = app.test_client()

    response: Any = client.get("/")
    html: str = response.get_data(as_text=True)

    assert 'id="volumeSlider"' in html
    assert 'type="range"' in html
    assert "fetch('/volume')" in html or 'fetch("/volume")' in html
    # Voice selection markup must still be present -- this slice adds
    # the volume slider alongside it, not in place of it.
    assert 'id="voiceList"' in html
