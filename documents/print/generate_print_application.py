#!/usr/bin/env python3
"""Generate a self-contained, print-ready HTML rental application from
`documents/application.md`.

The same treatment as the lease and the security deposit: `application.md`
is the file anyone edits, and this derives the printable form from it with
the lease generator's header, embedded font and apartment picker - picking
an apartment fills in "Address of property" from `documents/properties.json`.

Usage:
    python documents/print/generate_print_application.py
"""
from __future__ import annotations

import html
import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
SOURCE = REPO_ROOT / "documents" / "application.md"
OUTPUT = HERE / "application_print.html"

TITLE = "Application for Apartment"
SUBTITLE = "APPLICATION FOR APARTMENT"
PREMISES_LEAD = "Address of property"
# Blanks are drawn proportional to their underscores in application.md, so
# the form's layout is edited there, by eye, rather than in this script.
INCHES_PER_UNDERSCORE = 0.07


def _load_lease_generator():
    spec = importlib.util.spec_from_file_location("generate_print_lease", HERE / "generate_print_lease.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


lease = _load_lease_generator()

BLANK = re.compile(r"_{2,}")
CHECKBOX = "[ ]"

# Blanks the office fills in, offered as optional boxes in the popup: the
# label printed before each blank, the popup's label, and the blank's id.
OFFICE_FIELDS = (
    ("Monthly rental rate", "Monthly rental rate", "field-rent"),
    ("Term of lease", "Term of lease", "field-term"),
    ("Security deposit $", "Security deposit $", "field-deposit"),
)

# A block beginning "(parking=limited) " prints on every blank application
# but, once an apartment is picked, only where that option applies - the
# same data-option tag the lease uses. The vehicles section is one: only an
# address with parking needs its vehicles listed (lease §21).
CONDITION = re.compile(r"^\((\w+)=([\w-]+)\) ")

EXTRA_CSS = """
  p.field {
    margin: 0 0 0.62em;
    text-align: left;
    line-height: 1.9;
    page-break-inside: avoid;
    break-inside: avoid;
  }
  .blank.fixed { min-width: 0; }
  /* The form's labels run straight into their blanks; a filled-in address
     needs a gap the empty line did not. */
  .blank.fixed.filled { margin-left: 0.3em; margin-right: 0.6em; }
  .box {
    display: inline-block;
    width: 0.8em;
    height: 0.8em;
    border: 1px solid #000;
    vertical-align: -0.05em;
  }
  ul.steps { margin: 0 0 0.85em; padding-left: 1.4em; }
  ul.steps li { margin: 0 0 0.3em; text-align: justify; }
"""

FOOTER_NOTE = """
<div class="footer-note">
  This is a rental application generated from <code>documents/application.md</code>
  by <code>documents/print/generate_print_application.py</code>. It will not appear on
  a printed copy (hidden in print styles). Regenerate after editing
  <code>documents/application.md</code> or <code>documents/properties.json</code>.
</div>"""


def body_blocks(source_text: str) -> list[str]:
    blocks = []
    for block in re.split(r"\n\s*\n", source_text.strip()):
        stripped = block.strip()
        if (not stripped or stripped.startswith("# ") or stripped == "---"
                or re.match(r"^## PAGE \d+$", stripped)):
            continue
        blocks.append(stripped)
    return blocks


def flatten(text: str) -> str:
    return re.sub(r"[ \t]*\n[ \t]*", " ", text).strip()


def render_text(text: str) -> str:
    """Escaped text: **bold**, "[ ]" as a box to tick, and each run of
    underscores as a blank as wide as the run. The blank after "Address of
    property" is the premises, which the apartment picker fills in."""
    escaped = lease.convert_bold(html.escape(flatten(text)))
    escaped = escaped.replace(html.escape(CHECKBOX), '<span class="box"></span>')

    def blank(match: re.Match) -> str:
        width = f"{len(match.group(0)) * INCHES_PER_UNDERSCORE:.2f}in"
        before = escaped[:match.start()]
        ident = ""
        if before.endswith(PREMISES_LEAD):
            ident = ' id="premises"'
        for lead, _, target in OFFICE_FIELDS:
            if before.endswith(html.escape(lead)):
                ident = f' id="{target}"'
        return f'<span class="blank fixed"{ident} style="min-width: {width}"></span>'

    return BLANK.sub(blank, escaped)


def render_list(block: str) -> str:
    items = re.split(r"\n(?=- )", block)
    rows = "\n".join(f"  <li>{render_text(item[2:])}</li>" for item in items)
    return f'<ul class="steps">\n{rows}\n</ul>'


def generate(source_text: str) -> str:
    parts = []
    for block in body_blocks(source_text):
        tag = ""
        condition = CONDITION.match(block)
        if condition:
            group, value = condition.groups()
            if value not in lease.OPTION_GROUPS.get(group, ()):
                raise SystemExit(f"{SOURCE.name}: unknown condition ({group}={value}).")
            tag = f' data-option="{group}={value}"'
            block = block[condition.end():]
        if block.startswith("- "):
            parts.append(render_list(block))
        elif BLANK.search(block) or CHECKBOX in block:
            parts.append(f'<p{tag} class="field">{render_text(block)}</p>')
        else:
            parts.append(f"<p{tag}>{render_text(block)}</p>")
    body = "\n".join(parts)
    if body.count('id="premises"') != 1:
        raise SystemExit(f'{SOURCE.name} needs exactly one "{PREMISES_LEAD}___" blank for the picker.')
    for lead, _, target in OFFICE_FIELDS:
        if body.count(f'id="{target}"') != 1:
            raise SystemExit(f'{SOURCE.name} needs exactly one "{lead}___" blank.')
    head = lease.render_head(lease.COMPANY_NAME, TITLE, SUBTITLE).replace("</style>", EXTRA_CSS + "</style>", 1)
    fields = tuple((label, target) for _, label, target in OFFICE_FIELDS)
    return head + body + "\n" + FOOTER_NOTE + lease.render_picker_footer("application", fields)


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"{SOURCE} does not exist.")
    OUTPUT.write_text(generate(SOURCE.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"Wrote {OUTPUT} from {SOURCE}.")


if __name__ == "__main__":
    main()
