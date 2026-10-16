#!/usr/bin/env python3
"""Build the standalone HTML defence deck from FYP-defense-deck.md.

Usage:
    python docs/build_deck.py            # writes docs/FYP-defense-deck.html

Stdlib only, no network. The Markdown deck is the single source of truth; this
script renders the subset of Markdown it actually uses (headings, lists, tables,
fenced code, blockquotes, bold/inline-code, HTML-comment speaker notes) into a
self-contained slide viewer: arrow keys / click to navigate, `n` toggles
speaker notes, Ctrl+P prints one slide per landscape page (use "Save as PDF").
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent
SOURCE = DOCS / "FYP-defense-deck.md"
TARGET = DOCS / "FYP-defense-deck.html"


# --------------------------------------------------------------------------- #
# Markdown subset -> HTML
# --------------------------------------------------------------------------- #
def inline(text: str) -> str:
    """Escape then re-apply the inline markup used in the deck."""
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", out)
    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', out)
    return out


def _is_table_row(line: str) -> bool:
    return line.strip().startswith("|") and line.strip().endswith("|")


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def fixup_cells(row: list[str], width: int) -> list[str]:
    """Pad/trim a table row so header and body line up."""
    if len(row) < width:
        row = row + [""] * (width - len(row))
    return row[:width]


def render_blocks(lines: list[str]) -> str:
    """Render a list of markdown lines (one slide body) to HTML."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # fenced code ------------------------------------------------------
        if stripped.startswith("```"):
            i += 1
            buf: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1  # closing fence
            out.append("<pre><code>%s</code></pre>" % html.escape("\n".join(buf)))
            continue

        # heading ----------------------------------------------------------
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            i += 1
            continue

        # table ------------------------------------------------------------
        if _is_table_row(line) and i + 1 < len(lines) and re.match(
            r"^\|[\s:|-]+\|$", lines[i + 1].strip()
        ):
            header = _split_row(line)
            width = len(header)
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and _is_table_row(lines[i]):
                rows.append(fixup_cells(_split_row(lines[i]), width))
                i += 1
            head_html = "".join(f"<th>{inline(c)}</th>" for c in header)
            body_html = "".join(
                "<tr>%s</tr>" % "".join(f"<td>{inline(c)}</td>" for c in r) for r in rows
            )
            out.append(
                f'<table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table>'
            )
            continue

        # blockquote -------------------------------------------------------
        if stripped.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append("<blockquote>%s</blockquote>" % "<br>".join(inline(b) for b in buf))
            continue

        # lists ------------------------------------------------------------
        list_match = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if list_match:
            ordered = list_match.group(2).endswith(".")
            tag = "ol" if ordered else "ul"
            items: list[tuple[int, str]] = []
            while i < len(lines):
                m2 = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[i])
                if not m2:
                    if not lines[i].strip():
                        # keep a blank line only if the list continues after it
                        nxt = lines[i + 1] if i + 1 < len(lines) else ""
                        if re.match(r"^\s*([-*]|\d+\.)\s+", nxt):
                            i += 1
                            continue
                    break
                indent = len(m2.group(1))
                items.append((indent // 2, m2.group(3)))
                i += 1
            # flatten one level of nesting (the deck only uses it lightly)
            parts = []
            depth = 0
            open_lists: list[str] = []
            for lvl, text in items:
                while depth < lvl:
                    parts.append(f"<{tag}>")
                    open_lists.append(tag)
                    depth += 1
                while depth > lvl:
                    parts.append(f"</{open_lists.pop()}>")
                    depth -= 1
                parts.append(f"<li>{inline(text)}</li>")
            while open_lists:
                parts.append(f"</{open_lists.pop()}>")
            if not parts or not parts[0].startswith(f"<{tag}>"):
                parts.insert(0, f"<{tag}>")
                parts.append(f"</{tag}>")
            out.append("".join(parts))
            continue

        # paragraph --------------------------------------------------------
        buf = []
        while i < len(lines) and lines[i].strip() and not re.match(
            r"^(\s*([-*]|\d+\.)\s+|#{1,6}\s+|>|\|)", lines[i].strip()
        ) and not lines[i].strip().startswith("```"):
            buf.append(lines[i].strip())
            i += 1
        if buf:
            out.append("<p>%s</p>" % inline(" ".join(buf)))
    return "\n".join(out)


def split_slides(text: str) -> list[dict]:
    """Split the Marp source into slides, extracting HTML comments as notes."""
    lines = text.splitlines()

    # strip YAML front matter
    if lines and lines[0].strip() == "---":
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                lines = lines[idx + 1:]
                break

    raw_slides: list[list[str]] = [[]]
    in_fence = False
    for line in lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.strip() == "---":
            raw_slides.append([])
            continue
        raw_slides[-1].append(line)

    slides = []
    for body in raw_slides:
        if not any(l.strip() for l in body):
            continue
        notes: list[str] = []
        kept: list[str] = []
        in_comment = False
        buf: list[str] = []
        for line in body:
            if in_comment:
                if "-->" in line:
                    in_comment = False
                    buf.append(line.split("-->")[0])
                    notes.append("\n".join(buf).strip())
                    buf = []
                else:
                    buf.append(line)
                continue
            if "<!--" in line:
                head, _, tail = line.partition("<!--")
                if "-->" in tail:
                    notes.append(tail.split("-->")[0].strip())
                    if head.strip():
                        kept.append(head)
                else:
                    in_comment = True
                    buf = [tail]
                    if head.strip():
                        kept.append(head)
                continue
            kept.append(line)
        body_html = render_blocks(kept)
        note_text = "\n".join(n for n in notes if n)
        if not body_html:  # a slide that is only a comment belongs to the previous one
            if slides and note_text:
                slides[-1]["notes"] = "\n".join(filter(None, [slides[-1]["notes"], note_text]))
            continue
        slides.append({"body": body_html, "notes": note_text})
    return slides


# --------------------------------------------------------------------------- #
# HTML shell
# --------------------------------------------------------------------------- #
CSS = """
:root {
  --bg: #0f172a; --panel: #ffffff; --ink: #0f172a; --muted: #64748b;
  --accent: #1d4ed8; --accent-soft: #dbeafe; --line: #e2e8f0;
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
body {
  background: #1e293b; color: var(--ink);
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  display: flex; align-items: center; justify-content: center;
}
.deck { position: relative; width: min(1180px, 96vw); aspect-ratio: 16 / 9;
        max-height: 96vh; }
.slide {
  display: none; position: absolute; inset: 0; overflow: auto;
  background: var(--panel); border-radius: 14px; padding: 40px 56px;
  box-shadow: 0 24px 60px rgba(2, 6, 23, .45);
  font-size: clamp(13px, 1.28vw, 19px); line-height: 1.45;
}
.slide.active { display: block; }
.slide h1 { font-size: 1.85em; margin: .1em 0 .35em; color: var(--accent);
            letter-spacing: -.01em; }
.slide h2 { font-size: 1.4em; margin: .1em 0 .5em; }
.slide h3 { font-size: 1.1em; margin: .6em 0 .3em; color: #334155; }
.slide p { margin: .45em 0; }
.slide ul, .slide ol { margin: .35em 0 .5em; padding-left: 1.3em; }
.slide li { margin: .18em 0; }
.slide li > ul { margin: .1em 0; }
.slide code { background: #f1f5f9; border: 1px solid var(--line);
              border-radius: 5px; padding: .05em .35em; font-size: .9em; }
.slide pre { background: #0f172a; color: #e2e8f0; border-radius: 10px;
             padding: 14px 16px; overflow: auto; font-size: .72em; line-height: 1.35; }
.slide pre code { background: none; border: 0; color: inherit; padding: 0; }
.slide table { border-collapse: collapse; width: 100%; margin: .5em 0;
               font-size: .84em; }
.slide th, .slide td { border: 1px solid var(--line); padding: 6px 9px;
                       text-align: left; vertical-align: top; }
.slide th { background: var(--accent-soft); font-weight: 650; }
.slide tbody tr:nth-child(even) { background: #f8fafc; }
.slide blockquote { margin: .5em 0; padding: .55em .9em; border-left: 4px solid var(--accent);
                    background: #f8fafc; border-radius: 0 8px 8px 0; font-style: italic; }
.slide strong { color: #0b1220; }
.slide a { color: var(--accent); }
.notes { display: none; margin-top: 18px; padding: 10px 14px; border-top: 2px dashed #cbd5e1;
         color: var(--muted); font-size: .82em; white-space: pre-wrap; }
body.show-notes .notes { display: block; }
.hud { position: fixed; bottom: 14px; right: 18px; color: #cbd5e1; font-size: 13px;
       display: flex; gap: 14px; align-items: center; font-family: ui-monospace, monospace; }
.hud button { background: #334155; color: #e2e8f0; border: 0; border-radius: 7px;
              padding: 5px 11px; cursor: pointer; font: inherit; }
.hud button:hover { background: #475569; }
.help { position: fixed; bottom: 14px; left: 18px; color: #94a3b8; font-size: 12px; }
@media print {
  @page { size: A4 landscape; margin: 8mm; }
  body { background: #fff; display: block; }
  .deck { width: auto; aspect-ratio: auto; max-height: none; }
  .hud, .help { display: none; }
  .slide { display: block !important; position: static; inset: auto;
           break-after: page; page-break-after: always; box-shadow: none;
           border-radius: 0; height: 190mm; overflow: hidden;
           font-size: 12.5pt; padding: 0 6mm; }
  .slide pre { font-size: 8pt; }
  .slide table { font-size: 9.5pt; }
  .notes { display: block; }
}
"""

JS = """
const slides = [...document.querySelectorAll('.slide')];
let i = 0;
function show(n) {
  i = Math.max(0, Math.min(slides.length - 1, n));
  slides.forEach((s, k) => s.classList.toggle('active', k === i));
  document.querySelectorAll('.slide')[i].scrollTop = 0;
  document.getElementById('counter').textContent = (i + 1) + ' / ' + slides.length;
  location.hash = 's' + (i + 1);
}
document.addEventListener('keydown', e => {
  if (['ArrowRight', 'ArrowDown', ' ', 'PageDown', 'n'].includes(e.key) && e.key !== 'n') { show(i + 1); e.preventDefault(); }
  else if (['ArrowLeft', 'ArrowUp', 'PageUp'].includes(e.key)) { show(i - 1); e.preventDefault(); }
  else if (e.key === 'Home') show(0);
  else if (e.key === 'End') show(slides.length - 1);
  else if (e.key === 'n') document.body.classList.toggle('show-notes');
});
document.addEventListener('click', e => {
  if (e.target.closest('button') || e.target.closest('a')) return;
  const half = window.innerWidth / 2;
  show(e.clientX > half ? i + 1 : i - 1);
});
let touchX = null;
document.addEventListener('touchstart', e => touchX = e.touches[0].clientX);
document.addEventListener('touchend', e => {
  if (touchX === null) return;
  const dx = e.changedTouches[0].clientX - touchX;
  if (Math.abs(dx) > 40) show(dx < 0 ? i + 1 : i - 1);
  touchX = null;
});
const start = parseInt((location.hash || '#s1').slice(2), 10);
show(Number.isFinite(start) ? start - 1 : 0);
"""


def build() -> Path:
    text = SOURCE.read_text(encoding="utf-8")
    slides = split_slides(text)
    if not slides:
        raise SystemExit("no slides found — check the '---' separators")
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>FYP Defence — Time Table Schedule Generator</title>",
        f"<style>{CSS}</style>",
        "</head>",
        "<body>",
        '<div class="deck">',
    ]
    for n, slide in enumerate(slides, start=1):
        notes = (
            f'<aside class="notes"><strong>Notes · slide {n}</strong>\n'
            f"{html.escape(slide['notes'])}</aside>"
            if slide["notes"]
            else ""
        )
        parts.append(f'<section class="slide">{slide["body"]}{notes}</section>')
    parts += [
        "</div>",
        '<div class="hud">'
        '<button onclick="document.body.classList.toggle(\'show-notes\')">notes (n)</button>'
        '<button onclick="window.print()">print / PDF</button>'
        f'<span id="counter">1 / {len(slides)}</span></div>',
        '<div class="help">← / → or click to navigate · n = speaker notes · Ctrl+P = one slide per page</div>',
        f"<script>{JS}</script>",
        "</body></html>",
    ]
    TARGET.write_text("\n".join(parts), encoding="utf-8")
    return TARGET


if __name__ == "__main__":
    path = build()
    print(f"wrote {path} ({path.stat().st_size // 1024} kB)")
    sys.exit(0)
