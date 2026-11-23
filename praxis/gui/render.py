"""The building blocks of the result panes: Qt rich text (a subset of HTML).

Results used to be Markdown, which ``QTextBrowser`` draws as one plain
column: every heading, passage and AI paragraph looked alike. Here each
kind of content has its own look, so a reader can tell at a glance what
they are reading:

- the authors' own words (passages, reports) sit in white cards, in serif
  type, each with its citation and a link to open it in the library;
- everything the model wrote sits in a tinted box with its own ink, headed
  "AI-generated", like an annotation in the reader;
- a citation such as ``[3]`` in AI text is a link that scrolls to
  passage 3, so a claim can be checked against its source in one click.

Qt's rich text has no CSS boxes (no padding or borders on ``div``), so
boxes are one-cell tables, which it does draw with a background and border.
"""

from __future__ import annotations

import html
import re

from PySide6.QtGui import QTextDocument

from praxis.agent.corpus import Source

INK = "#1a1a1a"
MUTED = "#6b5f4f"
RED = "#b71c1c"
PAPER = "#fbf7ee"
CARD = "#fffdf8"
RULE = "#e2d6bd"
AI_INK = "#6d1b1b"
AI_PAPER = "#f2dcd3"
NOTE_PAPER = "#f3ecdc"
GOOD = "#2e6b34"
SERIF = "Georgia, 'Times New Roman', serif"

SHOWN_PASSAGE_CHARS = 600

# Applied to every result pane's document. qt-material colours text
# browsers red and links default blue; results are set in ink on paper.
DOCUMENT_STYLE = f"""
body {{ color: {INK}; font-size: 14px; }}
a {{ color: {RED}; text-decoration: none; }}
h2 {{ color: {INK}; font-size: 22px; font-weight: 800; margin-top: 0px; margin-bottom: 2px; }}
h3 {{ color: {RED}; font-size: 13px; font-weight: 800; margin-top: 22px; margin-bottom: 8px; }}
h4 {{ color: {INK}; font-size: 14px; font-weight: 700; margin-top: 12px; margin-bottom: 4px; }}
p {{ margin-top: 0px; margin-bottom: 6px; line-height: 140%; }}
li {{ margin-bottom: 5px; line-height: 140%; }}
"""
WIDGET_STYLE = f"""
QTextBrowser {{
  color: {INK}; background: {PAPER}; border: 1px solid {RULE};
  font-size: 14px; padding: 6px;
}}
"""

# --- text ----------------------------------------------------------------------

# Characters Markdown would read as formatting (for panes still in Markdown).
_SPECIAL = re.compile(r"([\\`*_\[\]#<>|])")


def escape(text: str) -> str:
    """Escape for Markdown (the workspace page still uses it)."""
    return _SPECIAL.sub(r"\\\1", text)


def esc(text: str) -> str:
    """Escape for HTML."""
    return html.escape(text, quote=True)


def shorten(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " […]"


# --- links ---------------------------------------------------------------------

# Links of this form open a text at a paragraph on the library page.
READ_SCHEME = "praxis"


def read_href(document_id, locator: str = "") -> str:
    paragraph = locator.lstrip("¶") or "1"
    return f"{READ_SCHEME}:read/{document_id}/{paragraph}"


def read_link(document_id, locator: str = "", label: str = "Open in the library ›") -> str:
    return f'<a href="{read_href(document_id, locator)}">{esc(label)}</a>'


def parse_read_link(url: str) -> tuple[str, int] | None:
    """(document id, paragraph) from a ``read_link`` target, else None."""
    prefix = f"{READ_SCHEME}:read/"
    if not url.startswith(prefix):
        return None
    document_id, _, paragraph = url[len(prefix):].partition("/")
    return document_id, int(paragraph) if paragraph.isdigit() else 1


def source_anchor(number: int) -> str:
    return f"src-{number}"


def cite(evidence: tuple[int, ...] | list[int]) -> str:
    """``[1, 3]`` with each number a link to its passage."""
    if not evidence:
        return ""
    links = ", ".join(f'<a href="#{source_anchor(n)}">{n}</a>' for n in evidence)
    return f'<span style="color:{RED}; font-size:12px; font-weight:700;">[{links}]</span>'


_CITATION = re.compile(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\]")


def link_citations(fragment: str) -> str:
    """Turn ``[3]`` and ``[1, 2]`` in model text (already HTML) into links
    to the passages. Text inside tags is left alone."""
    def replace(match: re.Match) -> str:
        numbers = [int(n) for n in re.findall(r"\d+", match.group(1))]
        return cite(numbers)

    pieces = re.split(r"(<[^>]*>)", fragment)
    return "".join(piece if piece.startswith("<") else _CITATION.sub(replace, piece) for piece in pieces)


def markdown_html(markdown: str) -> str:
    """The model writes Markdown; Qt converts it to its own HTML. Only the
    body is kept, so the surrounding box's colour and font apply to it."""
    document = QTextDocument()
    document.setMarkdown(markdown.strip())
    converted = document.toHtml()
    start = converted.find(">", converted.find("<body")) + 1
    end = converted.rfind("</body>")
    return converted[start:end] if start > 0 and end > start else esc(markdown)


# --- blocks --------------------------------------------------------------------


def box(inner: str, background: str = CARD, border: str = RULE, padding: int = 12,
        color: str = INK, margin_bottom: int = 10, anchor: str = "") -> str:
    """A block with a background and border: a one-cell table."""
    name = f'<a name="{anchor}"></a>' if anchor else ""
    return (f'{name}<table width="100%" cellspacing="0" cellpadding="{padding}" '
            f'style="margin-bottom:{margin_bottom}px; border:1px solid {border}; border-style:solid; '
            f'background-color:{background};">'
            f'<tr><td style="color:{color};">{inner}</td></tr></table>')


def badge(text: str, background: str = NOTE_PAPER, color: str = MUTED) -> str:
    return (f'<span style="background-color:{background}; color:{color}; font-size:11px; '
            f'font-weight:700;">&nbsp;{esc(text)}&nbsp;</span>')


def ai_badge(personalized: bool = False) -> str:
    return badge("AI-GENERATED" + (" · ADAPTED TO YOU" if personalized else ""), AI_PAPER, AI_INK)


def title(text: str, subtitle: str = "") -> str:
    sub = f'<p style="color:{MUTED}; font-size:13px; margin-bottom:4px;">{subtitle}</p>' if subtitle else ""
    return f"<h2>{esc(text)}</h2>{sub}"


def meta(*items: str) -> str:
    """A muted line of details separated by dots (items already HTML)."""
    shown = [item for item in items if item]
    return f'<p style="color:{MUTED}; font-size:13px;">{" &nbsp;·&nbsp; ".join(shown)}</p>' if shown else ""


def section(heading: str, body: str, anchor: str = "", note: str = "") -> str:
    """A titled part of a result; ``anchor`` lets the jump bar reach it."""
    if not body:
        return ""
    name = f'<a name="{anchor}"></a>' if anchor else ""
    extra = f' <span style="color:{MUTED}; font-size:12px; font-weight:400;">{esc(note)}</span>' if note else ""
    return f"{name}<h3>{esc(heading.upper())}{extra}</h3>{body}"


def jump_bar(targets: list[tuple[str, str]]) -> str:
    """Links to the parts of a long result, shown under its title."""
    if len(targets) < 2:
        return ""
    links = " &nbsp;·&nbsp; ".join(f'<a href="#{anchor}">{esc(label)}</a>' for label, anchor in targets)
    return f'<p style="font-size:13px; margin-top:6px;"><span style="color:{MUTED};">Jump to:</span> {links}</p>'


def ai_box(label: str, inner: str, personalized: bool = False, anchor: str = "") -> str:
    """Model output, set apart in the annotation colours and labelled."""
    head = (f'<p style="margin-bottom:8px;">{ai_badge(personalized)} '
            f'<span style="font-weight:700;">{esc(label)}</span></p>')
    return box(head + inner, AI_PAPER, "#e5c4b8", 14, AI_INK, 14, anchor)


def ai_prose(label: str, text: str, personalized: bool = False, anchor: str = "") -> str:
    """Model prose (Markdown) in an AI box, its citations made links."""
    return ai_box(label, link_citations(markdown_html(text)), personalized, anchor)


def bullets(rows: list[str]) -> str:
    """A list; each row is already HTML."""
    if not rows:
        return ""
    return '<ul style="margin-top:0px; margin-left:-16px;">' + "".join(f"<li>{row}</li>" for row in rows) + "</ul>"


def point(text: str, evidence: tuple[int, ...] = (), label: str = "") -> str:
    """One finding: an optional bold label, the text, its citations."""
    lead = f"<b>{esc(label)}</b> — " if label else ""
    return f"{lead}{esc(text)} {cite(evidence)}".rstrip()


def subsection(heading: str, rows: list[str]) -> str:
    if not rows:
        return ""
    return f"<h4>{esc(heading)}</h4>{bullets(rows)}"


def quote(text: str) -> str:
    """The authors' words, in serif type."""
    body = esc(text).replace("\n\n", "<br/><br/>").replace("\n", " ")
    return f'<p style="font-family:{SERIF}; font-size:15px; line-height:150%; color:{INK};">{body}</p>'


def passage_card(source: Source, marks: list[str] = (), limit: int = SHOWN_PASSAGE_CHARS) -> str:
    """A passage: its number, where it is from, how it was used, the words."""
    citation = source.citation
    tags = " ".join(badge(m.upper(), AI_PAPER if m == "cited" else NOTE_PAPER,
                          AI_INK if m == "cited" else MUTED) for m in marks)
    head = (f'<p style="margin-bottom:6px;"><span style="color:{RED}; font-weight:800;">{esc(source.label)}</span> '
            f'<b>{esc(citation.author)}</b>, <i>{esc(citation.document_title)}</i>'
            f'<span style="color:{MUTED};"> {esc(citation.locator)}</span> {tags}</p>')
    foot = f'<p style="font-size:13px; margin-bottom:0px;">{read_link(citation.document_id, citation.locator)}</p>'
    return box(head + quote(shorten(citation.quoted_text, limit)) + foot, anchor=source_anchor(source.number))


def sources(
    found: tuple[Source, ...],
    cited: tuple[Source, ...] = (),
    purposes: dict[int, str] | None = None,
    heading: str = "Sources",
    anchor: str = "sources",
) -> str:
    """Each passage as a card, marked with what it was used for and
    whether the AI text cites it."""
    if not found:
        return ""
    cited_numbers = {source.number for source in cited}
    cards = []
    for source in found:
        marks = []
        if purposes and source.number in purposes:
            marks.append(purposes[source.number])
        if source.number in cited_numbers:
            marks.append("cited")
        cards.append(passage_card(source, marks))
    note = f"{len(found)} passage{'s' if len(found) != 1 else ''}"
    if cited_numbers:
        note += f", {len(cited_numbers)} cited"
    return section(heading, "".join(cards), anchor, note)


def warnings(notes: tuple[str, ...], tokens_used: int = 0) -> str:
    parts = [f'<p style="margin-bottom:4px;"><b>Note:</b> {esc(note)}</p>' for note in notes]
    if parts:
        body = box("".join(parts), NOTE_PAPER, RULE, 10, INK, 6)
    else:
        body = ""
    if tokens_used:
        body += f'<p style="color:{MUTED}; font-size:12px;">{tokens_used:,} model tokens</p>'
    return body


def progress(fraction: float, width: int = 100) -> str:
    """A thin bar for progress from 0 to 1."""
    done = max(0, min(100, round(fraction * 100)))
    cells = ""
    if done:
        cells += f'<td width="{done}%" style="background-color:{RED}; font-size:3px;">&nbsp;</td>'
    if done < 100:
        cells += f'<td width="{100 - done}%" style="background-color:{RULE}; font-size:3px;">&nbsp;</td>'
    # An empty cell has no height in Qt's rich text, hence the tiny space.
    return (f'<table width="{width}%" cellspacing="0" cellpadding="0" '
            f'style="margin-top:6px; margin-bottom:12px;"><tr>{cells}</tr></table>')


def notice(text: str) -> str:
    """A whole pane saying one thing (nothing yet, where to go)."""
    return f'<p style="color:{MUTED}; font-size:15px; margin-top:20px;">{esc(text)}</p>'


def join(*parts: str) -> str:
    return "".join(part for part in parts if part)
