"""The first page: where to start. The news worth looking into (F01),
fetched when the application starts; texts the reader has begun and not
finished (F05, from the reading history F13 keeps); and the learning path
in progress (F08). Each is a card that opens its page.

If the library is empty, the page offers to load the bundled texts.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from praxis.app import Application, bundled_library_service
from praxis.gui.tasks import TaskRunner, describe_error
from praxis.gui.widgets import Card, heading, progress_bar
from praxis.library import ImportReport
from praxis.news.events import Event, Grouping
from praxis.news.service import Dashboard
from praxis.reader_model.models import ReadingRecord
from praxis.reading import LearningPath

NO_MODEL = (
    "No language model is configured: passages are still found, but nothing "
    "is explained. Copy .env.example to .env and set OPENAI_API_KEY."
)
NEWS_CARDS = 6
READING_CARDS = 4
COLUMNS = 3
SUMMARY_CHARS = 240
NO_READINGS = "Nothing in progress. Open a text in the Library and it will wait for you here."
NO_PATH = "No learning path in progress. Build one on the Research page (“What does this assume?”)."
NO_NEWS = "No news yet. Press Refresh to fetch the latest from the feeds."


@dataclass(frozen=True)
class HomeStatus:
    texts: int
    has_model: bool


@dataclass(frozen=True)
class Reading:
    """A text begun and not finished."""

    record: ReadingRecord
    author: str


class HomeController:
    def __init__(self, application: Application) -> None:
        self._application = application

    def status(self) -> HomeStatus:
        return HomeStatus(len(self._application.library.browse()), self._application.llm is not None)

    def load_bundled_library(self) -> ImportReport:
        return bundled_library_service(self._application).import_catalogue()

    def news(self, refresh: bool = True) -> Dashboard:
        """F01's dashboard, as the News page shows it."""
        return self._application.news.get_dashboard_events(2, limit=12, refresh=refresh)

    def readings(self, count: int = READING_CARDS) -> list[Reading]:
        """The texts read most recently that are not finished and are
        still in the library."""
        found = []
        for record in self._application.profiles.get_profile().history.recent(50):
            if record.completed:
                continue
            try:
                document = self._application.library.get_document(record.document_id)
            except Exception:  # removed from the library since
                continue
            found.append(Reading(record, document.author))
            if len(found) == count:
                break
        return found

    def current_path(self) -> LearningPath | None:
        """The most recently used learning path with a step still to do."""
        prerequisites = self._application.prerequisites
        for summary in prerequisites.list_paths(20):
            if summary.settled_count < summary.step_count:
                return prerequisites.get_path(summary.id)
        return None


class HomeView(QWidget):
    def __init__(
        self,
        controller: HomeController,
        runner: TaskRunner,
        open_reading: Callable[[str, int], None] | None = None,
        open_event: Callable[[UUID], None] | None = None,
        open_path: Callable[[UUID], None] | None = None,
        news_loaded: Callable[[Dashboard], None] | None = None,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._runner = runner
        self._open_reading = open_reading or (lambda *_: None)
        self._open_event = open_event or (lambda _: None)
        self._open_path = open_path or (lambda _: None)
        self._news_loaded = news_loaded or (lambda _: None)
        self.news_cards: list[Card] = []
        self.reading_cards: list[Card] = []
        self.path_card: Card | None = None
        self.path: LearningPath | None = None

        title = QLabel("PRAXIS")
        title.setStyleSheet("font-size: 34px; font-weight: 900; color: #b71c1c; letter-spacing: 4px;")
        tagline = QLabel("Current events, history and political theory, read from the primary sources.")
        tagline.setWordWrap(True)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("color: #6b5f4f;")
        self.load_button = QPushButton("Load the bundled library")
        self.load_button.clicked.connect(self.load_library)
        self.message = QLabel()
        self.message.setWordWrap(True)
        runner.busy_changed.connect(lambda busy: self.load_button.setEnabled(not busy))

        self.refresh_news_button = QPushButton("Refresh")
        self.refresh_news_button.clicked.connect(self.fetch_news)
        runner.busy_changed.connect(lambda busy: self.refresh_news_button.setEnabled(not busy))
        self.news_status = QLabel(NO_NEWS)
        self.news_status.setWordWrap(True)
        self.news_grid = QGridLayout()
        self.news_grid.setSpacing(12)
        self.readings_status = QLabel()
        self.readings_status.setWordWrap(True)
        self.readings_grid = QGridLayout()
        self.readings_grid.setSpacing(12)
        self.path_status = QLabel()
        self.path_status.setWordWrap(True)
        self.path_box = QVBoxLayout()

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(tagline)
        layout.addWidget(self.summary)
        layout.addWidget(self.load_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.message)
        layout.addLayout(_section("In the news", self.refresh_news_button))
        layout.addWidget(self.news_status)
        layout.addLayout(self.news_grid)
        layout.addLayout(_section("Pick up where you left off"))
        layout.addWidget(self.readings_status)
        layout.addLayout(self.readings_grid)
        layout.addLayout(_section("Your learning path"))
        layout.addWidget(self.path_status)
        layout.addLayout(self.path_box)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.refresh()

    def refresh(self) -> None:
        """Everything but the news, which is fetched on start and on Refresh."""
        status = self._controller.status()
        lines = [f"The library holds {status.texts} text{'s' if status.texts != 1 else ''}."]
        if not status.has_model:
            lines.append(NO_MODEL)
        self.summary.setText(" ".join(lines))
        self.load_button.setVisible(status.texts == 0)
        self._show_readings(self._controller.readings())
        self._show_path(self._controller.current_path())

    # --- news ------------------------------------------------------------------

    def fetch_news(self) -> None:
        """Fetch and group the latest news. Run at start-up; the model
        writes the summaries, so it can take a minute."""
        self.news_status.setText("Fetching the latest news… the summaries can take a minute.")
        self.news_status.show()

        def done(dashboard: Dashboard) -> None:
            self.show_news(dashboard)
            self._news_loaded(dashboard)

        self._runner.run("Fetching the news", lambda: self._controller.news(), done,
                         lambda exc: self.news_status.setText(f"The news could not be fetched: {describe_error(exc)}"))

    def show_news(self, dashboard: Dashboard) -> None:
        self.news_cards = [self._event_card(event) for event in dashboard.events[:NEWS_CARDS]]
        _fill(self.news_grid, self.news_cards)
        notes = list(dashboard.warnings)
        if not dashboard.events:
            notes.insert(0, NO_NEWS)
        self.news_status.setText("\n".join(notes))
        self.news_status.setVisible(bool(notes))

    def _event_card(self, event: Event) -> Card:
        details = [event.last_date.strftime("%b %d") if event.last_date else "undated"]
        count = len(event.outlets)
        details.append(f"{count} outlet{'s' if count != 1 else ''}")
        if event.categories:
            details.append(event.categories[0])
        if event.is_summarized:
            body = "AI summary: " + _shorten(event.summary)
        elif event.grouping is Grouping.SINGLE_REPORT:
            body = f"Reported only by {', '.join(event.outlets)}."
        else:
            body = ", ".join(event.outlets)
        card = Card(event.headline, " · ".join(details), body)
        card.clicked.connect(lambda: self._open_event(event.id))
        return card

    # --- readings --------------------------------------------------------------

    def _show_readings(self, readings: list[Reading]) -> None:
        self.reading_cards = [self._reading_card(r) for r in readings]
        _fill(self.readings_grid, self.reading_cards)
        self.readings_status.setText(NO_READINGS)
        self.readings_status.setVisible(not readings)

    def _reading_card(self, reading: Reading) -> Card:
        record = reading.record
        card = Card(
            record.title,
            reading.author,
            f"¶{record.furthest_paragraph} of {record.total_paragraphs} · "
            f"{round(record.progress * 100)}% · last read {record.last_read.strftime('%b %d')}",
        )
        card.add(progress_bar(record.progress))
        card.clicked.connect(lambda: self._open_reading(str(record.document_id), record.furthest_paragraph))
        return card

    # --- the learning path -----------------------------------------------------

    def _show_path(self, path: LearningPath | None) -> None:
        self.path = path
        if self.path_card is not None:
            self.path_card.deleteLater()
            self.path_card = None
        self.path_status.setText(NO_PATH)
        self.path_status.setVisible(path is None)
        if path is None:
            return
        settled, total = path.settled_count, len(path.steps)
        number, step = path.next_step
        body = f"Next: step {number} of {total} — {step.name}"
        if step.prerequisite.why:
            body += f"\n{step.prerequisite.why} (AI-generated)"
        card = Card(path.target, f"{settled} of {total} steps dealt with", body)
        card.add(progress_bar(settled / total if total else 0))
        self.continue_button = QPushButton("Continue" if step.readings else "Open the path")
        self.continue_button.clicked.connect(self.continue_path)
        card.add(self.continue_button)
        card.clicked.connect(lambda: self._open_path(path.id))
        self.path_card = card
        self.path_box.addWidget(card)

    def continue_path(self) -> None:
        """Open the next step's first reading, or the path if it has none."""
        if self.path is None or self.path.next_step is None:
            return
        _, step = self.path.next_step
        if step.readings:
            citation = step.readings[0]
            paragraph = citation.locator.lstrip("¶")
            self._open_reading(str(citation.document_id), int(paragraph) if paragraph.isdigit() else 1)
        else:
            self._open_path(self.path.id)

    # --- the bundled library ---------------------------------------------------

    def load_library(self) -> None:
        def done(report: ImportReport) -> None:
            self.message.setText(f"{len(report.imported)} imported, {len(report.failures)} skipped.")
            self.refresh()

        self._runner.run(
            "Loading the bundled library", self._controller.load_bundled_library, done,
            lambda exc: self.message.setText(f"Error: {describe_error(exc)}"),
        )


def _section(title: str, *extras: QWidget) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setContentsMargins(0, 18, 0, 0)
    row.addWidget(heading(title))
    row.addStretch()
    for widget in extras:
        row.addWidget(widget)
    return row


def _fill(grid: QGridLayout, cards: list[Card]) -> None:
    """Replace the grid's cards, ``COLUMNS`` to a row."""
    while grid.count():
        widget = grid.takeAt(0).widget()
        if widget is not None:
            widget.deleteLater()
    for index, card in enumerate(cards):
        grid.addWidget(card, index // COLUMNS, index % COLUMNS, Qt.AlignmentFlag.AlignTop)
    for column in range(COLUMNS):
        grid.setColumnStretch(column, 1)


def _shorten(text: str, limit: int = SUMMARY_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"
