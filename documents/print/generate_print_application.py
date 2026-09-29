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

# A block this short (not counting its underscores) is a row of form
# fields, laid out full width; a longer one is prose that happens to hold a
# blank, like the holding deposit's "$____".
ROW_MAX_TEXT = 110

EXTRA_CSS = """
  /* A row of form fields: full page width, the blanks stretching to fill
     it in proportion to their underscores in application.md, and 3/8in
     tall - room to write, without spreading the form over extra pages. */
  p.field.row {
    display: flex;
    align-items: flex-end;
    gap: 0.07in;
    min-height: 0.375in;
    margin: 0;
    line-height: 1.2;
    text-align: left;
    page-break-inside: avoid;
    break-inside: avoid;
  }
  p.field.row .label { flex: 0 0 auto; white-space: nowrap; }
  p.field.row .blank + .label { margin-left: 0.12in; }
  p.field.row .blank.fixed {
    flex-basis: 0;
    flex-shrink: 1;
    min-width: 0.35in;
    height: 1.2em;
  }
  p.field.row .blank.fixed.filled {
    border-bottom: 1px solid #000;
    text-decoration: none;
    white-space: nowrap;
    overflow: hidden;
  }
  p.field {
    text-align: left;
    page-break-inside: avoid;
    break-inside: avoid;
  }
  p.label-line { margin: 0.9em 0 0; }
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


def blank_id(label: str) -> str:
    """The id for the blank after this label, if the picker fills it."""
    if label.endswith(PREMISES_LEAD):
        return ' id="premises"'
    for lead, _, target in OFFICE_FIELDS:
        if label.endswith(lead):
            return f' id="{target}"'
    return ""


def is_row(block: str) -> bool:
    flat = flatten(block)
    return bool(BLANK.search(flat)) and len(BLANK.sub("", flat)) <= ROW_MAX_TEXT


def render_row(block: str) -> str:
    """A row of fields: each label a fixed box, each blank a flexible one
    whose share of the leftover width is its underscore count."""
    cells = []
    label = ""
    for piece in re.split(r"(_{2,})", flatten(block)):
        if BLANK.fullmatch(piece):
            cells.append(f'<span class="blank fixed"{blank_id(label)} '
                         f'style="flex-grow: {len(piece)}"></span>')
        elif piece.strip():
            label = piece.strip()
            cells.append(f'<span class="label">{lease.convert_bold(html.escape(label))}</span>')
    return "".join(cells)


def render_list(block: str) -> str:
    items = re.split(r"\n(?=- )", block)
    rows = "\n".join(f"  <li>{render_text(item[2:])}</li>" for item in items)
    return f'<ul class="steps">\n{rows}\n</ul>'


def render_body(source_text: str) -> str:
    """The form itself, without the page around it - shared by this page
    and the combined one (generate_print_packet.py)."""
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
        elif is_row(block):
            parts.append(f'<p{tag} class="field row">{render_row(block)}</p>')
        elif BLANK.search(block) or CHECKBOX in block:
            parts.append(f'<p{tag} class="field">{render_text(block)}</p>')
        elif flatten(block).endswith(":") and len(flatten(block)) <= ROW_MAX_TEXT:
            # A short lead-in to the rows below it, like "Other persons who
            # will occupy this apartment with you:".
            parts.append(f'<p{tag} class="label-line">{render_text(block)}</p>')
        else:
            parts.append(f"<p{tag}>{render_text(block)}</p>")
    body = "\n".join(parts)
    if body.count('id="premises"') != 1:
        raise SystemExit(f'{SOURCE.name} needs exactly one "{PREMISES_LEAD}___" blank for the picker.')
    for lead, _, target in OFFICE_FIELDS:
        if body.count(f'id="{target}"') != 1:
            raise SystemExit(f'{SOURCE.name} needs exactly one "{lead}___" blank.')
    return body


# The popup's optional boxes for this document, as (label, blank id).
PICKER_FIELDS = tuple((label, target) for _, label, target in OFFICE_FIELDS)


def generate(source_text: str) -> str:
    head = lease.render_head(lease.COMPANY_NAME, TITLE, SUBTITLE).replace("</style>", EXTRA_CSS + "</style>", 1)
    return head + render_body(source_text) + "\n" + FOOTER_NOTE + lease.render_picker_footer("application", PICKER_FIELDS)


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"{SOURCE} does not exist.")
    OUTPUT.write_text(generate(SOURCE.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"Wrote {OUTPUT} from {SOURCE}.")


if __name__ == "__main__":
    main()
