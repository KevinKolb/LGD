#!/usr/bin/env python3
"""Generate a self-contained, print-ready HTML security deposit agreement
from `documents/security_deposit.md`.

`documents/security_deposit.md` is the file anyone edits; this script derives
the printable output from it, the same way `generate_print_lease.py` derives
the lease - and it borrows that script's header, embedded font and apartment
picker, so the two documents look and behave alike. Picking an apartment
fills in "As Security Deposit for ___" from `documents/properties.json`.

Usage:
    python documents/print/generate_print_deposit.py
"""
from __future__ import annotations

import html
import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
SOURCE = REPO_ROOT / "documents" / "security_deposit.md"
OUTPUT = HERE / "security_deposit_print.html"

# Hardcoded LGD: a 2.0 migration (see CLAUDE.md). The user's wording for this
# header, 2026-09-28 - note it differs from the lease's COMPANY_NAME.
COMPANY_NAME = "LGD PROPERTIES, INC"
TITLE = "Security Deposit Agreement"
SUBTITLE = "SECURITY DEPOSIT AGREEMENT"


def _load_lease_generator():
    spec = importlib.util.spec_from_file_location("generate_print_lease", HERE / "generate_print_lease.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


lease = _load_lease_generator()

BLANK = re.compile(r"_{2,}")
LIST_ITEM = re.compile(r"^(\d+)\.\s+", re.M)
SIGNATURE = re.compile(r"^(Lessee|Lessor|Lessor/Agent)_{2,}$")
HEADING = re.compile(r"^\*\*(.+)\*\*$")
PREMISES_LEAD = "As Security Deposit for"

EXTRA_CSS = """
  p.fill { text-align: left; }
  p.conditions-heading {
    margin-top: 1.2em;
    font-weight: bold;
    font-style: italic;
    text-decoration: underline;
    text-align: left;
    page-break-after: avoid;
    break-after: avoid;
  }
  ol.conditions { margin: 0 0 0.85em; padding-left: 2em; }
  ol.conditions li { margin: 0 0 0.3em; text-align: justify; }
"""

FOOTER_NOTE = """
<div class="footer-note">
  This is a security deposit agreement generated from
  <code>documents/security_deposit.md</code> by
  <code>documents/print/generate_print_deposit.py</code>. It will not appear on a
  printed copy (hidden in print styles). Regenerate after editing
  <code>documents/security_deposit.md</code> or <code>documents/properties.json</code>.
</div>"""


def body_blocks(source_text: str) -> list[str]:
    """Blank-line-separated blocks, minus the title, rules and page markers
    that only exist to keep the source readable."""
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
    """Escaped text with each run of underscores turned into a blank. The
    blank after "As Security Deposit for" is the premises, which the
    apartment picker fills in."""
    escaped = html.escape(flatten(text))

    def blank(match: re.Match) -> str:
        width = "medium" if len(match.group(0)) >= 40 else "word"
        before = escaped[:match.start()]
        if before.rstrip().endswith(PREMISES_LEAD):
            return f'<span class="blank {width}" id="premises"></span>'
        return f'<span class="blank {width}"></span>'

    return BLANK.sub(blank, escaped)


# Conditions whose wording depends on the address, keyed by number, and the
# lease option group that picks their version - the same groups, values and
# picker as the lease, so a deposit always matches its lease. In
# security_deposit.md such a condition reads "6. (A) ... (B) ...".
ITEM_OPTIONS = {
    6: "walls",   # matches lease §20 WALLS
    9: "yard",    # matches lease §17 PATIO/YARD
}
VERSION_SPLIT = re.compile(r"(?:^|\s)\(([A-Z])\) ")


def render_item(number: int, text: str) -> str:
    """One condition. A versioned one becomes one span per version, tagged
    like the lease's, so the picker shows only the address's version."""
    text = flatten(text)
    group = ITEM_OPTIONS.get(number)
    has_versions = text.startswith("(A) ")
    if bool(group) != has_versions:
        raise SystemExit(
            f"Condition {number} in {SOURCE.name}: ITEM_OPTIONS and its (A)/(B) "
            "versions disagree - has a condition been renumbered?"
        )
    if not group:
        return render_text(text)
    pieces = VERSION_SPLIT.split(text)[1:]  # [letter, text, letter, text, ...]
    return " ".join(
        f'<span data-option="{group}={letter}">{lease.version_label(letter)}{render_text(body)}</span>'
        for letter, body in zip(pieces[::2], pieces[1::2])
    )


def render_list(block: str) -> tuple[str, list[int]]:
    starts = [m.start() for m in LIST_ITEM.finditer(block)]
    items = [block[a:b] for a, b in zip(starts, starts[1:] + [len(block)])]
    numbers = [int(LIST_ITEM.match(item).group(1)) for item in items]
    if numbers != list(range(numbers[0], numbers[0] + len(numbers))):
        raise SystemExit(f"Numbered list in {SOURCE.name} skips or repeats: {numbers}")
    rows = "\n".join(
        f"  <li>{render_item(number, LIST_ITEM.sub('', item, count=1))}</li>"
        for number, item in zip(numbers, items)
    )
    return f'<ol class="conditions" start="{numbers[0]}">\n{rows}\n</ol>', numbers


def render_signatures(labels: list[str]) -> str:
    rows = "\n".join(f'<div class="sig-line">{html.escape(label)}</div>' for label in labels)
    return f'<div class="signature-block">\n{rows}\n</div>'


def generate(source_text: str) -> str:
    parts: list[str] = []
    list_numbers: list[int] = []
    signatures: list[str] = []

    def flush_signatures() -> None:
        # Signature lines are bound to the paragraph they sign, as in the
        # lease: one break-inside: avoid unit, so they never strand alone.
        if not signatures:
            return
        signed = parts.pop() if parts else ""
        parts.append('<div class="execution-block">\n' + signed + "\n"
                     + render_signatures(signatures) + "\n</div>")
        signatures.clear()

    for block in body_blocks(source_text):
        signature = SIGNATURE.match(block)
        if signature:
            signatures.append(signature.group(1))
            continue
        flush_signatures()
        heading = HEADING.match(block)
        if heading:
            parts.append(f'<p class="conditions-heading">{html.escape(heading.group(1))}</p>')
        elif LIST_ITEM.match(block):
            rendered, numbers = render_list(block)
            list_numbers += numbers
            parts.append(rendered)
        else:
            css = ' class="fill"' if BLANK.search(block) else ""
            parts.append(f"<p{css}>{render_text(block)}</p>")
    flush_signatures()

    body = "\n".join(parts)
    if body.count('id="premises"') != 1:
        raise SystemExit(f'{SOURCE.name} needs exactly one "{PREMISES_LEAD} ___" blank for the premises.')
    if list_numbers != list(range(1, len(list_numbers) + 1)):
        raise SystemExit(f"The conditions in {SOURCE.name} do not run 1..N: {list_numbers}")
    if "signature-block" not in body:
        raise SystemExit(f"No signature lines found in {SOURCE.name}.")
    for group in ITEM_OPTIONS.values():
        for value in sorted(lease.OPTION_GROUPS[group]):
            if f'data-option="{group}={value}"' not in body:
                raise SystemExit(f"{SOURCE.name} has no {group} version {value}, which the lease has.")

    head = lease.render_head(COMPANY_NAME, TITLE, SUBTITLE).replace("</style>", EXTRA_CSS + "</style>", 1)
    return head + body + "\n" + FOOTER_NOTE + lease.render_picker_footer("security deposit")


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"{SOURCE} does not exist.")
    output = generate(SOURCE.read_text(encoding="utf-8"))
    OUTPUT.write_text(output, encoding="utf-8")
    print(f"Wrote {OUTPUT} from {SOURCE}.")


if __name__ == "__main__":
    main()
