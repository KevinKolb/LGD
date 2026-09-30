#!/usr/bin/env python3
"""Generate a printable Plaster Walls Addendum for a lease signed before §20
WALLS existed.

The rules are not written here: they are lease §20 WALLS, version (B) -
read out of `documents/lease.md` on every run, so the addendum and the lease
can never say different things about plaster walls. The premises are the
address in `documents/properties.json` whose walls are "B".

Usage:
    python documents/print/generate_print_addendum.py
"""
from __future__ import annotations

import html
import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
LEASE_SOURCE = REPO_ROOT / "documents" / "lease.md"
OUTPUT = HERE / "plaster_walls_addendum_print.html"

TITLE = "Plaster Walls Addendum"
SUBTITLE = "PLASTER WALLS ADDENDUM"
WALLS_TITLE = "WALLS"
VERSION = "B"
SIGNERS = ["Lessor/Agent", "Lessee", "Lessee", "Lessee"]


def _load_lease_generator():
    spec = importlib.util.spec_from_file_location("generate_print_lease", HERE / "generate_print_lease.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


lease = _load_lease_generator()

EXTRA_CSS = """
  p.incorporation { text-align: left; }
"""

FOOTER_NOTE = """<div class="footer-note">
  Generated from lease &sect;20 WALLS, version (B), in <code>documents/lease.md</code>
  by <code>documents/print/generate_print_addendum.py</code>. It will not appear on a
  printed copy. Regenerate after editing <code>documents/lease.md</code> or
  <code>documents/properties.json</code>.
</div>"""

AUTO_PRINT = """
<script>
  // As with the lease: print once the embedded font is ready, unless opened
  // with #view to read on screen. No picker here, so the floating Print
  // button (lease.DOC_BUTTONS) shows straight away.
  document.getElementById("print-button").hidden = false;
  window.addEventListener("load", function () {
    if (window.location.hash === "#view") { return; }
    var fontsReady = (document.fonts && document.fonts.ready) ? document.fonts.ready : Promise.resolve();
    fontsReady.then(function () { setTimeout(function () { window.print(); }, 150); });
  });
</script>
</body>
</html>
"""


def plaster_premises() -> str:
    """The one address whose walls are plaster, written out in full."""
    plaster = [p for p in lease.load_properties()["properties"] if p["lease_options"]["walls"] == VERSION]
    if len(plaster) != 1:
        raise SystemExit(
            f"Expected exactly one plaster-walls address in properties.json, found {len(plaster)}: "
            "the addendum names one premises."
        )
    prop = plaster[0]
    if prop["units"]:
        raise SystemExit(f"{prop['address']} has units; the addendum needs a unit blank for that.")
    return f"{prop['address']}, {prop.get('city', 'New Orleans')}, {prop.get('state', 'LA')} {prop.get('zip', '')}".strip()


def walls_version_blocks(lease_text: str) -> list[str]:
    """The paragraphs of lease §20 WALLS, version (B), without its label."""
    body_source, _ = lease.split_source(lease_text)
    blocks = lease.extract_body_blocks(body_source)
    start = next((i for i, b in enumerate(blocks)
                  if (m := lease.SECTION_TITLE.match(b)) and m.group(1) == WALLS_TITLE), None)
    if start is None:
        raise SystemExit(f"No section titled {WALLS_TITLE!r} in documents/lease.md.")
    section = [blocks[start]]
    for block in blocks[start + 1:]:
        if lease.STARTS_NEW_SECTION.match(block):
            break
        section.append(block)
    first = next((i for i, b in enumerate(section) if b.startswith(f"({VERSION}) ")), None)
    if first is None:
        raise SystemExit(f"Section {WALLS_TITLE} has no version ({VERSION}).")
    version = [section[first][len(f"({VERSION}) "):]]
    for block in section[first + 1:]:
        if lease.VERSION_START.match(block):
            break
        version.append(block)
    return version


def render_block(block: str) -> str:
    text = lease.convert_bold(html.escape(block))
    css = ' class="bullet"' if block.startswith("• ") else ""
    return f"<p{css}>{text}</p>"


def render_signatures() -> str:
    rows = "\n".join(lease.signature_row(who) for who in SIGNERS)
    return f'<div class="signature-block">\n{rows}\n</div>'


def generate(lease_text: str) -> str:
    premises = html.escape(plaster_premises())
    date_blank = '<span class="blank word"></span>'
    year_blank = '<span class="blank tiny"></span>'
    name_blank = '<span class="blank medium"></span>'
    incorporation = (
        '<p class="incorporation">This Addendum is made part of and incorporated into the '
        f"Lease Agreement dated {date_blank}, 20{year_blank}, between {name_blank} (Lessor) "
        f"and {name_blank} (Lessee) for the premises located at "
        f"<strong><u>{premises}</u></strong>. Where this "
        "Addendum and the Lease Agreement differ, this Addendum controls. All other terms of "
        "the Lease Agreement remain in full force and effect.</p>"
    )
    rules = "\n".join(render_block(b) for b in walls_version_blocks(lease_text))
    closing = ("<p>By signing below, Lessee acknowledges having read, understood, and agreed "
               "to this Addendum.</p>")
    head = lease.render_head(lease.COMPANY_NAME, TITLE, SUBTITLE).replace("</style>", EXTRA_CSS + "</style>", 1)
    return (head + incorporation + "\n" + rules + "\n"
            + '<div class="execution-block">\n' + closing + "\n" + render_signatures() + "\n</div>"
            + "\n" + FOOTER_NOTE + lease.DOC_BUTTONS + AUTO_PRINT)


def main() -> None:
    output = generate(LEASE_SOURCE.read_text(encoding="utf-8"))
    OUTPUT.write_text(output, encoding="utf-8")
    print(f"Wrote {OUTPUT} from {LEASE_SOURCE}.")


if __name__ == "__main__":
    main()
