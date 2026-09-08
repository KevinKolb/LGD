#!/usr/bin/env python3
"""Generate `manager/legal_research.html` from `manager/LEGAL_RESEARCH.md`.

Same shape as `documents/print/generate_print_lease.py`: the markdown file stays the
one thing anyone edits, and this derives a page from it. The research log is
appended to as clauses change, and a manager should be able to read it as an
ordinary page on this site rather than being sent to a code host to view a
raw file.

Usage:
    python manager/generate_legal_research.py

No third-party dependencies. This is not a general markdown renderer - it
handles exactly the constructs the log actually uses, and raises on anything
it does not recognise rather than silently dropping it. If a new construct
turns up (a table, a fenced code block), it fails loudly and gets added here
deliberately.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "manager" / "LEGAL_RESEARCH.md"
OUTPUT = REPO_ROOT / "manager" / "legal_research.html"

BULLET = re.compile(r"^- (.*)$")
NUMBERED = re.compile(r"^(\d+)\. (.*)$")
CONTINUATION = re.compile(r"^ {2,}(\S.*)$")
HEADING = re.compile(r"^(#{1,3}) (.*)$")
RULE = re.compile(r"^---\s*$")

# Constructs this converter does not handle. Better to stop than to emit a
# page that quietly loses a table or a code block.
UNSUPPORTED = {
    "a fenced code block": re.compile(r"^```"),
    "a table": re.compile(r"^\|"),
    "a blockquote": re.compile(r"^> "),
}


def inline(text: str) -> str:
    """Escape, then apply the inline markup the log uses.

    Order matters: code spans are extracted first so their contents are not
    then read as bold or italic, and links are turned into anchors last so
    an earlier pass cannot mangle a URL.
    """
    text = html.escape(text, quote=False)

    # Code spans are held aside while the rest is formatted.
    held: list[str] = []

    def hold(match: re.Match) -> str:
        held.append(f"<code>{match.group(1)}</code>")
        return f"\x00{len(held) - 1}\x00"

    text = re.sub(r"`([^`]+)`", hold, text)

    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)

    # <https://...> first, then any bare URL left over.
    text = re.sub(
        r"&lt;(https?://[^&\s]+)&gt;",
        r'<a href="\1" target="_blank" rel="noopener">\1</a>',
        text,
    )
    text = re.sub(
        r'(?<!["=>])\b(https?://[^\s<)]+[^\s<).,])',
        r'<a href="\1" target="_blank" rel="noopener">\1</a>',
        text,
    )

    for index, code in enumerate(held):
        text = text.replace(f"\x00{index}\x00", code)
    return text


def convert(markdown: str) -> tuple[str, str]:
    """Return (page title, body HTML)."""
    lines = markdown.splitlines()
    for number, line in enumerate(lines, 1):
        for label, pattern in UNSUPPORTED.items():
            if pattern.match(line):
                raise SystemExit(
                    f"{SOURCE.name} line {number} uses {label}, which "
                    f"{Path(__file__).name} does not handle yet. Add it there "
                    f"rather than leaving it silently dropped:\n  {line!r}"
                )

    title = ""
    out: list[str] = []
    paragraph: list[str] = []
    items: list[list[str]] = []
    list_tag = ""

    def flush_paragraph() -> None:
        if paragraph:
            out.append(f"<p>{inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_list() -> None:
        nonlocal list_tag
        if items:
            out.append(f"<{list_tag}>")
            for item in items:
                out.append(f"  <li>{inline(' '.join(item))}</li>")
            out.append(f"</{list_tag}>")
            items.clear()
        list_tag = ""

    for line in lines:
        if not line.strip():
            # A blank line ends a paragraph, but NOT a list: the log puts a
            # blank line between numbered sources, and closing the list there
            # would restart every entry at "1.". The list is closed instead by
            # whatever comes next that is not another item - a paragraph,
            # heading or rule, all of which flush it themselves.
            flush_paragraph()
            continue

        heading = HEADING.match(line)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            text = heading.group(2)
            if level == 1 and not title:
                title = text
                continue  # The <h1> is rendered by the page header instead.
            out.append(f"<h{level}>{inline(text)}</h{level}>")
            continue

        if RULE.match(line):
            flush_paragraph()
            flush_list()
            out.append("<hr>")
            continue

        bullet = BULLET.match(line)
        numbered = NUMBERED.match(line)
        if bullet or numbered:
            flush_paragraph()
            wanted = "ul" if bullet else "ol"
            if list_tag and list_tag != wanted:
                flush_list()
            list_tag = wanted
            items.append([(bullet or numbered).group(1 if bullet else 2)])
            continue

        continuation = CONTINUATION.match(line)
        if continuation and items:
            # An indented line under a list item belongs to that item.
            items[-1].append(continuation.group(1))
            continue

        flush_list()
        paragraph.append(line.strip())

    flush_paragraph()
    flush_list()
    return title, "\n".join(out)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="../favicon.ico?v=1">
<link rel="stylesheet" href="../shared/site.css">
<title>{title}</title>
<style>
  :root {{
    --bg: #f6f5f2;
    --panel: #ffffff;
    --ink: #1c1c1a;
    --muted: #6b6a66;
    --line: #dcdad4;
    --accent: #1f5d4c;
    --accent-ink: #ffffff;
    --radius: 8px;
  }}
  html.theme-orange {{ --accent: #d2601a; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }}
  header {{
    background: var(--accent);
    color: var(--accent-ink);
    padding: 18px 24px;
  }}
  header h1 {{ margin: 0; font-size: 18px; letter-spacing: .01em; }}
  header p {{ margin: 4px 0 0; opacity: .8; font-size: 13px; }}
  main {{
    width: 100%;
    max-width: 820px;
    margin: 0 auto;
    padding: 24px;
  }}
  article {{
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    padding: 28px 32px;
  }}
  h2 {{
    margin: 32px 0 10px;
    font-size: 17px;
    line-height: 1.3;
    color: var(--accent);
    padding-top: 20px;
    border-top: 1px solid var(--line);
  }}
  article > h2:first-child {{ margin-top: 0; padding-top: 0; border-top: 0; }}
  h3 {{ margin: 24px 0 8px; font-size: 15px; }}
  p {{ margin: 0 0 14px; }}
  ul, ol {{ margin: 0 0 16px; padding-left: 24px; }}
  li {{ margin-bottom: 8px; }}
  code {{
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 13px;
    background: #f0efea;
    padding: 1px 5px;
    border-radius: 4px;
  }}
  a {{ color: var(--accent); overflow-wrap: anywhere; }}
  hr {{ border: 0; border-top: 1px solid var(--line); margin: 28px 0; }}
  .source-note {{
    margin: 0 0 20px;
    color: var(--muted);
    font-size: 13px;
  }}
</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <p>Lower Garden District Properties LLC</p>
</header>

<main>
  <article>
{body}
  </article>
  <p class="source-note">
    Generated from <code>manager/LEGAL_RESEARCH.md</code> by
    <code>manager/generate_legal_research.py</code> &mdash; edit the markdown,
    not this page.
  </p>
</main>

<script src="../shared/footer.js"></script>
</body>
</html>
"""


def generate(markdown: str) -> str:
    title, body = convert(markdown)
    return PAGE.format(title=html.escape(title or "Legal Research"), body=body)


def main() -> None:
    OUTPUT.write_text(generate(SOURCE.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"Wrote {OUTPUT} from {SOURCE}.")


if __name__ == "__main__":
    main()
