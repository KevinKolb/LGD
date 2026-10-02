"""The home page's add-to-home-screen tip (the user, 2026-09-30): on a
phone or tablet, the first visit only."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "index.html").read_text(encoding="utf-8")


def test_the_tip_has_steps_for_iphone_and_android():
    assert '<div id="home-screen-modal" class="modal-overlay" hidden>' in PAGE
    assert "Add to Home Screen" in PAGE[PAGE.index('id="home-screen-ios"'):]
    assert "Add to Home screen" in PAGE[PAGE.index('id="home-screen-android"'):]


def test_only_on_a_phone_or_tablet_and_only_the_first_time():
    script = PAGE[PAGE.index('const SEEN = "lgd-home-screen-tip";'):]
    assert "if (!(ios || android) || installed) return;" in script
    assert "if (localStorage.getItem(SEEN)) return;" in script
    assert re.search(r"localStorage\.setItem\(SEEN,", script)
    assert '"(display-mode: standalone)"' in script


def test_logout_shows_on_the_home_page_only_when_signed_in():
    """The user, 2026-10-02: "logout button on home screen"."""
    assert '<button type="button" id="home-logout" hidden>Logout</button>' in PAGE
    assert '<script src="shared/auth.js"></script>' in PAGE
    script = PAGE[PAGE.index('const button = document.getElementById("home-logout");') - 400:]
    assert "if (!session) return;" in script
    assert "await auth.signOut();" in script
