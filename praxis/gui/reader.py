"""The reader: a whole text as one continuous scroll (F05), with AI
annotations shown inline under the paragraph they explain (F06).

Each paragraph starts with its number as a link. Clicking it emits
``paragraph_clicked``; the library page answers with the "Ask about" menu.
While an annotation is being written, a line under the paragraph says so;
when it arrives it is shown there, set apart in its own colour so the
model's words are never mistaken for the author's.

The text is rendered as Qt rich text (a subset of HTML). After rendering,
every block of the document is tagged with the number of the paragraph it
belongs to (``QTextBlock.setUserState``), so the widget can tell which
paragraph is at the bottom of the screen: that is how far the reader got.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from uuid import UUID

from PySide6.QtCore import QPoint, QTimer, QUrl, Signal
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QTextBrowser

from praxis.documents import Annotation, AnnotationType, Document, Passage

ASK_SCHEME = "ask"
COLUMN_WIDTH = 760  # pixels: lines much longer than this are hard to follow
MARGIN = 28
# qt-material colours a text browser's text with the theme's red and sets
# Roboto; the reader is set in black serif type on paper instead.
READER_STYLE = """
QTextBrowser {
  color: #1a1a1a; background: #fbf7ee; border: 1px solid #e2d6bd;
  font-family: Georgia, "Times New Roman", serif; font-size: 17px;
}
"""
INK = "#1a1a1a"
RED = "#b71c1c"
MUTED = "#7a6f5f"
ANNOTATION_INK = "#6d1b1b"
ANNOTATION_PAPER = "#f2dcd3"
# A paragraph's block starts with its number and two no-break spaces, which
# an annotation that mentions "¶3" will not.
_PARAGRAPH_START = re.compile("^¶(\\d+)  ")


@dataclass
class ReaderText:
    """What the reader shows: a text, its paragraphs, the annotations
    stored for them, and requests still running or failed."""

    document: Document
    passages: list[Passage]
    annotations: dict[UUID, list[Annotation]] = field(default_factory=dict)
    pending: dict[int, AnnotationType] = field(default_factory=dict)  # ¶ → type asked for
    failed: dict[int, str] = field(default_factory=dict)  # ¶ → why nothing was written

    @property
    def total(self) -> int:
        return len(self.passages)


def text_html(text: ReaderText) -> str:
    parts = []
    reproducible = text.document.can_reproduce()
    for number, passage in enumerate(text.passages, start=1):
        body = passage.text if reproducible else text.document.cite(passage).quoted_text
        parts.append(
            f'<p style="margin-top:0px; margin-bottom:14px; line-height:150%; color:{INK};">'
            f'<a name="p{number}" href="{ASK_SCHEME}:{number}" '
            f'style="color:{RED}; text-decoration:none; font-weight:700;">¶{number}</a>'
            f"&nbsp;&nbsp;{html.escape(body)}</p>"
        )
        for annotation in text.annotations.get(passage.id, []):
            parts.append(annotation_html(annotation))
        if number in text.pending:
            label = text.pending[number].label
            parts.append(_note_html(f"Asking about the {label} of ¶{number}… the annotation is being written; "
                                    "this can take a minute.", MUTED))
        if number in text.failed:
            parts.append(_note_html(f"✕ {text.failed[number]}", RED))
    return "".join(parts)


def _note_html(text: str, colour: str) -> str:
    return (f'<p style="margin-left:32px; margin-top:0px; margin-bottom:14px; '
            f'color:{colour}; font-style:italic;">{html.escape(text)}</p>')


def annotation_html(annotation: Annotation) -> str:
    """One annotation, in a tinted box with its own ink, labelled as AI."""
    label = f"✎ AI annotation · {annotation.type.label}"
    if annotation.personalized:
        label += " · adapted to your reader profile"
    rows = [f'<p style="font-weight:700; margin-bottom:6px;">{html.escape(label)}</p>',
            markdown_html(annotation.content)]
    if annotation.uncertainties:
        rows.append('<p style="font-weight:700; margin-top:8px;">Could not be verified:</p><ul>'
                    + "".join(f"<li>{html.escape(note)}</li>" for note in annotation.uncertainties)
                    + "</ul>")
    if annotation.sources:
        rows.append('<p style="margin-top:8px; font-size:small;">'
                    + "<br/>".join(f"[{n}] {html.escape(c.format())}"
                                   for n, c in enumerate(annotation.sources, start=1))
                    + "</p>")
    return (f'<table width="100%" cellpadding="12" cellspacing="0" '
            f'style="margin-left:32px; margin-bottom:16px; background-color:{ANNOTATION_PAPER};">'
            f'<tr><td style="color:{ANNOTATION_INK};">{"".join(rows)}</td></tr></table>')


def markdown_html(markdown: str) -> str:
    """The model writes Markdown; Qt converts it to its own HTML. Only the
    body is kept, so the box's colour and font apply to it."""
    document = QTextDocument()
    document.setMarkdown(markdown.strip())
    converted = document.toHtml()
    start = converted.find(">", converted.find("<body")) + 1
    end = converted.rfind("</body>")
    return converted[start:end] if start > 0 and end > start else html.escape(markdown)


class ReaderPane(QTextBrowser):
    """Shows one ``ReaderText``. Emits ``paragraph_clicked`` with the
    paragraph number, and ``reached`` with the furthest paragraph on screen
    once scrolling settles."""

    paragraph_clicked = Signal(int)
    reached = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._clicked)
        self.setStyleSheet(READER_STYLE)
        self.document().setDocumentMargin(MARGIN)
        self.text: ReaderText | None = None
        self._settled = QTimer(self)  # scrolling has paused: note how far the reader got
        self._settled.setSingleShot(True)
        self._settled.setInterval(700)
        self._settled.timeout.connect(lambda: self.reached.emit(self.furthest_visible()))
        self.verticalScrollBar().valueChanged.connect(lambda _: self._settled.start())

    def show_text(self, text: ReaderText, paragraph: int = 1) -> None:
        """Show ``text`` from ``paragraph``."""
        self.text = text
        self._render()
        self.scroll_to(paragraph)

    def rerender(self) -> None:
        """Show changes (an annotation arrived) without moving the page.
        Nothing above the changed paragraph moves, so the scroll position
        still points at the same place."""
        bar = self.verticalScrollBar()
        position = bar.value()
        self._render()
        bar.setValue(position)
        QTimer.singleShot(0, lambda: bar.setValue(position))  # after Qt finishes laying out

    def scroll_to(self, paragraph: int) -> None:
        if paragraph <= 1:
            self.verticalScrollBar().setValue(0)
        else:
            self.scrollToAnchor(f"p{paragraph}")
            QTimer.singleShot(0, lambda: self.scrollToAnchor(f"p{paragraph}"))

    def furthest_visible(self) -> int:
        """The paragraph at the bottom edge of the screen."""
        if self.text is None:
            return 0
        viewport = self.viewport()
        block = self.cursorForPosition(QPoint(viewport.width() // 2, viewport.height() - 2)).block()
        return max(block.userState(), 1)

    def _render(self) -> None:
        self.setHtml(text_html(self.text) if self.text else "")
        self._centre_column()
        current = 0
        block = self.document().begin()
        while block.isValid():
            match = _PARAGRAPH_START.match(block.text())
            if match:
                current = int(match.group(1))
            block.setUserState(current)
            block = block.next()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt's name)
        super().resizeEvent(event)
        self._centre_column()

    def _centre_column(self) -> None:
        """Keep the text in a column of ``COLUMN_WIDTH``, centred, by
        widening the side margins of the document's outer frame."""
        side = max(0, (self.viewport().width() - COLUMN_WIDTH) // 2)
        frame = self.document().rootFrame()
        style = frame.frameFormat()
        if style.leftMargin() != side:
            style.setLeftMargin(side)
            style.setRightMargin(side)
            frame.setFrameFormat(style)

    def _clicked(self, url: QUrl) -> None:
        if url.scheme() == ASK_SCHEME and url.path().isdigit():
            self.paragraph_clicked.emit(int(url.path()))
