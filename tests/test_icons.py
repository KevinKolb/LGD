"""The little house is the icon everywhere, iPhone home screen included
(the user, 2026-09-29), and the home page's title bar reads Residential Guide."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = sorted(
    [p for p in ROOT.glob("*.html")] + [p for p in ROOT.glob("*/*.html") if p.parent.name != "_saved"]
    + list((ROOT / "documents" / "print").glob("*.html"))
)


@pytest.mark.parametrize("page", PAGES, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_page_uses_the_house(page) -> None:
    text = page.read_text(encoding="utf-8")
    depth = len(page.relative_to(ROOT).parts) - 1
    prefix = "../" * depth
    assert f'<link rel="icon" href="{prefix}favicon.ico?v=2" sizes="any">' in text
    assert f'<link rel="icon" href="{prefix}shared/icons/house.svg" type="image/svg+xml">' in text
    assert f'<link rel="apple-touch-icon" href="{prefix}shared/icons/apple-touch-icon.png">' in text
    assert '<meta name="apple-mobile-web-app-title" content="Residential Guide">' in text


def test_the_icon_files_exist() -> None:
    for name in ("house.svg", "apple-touch-icon.png", "icon-192.png", "icon-512.png"):
        assert (ROOT / "shared" / "icons" / name).is_file()
    assert (ROOT / "shared" / "manifest.webmanifest").is_file()


def test_the_home_page_title_bar() -> None:
    # Residential Guide since 2026-10-03 (the user; momandpop.com before); the home-screen name stays.
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "<title>Residential Guide</title>" in page
    assert '<meta name="apple-mobile-web-app-title" content="Residential Guide">' in page
