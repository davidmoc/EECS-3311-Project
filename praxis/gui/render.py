"""Results as Markdown for the GUI's text panes (``QTextBrowser.setMarkdown``).

These play the part the ``_print_*`` functions play in the CLI: they only
format what a service returned. AI-generated text is always labelled as
such, and kept apart from the authors' own words.
"""

from __future__ import annotations

import re

from praxis.agent.corpus import Source

# Characters Markdown would read as formatting.
_SPECIAL = re.compile(r"([\\`*_\[\]#<>|])")
SHOWN_PASSAGE_CHARS = 600


def escape(text: str) -> str:
    return _SPECIAL.sub(r"\\\1", text)


# Links of this form open a text at a paragraph on the library page.
READ_SCHEME = "praxis"


def read_link(document_id, locator: str = "", label: str = "open in the library") -> str:
    paragraph = locator.lstrip("¶") or "1"
    return f"[{escape(label)}]({READ_SCHEME}:read/{document_id}/{paragraph})"


def parse_read_link(url: str) -> tuple[str, int] | None:
    """(document id, paragraph) from a ``read_link`` target, else None."""
    prefix = f"{READ_SCHEME}:read/"
    if not url.startswith(prefix):
        return None
    document_id, _, paragraph = url[len(prefix):].partition("/")
    return document_id, int(paragraph) if paragraph.isdigit() else 1


def labels(evidence: tuple[int, ...]) -> str:
    return escape(f"[{', '.join(str(n) for n in evidence)}]") if evidence else ""


def line(text: str, evidence: tuple[int, ...] = ()) -> str:
    """One list item: the text and the passages it cites."""
    return f"- {escape(text)} {labels(evidence)}".rstrip()


def ai_heading(title: str, personalized: bool) -> str:
    label = f"{title} (AI-generated"
    label += ", adapted to your reader profile)" if personalized else ")"
    return f"### {escape(label)}"


def ai_text(title: str, text: str, personalized: bool) -> str:
    """Model prose under a heading saying it is AI-generated. The model
    writes Markdown, so it is shown as written."""
    return f"{ai_heading(title, personalized)}\n\n{text.strip()}"


def warnings(notes: tuple[str, ...], tokens_used: int = 0) -> str:
    parts = [f"> **Note:** {escape(note)}" for note in notes]
    if tokens_used:
        parts.append(f"*({tokens_used} model tokens)*")
    return "\n\n".join(parts)


def sources(
    found: tuple[Source, ...],
    cited: tuple[Source, ...] = (),
    purposes: dict[int, str] | None = None,
    heading: str = "Sources",
) -> str:
    """Each passage with its citation, marked if the text cites it."""
    if not found:
        return ""
    cited_numbers = {source.number for source in cited}
    parts = [f"### {heading}"]
    for source in found:
        marks = []
        if purposes and source.number in purposes:
            marks.append(purposes[source.number])
        if source.number in cited_numbers:
            marks.append("cited")
        suffix = f" *({', '.join(escape(m) for m in marks)})*" if marks else ""
        text = source.citation.quoted_text
        if len(text) > SHOWN_PASSAGE_CHARS:
            text = text[:SHOWN_PASSAGE_CHARS].rstrip() + " […]"
        link = read_link(source.citation.document_id, source.citation.locator)
        parts.append(
            f"**{escape(source.label)}** {escape(source.citation.format())}{suffix} — {link}"
            f"\n\n> {escape(text)}"
        )
    return "\n\n".join(parts)


def join(*parts: str) -> str:
    return "\n\n".join(part for part in parts if part)
