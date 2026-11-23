"""Results as Markdown for the GUI's text panes (``QTextBrowser.setMarkdown``).

These play the part the ``_print_*`` functions play in the CLI: they only
format what a service returned. AI-generated text is always labelled as
such, and kept apart from the authors' own words.
"""

from __future__ import annotations

import re

from praxis.agent.corpus import Source
from praxis.documents import Annotation, Document, Passage

# Characters Markdown would read as formatting.
_SPECIAL = re.compile(r"([\\`*_\[\]#<>|])")
SHOWN_PASSAGE_CHARS = 600


def escape(text: str) -> str:
    return _SPECIAL.sub(r"\\\1", text)


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
        parts.append(f"**{escape(source.label)}** {escape(source.citation.format())}{suffix}\n\n> {escape(text)}")
    return "\n\n".join(parts)


def join(*parts: str) -> str:
    return "\n\n".join(part for part in parts if part)


def paragraphs(document: Document, shown: list[Passage], annotations: dict) -> str:
    """The author's paragraphs, each headed by its number, with any stored
    annotations below it, set apart as AI commentary."""
    parts = []
    for passage in shown:
        text = passage.text if document.can_reproduce() else document.cite(passage).quoted_text
        parts.append(f"**{escape(passage.locator)}**  {escape(text)}")
        for annotation in annotations.get(passage.id, []):
            parts.append(annotation_markdown(annotation))
    return "\n\n".join(parts)


def annotation_markdown(annotation: Annotation) -> str:
    label = f"AI annotation: {annotation.type.label}"
    if annotation.personalized:
        label += ", adapted to your reader profile"
    body = "\n".join(f"> {row}" if row.strip() else ">" for row in annotation.content.strip().splitlines())
    parts = [f"> ✎ ***{escape(label)}***\n>\n{body}"]
    if annotation.uncertainties:
        parts.append("> **Could not be verified:**\n" + "\n".join(
            f"> - {escape(note)}" for note in annotation.uncertainties
        ))
    if annotation.sources:
        parts.append("\n".join(
            f"> {escape(f'[{number}]')} {escape(citation.format())}"
            for number, citation in enumerate(annotation.sources, start=1)
        ))
    return "\n>\n".join(parts)
