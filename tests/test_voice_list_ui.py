"""Tests for the Voice list appearing on the page (Slice 8).

Verification (from SLICES.md, Slice 8):
- Given the page is opened
- When it loads
- Then a selectable option for Passthrough is shown, and the old pitch
  slider is no longer present

There's no JS test runner in this project (and adding one is out of
scope -- see CLAUDE.md/CONTEXT.md), so this is tested at the HTML/
structural level via Flask's test client: it fetches the raw page HTML
and asserts on the string contents rather than executing the JS in a
real browser. This is a static/structural proxy for "will render
Passthrough as a selectable option when loaded in a real browser":
- The old `#pitchSlider` markup must be gone entirely.
- A `#voiceList` container must be present for the rendering JS to
  populate.
- The page's JS source must contain a fetch call to `/voices`, which
  is what makes rendering Passthrough (and any other Voice) possible
  once a browser actually executes it.
"""
from typing import Any

from flask.testing import FlaskClient

from app import app


def test_PageShowsPassthroughOptionAndHasNoPitchSlider() -> None:
    client: FlaskClient = app.test_client()

    response: Any = client.get("/")
    html: str = response.get_data(as_text=True)

    assert 'id="pitchSlider"' not in html
    assert 'id="voiceList"' in html
    assert "fetch('/voices')" in html or 'fetch("/voices")' in html
