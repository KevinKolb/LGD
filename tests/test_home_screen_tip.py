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


def test_login_and_logout_sit_in_the_home_page_header():
    """The user, 2026-10-02: "logout button on home screen", then the
    header of the other pages, minus Home - Login/Logout comes with it."""
    assert '<header data-no-home>' in PAGE
    assert 'id="home-logout"' not in PAGE
    for script in ("shared/auth.js", "shared/account.js", "shared/home.js"):
        assert f'<script src="{script}"></script>' in PAGE
