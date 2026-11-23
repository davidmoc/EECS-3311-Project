"""Small pieces shared by the views."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from praxis.gui.render import DOCUMENT_STYLE, WIDGET_STYLE, parse_read_link
from praxis.gui.tasks import TaskRunner

OpenReading = Callable[[str, int], None]


def lock_while_busy(runner: TaskRunner, *widgets: QWidget) -> None:
    """Disable ``widgets`` while a request runs: they reach the database,
    which the running request is using (see ``praxis.gui.tasks``)."""
    runner.busy_changed.connect(lambda busy: [w.setEnabled(not busy) for w in widgets])


def result_browser(open_reading: OpenReading | None = None,
                   on_link: Callable[[str], None] | None = None) -> QTextBrowser:
    """A pane for results (``praxis.gui.results``). Its links: a passage
    link (``render.read_link``) opens the text on the library page; ``#…``
    scrolls to that part of the result (a citation to its passage, the
    "Jump to" bar to a section); a web address opens in the browser; any
    other goes to ``on_link`` (a learning path's step actions)."""
    browser = QTextBrowser()
    browser.setOpenLinks(False)
    browser.setStyleSheet(WIDGET_STYLE)
    browser.document().setDefaultStyleSheet(DOCUMENT_STYLE)
    browser.document().setDocumentMargin(14)

    def clicked(url: QUrl) -> None:
        text = url.toString()
        target = parse_read_link(text)
        if target is not None:
            if open_reading is not None:
                open_reading(*target)
        elif not url.scheme() and url.fragment():
            browser.scrollToAnchor(url.fragment())
        elif url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)
        elif on_link is not None:
            on_link(text)

    browser.anchorClicked.connect(clicked)
    return browser


def item_list() -> QListWidget:
    """A list whose entries run to several lines (an event card, a saved
    item with its date), shaded alternately and spaced so each entry reads
    as one. A live run showed the news cards running together without it."""
    widget = QListWidget()
    widget.setWordWrap(True)
    widget.setAlternatingRowColors(True)
    widget.setSpacing(3)
    return widget


class Card(QFrame):
    """A clickable panel: a bold title, a line of details, and some text.
    The home page shows news, readings and the learning path as cards."""

    clicked = Signal()

    def __init__(self, title: str, details: str = "", body: str = "") -> None:
        super().__init__()
        self.setObjectName("card")
        self.key = ""  # what the card stands for, in a CardList
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(CARD_STYLE)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.title = _label(title, "font-size: 15px; font-weight: 700;")
        self.details = _label(details, f"color: {MUTED}; font-size: 12px;")
        self.body = _label(body, "font-size: 13px;")
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(14, 12, 14, 12)
        self.layout_.setSpacing(6)
        for label in (self.title, self.details, self.body):
            self.layout_.addWidget(label)
            label.setVisible(bool(label.text()))

    def add(self, widget: QWidget) -> None:
        self.layout_.addWidget(widget)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt's name)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


MUTED = "#6b5f4f"
CARD_STYLE = """
QFrame#card { background: #fbf7ee; border: 1px solid #e2d6bd; border-radius: 6px; }
QFrame#card:hover { border: 1px solid #b71c1c; }
QFrame#card QLabel { background: transparent; border: none; }
"""


def _label(text: str, style: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setStyleSheet(style)
    return label


def progress_bar(value: float) -> QProgressBar:
    """A thin bar for progress from 0 to 1."""
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(round(value * 100))
    bar.setTextVisible(False)
    bar.setFixedHeight(6)
    return bar


def heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-size: 20px; font-weight: 800; letter-spacing: 1px;")
    return label


SELECTED_CARD_STYLE = """
QFrame#card { background: #f2dcd3; border: 1px solid #b71c1c; border-radius: 6px; }
QFrame#card QLabel { background: transparent; border: none; }
"""


class CardList(QScrollArea):
    """Cards one under another, scrolling, one of them selectable: the
    news page's events. Clicking a card selects it and emits ``chosen``
    with the card's ``key``."""

    chosen = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(0, 0, 8, 0)
        self._layout.setSpacing(8)
        self._layout.addStretch()
        self.setWidget(content)
        self.cards: list[Card] = []
        self.selected: str | None = None

    def set_cards(self, cards: list[tuple[str, Card]]) -> None:
        for card in self.cards:
            card.deleteLater()
        self.cards = []
        self.selected = None
        for key, card in cards:
            card.key = key
            # Grow to fit the wrapped text; the default (Maximum) squeezes
            # the labels together when the list is narrow.
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            card.clicked.connect(lambda key=key: self.select(key))
            self._layout.insertWidget(self._layout.count() - 1, card)
            self.cards.append(card)

    def count(self) -> int:
        return len(self.cards)

    def select(self, key: str) -> None:
        self.selected = key
        for card in self.cards:
            card.setStyleSheet(SELECTED_CARD_STYLE if card.key == key else CARD_STYLE)
        self.chosen.emit(key)
