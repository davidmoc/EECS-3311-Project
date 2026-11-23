"""The news page: the dashboard of current events (F01) and an event's
expanded view (F02), from which it can be researched (F03), its outlets
compared (F10), its background traced (F09), or saved (F15).

Stage 1's ``NewsView`` and ``NewsController`` (SD03).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any
from uuid import UUID

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from praxis.app import Application
from praxis.gui import results
from praxis.gui.tasks import TaskRunner, describe_error
from praxis.gui.render import RED, notice, shorten
from praxis.gui.widgets import Card, CardList, OpenReading, lock_while_busy, result_browser
from praxis.news.events import Event, Grouping, SummaryStatus
from praxis.news.service import Dashboard

SUMMARY_CHARS = 200
_CITATIONS = re.compile(r"\s*\[\d+(?:\s*,\s*\d+)*\]")
EMPTY = "No current news is stored. Press “Fetch the latest news”."


def event_card(event: Event) -> Card:
    """F01: one dashboard event: headline, when and who reported it, how
    sure the grouping is, and the AI summary, shortened (the event's page
    has the rest)."""
    details = [f"{event.last_date:%b %d}" if event.last_date else "undated"]
    details += list(event.categories[:2])
    outlets = event.outlets
    details.append(f"{len(outlets)} outlet{'s' if len(outlets) != 1 else ''}")
    lines = []
    if event.is_summarized:
        # Citation marks mean nothing in the list; the event's page has them.
        summary = " ".join(_CITATIONS.sub("", event.summary).split())
        lines.append("AI summary: " + shorten(summary, SUMMARY_CHARS))
    elif event.summary_status is SummaryStatus.HEADLINES_ONLY:
        lines.append("No summary; open it to read the reports.")
    lines.append(", ".join(outlets))
    card = Card(event.headline, " · ".join(details), "\n".join(lines))
    flag = ""
    if event.grouping is Grouping.SINGLE_REPORT:
        flag = "Single report: no other outlet in the feeds has reported it."
    elif event.grouping is Grouping.UNCERTAIN:
        flag = "Grouping uncertain: these reports may not all be about one event."
    if event.note:
        flag = f"{flag} {event.note}".strip()
    if flag:
        warning = QLabel(flag)
        warning.setWordWrap(True)
        warning.setStyleSheet(f"color: {RED}; font-size: 12px;")
        card.add(warning)
    return card


class NewsController:
    def __init__(self, application: Application) -> None:
        self._application = application
        self._news = application.news

    def dashboard(self, days: int, refresh: bool) -> Dashboard:
        return self._news.get_dashboard_events(days, limit=12, refresh=refresh)

    def expand(self, event_id: UUID):
        return self._news.get_expanded_event(event_id)

    def research(self, event_id: UUID):
        return self._application.agent.research_event(self._news.get_event(event_id))

    def compare(self, event_id: UUID):
        return self._application.agent.compare_event_reports(self._news.get_event(event_id))

    def history(self, event_id: UUID):
        return self._application.agent.explore_event_history(self._news.get_event(event_id))

    def save(self, event_id: UUID):
        return self._application.workspace.save_event(self._news.get_event(event_id))


class NewsView(QWidget):
    def __init__(self, controller: NewsController, runner: TaskRunner, open_reading: OpenReading | None = None) -> None:
        super().__init__()
        self._controller = controller
        self._runner = runner
        self.selected: UUID | None = None
        self.dashboard: Dashboard | None = None

        self.days = QSpinBox()
        self.days.setRange(1, 14)
        self.days.setValue(2)
        self.days.setSuffix(" days")
        self.show_button = QPushButton("Show stored news")
        self.show_button.clicked.connect(lambda: self.load(refresh=False))
        self.fetch_button = QPushButton("Fetch the latest news")
        self.fetch_button.clicked.connect(lambda: self.load(refresh=True))
        top = QHBoxLayout()
        top.addWidget(QLabel("News from the last"))
        for widget in (self.days, self.show_button, self.fetch_button):
            top.addWidget(widget)
        top.addStretch()

        self.event_list = CardList()
        self.event_list.chosen.connect(lambda key: self.open_event(UUID(key)))
        self.event_list.setMinimumWidth(320)
        self.output = result_browser(open_reading)
        self.research_button = QPushButton("Research it (F03)")
        self.research_button.clicked.connect(
            lambda: self._act("research", "Researching the event", results.research)
        )
        self.compare_button = QPushButton("Compare the outlets (F10)")
        self.compare_button.clicked.connect(
            lambda: self._act("compare", "Comparing the outlets", results.comparison)
        )
        self.history_button = QPushButton("Historical background (F09)")
        self.history_button.clicked.connect(
            lambda: self._act("history", "Tracing the background", results.history)
        )
        self.save_button = QPushButton("Save to workspace")
        self.save_button.clicked.connect(self.save)
        actions = QHBoxLayout()
        for button in (self.research_button, self.compare_button, self.history_button, self.save_button):
            actions.addWidget(button)
        actions.addStretch()
        self.message = QLabel()
        self.message.setWordWrap(True)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.output, stretch=1)
        right_layout.addLayout(actions)
        splitter = QSplitter()
        splitter.addWidget(self.event_list)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(splitter, stretch=1)
        layout.addWidget(self.message)

        self._actions = (self.research_button, self.compare_button, self.history_button, self.save_button)
        lock_while_busy(runner, self.show_button, self.fetch_button, self.event_list)
        runner.busy_changed.connect(lambda _busy: self._enable_actions())
        self._enable_actions()
        self.output.setHtml(notice("Show the stored news, or fetch the latest from the feeds."))

    def _enable_actions(self) -> None:
        for button in self._actions:
            button.setEnabled(self.selected is not None and not self._runner.busy)

    def load(self, refresh: bool) -> None:
        """The dashboard. Summaries are written by the model, so even the
        stored news is loaded in the background."""
        days = self.days.value()

        self._run("Fetching the news" if refresh else "Loading the news",
                  lambda: self._controller.dashboard(days, refresh), self.show_dashboard)

    def show_dashboard(self, dashboard: Dashboard) -> None:
        """List the dashboard's events. The home page hands over the
        dashboard it fetched at start-up, so it is not fetched twice."""
        self.dashboard = dashboard
        self.event_list.set_cards([(str(event.id), event_card(event)) for event in dashboard.events])
        notes = list(dashboard.warnings)
        if dashboard.events:
            reports = sum(len(e.reports) for e in dashboard.events)
            notes.insert(0, f"The {len(dashboard.events)} most widely reported of "
                            f"{dashboard.total_events} events ({reports} reports).")
        else:
            notes.insert(0, EMPTY)
        self.message.setText("\n".join(notes))

    def open_event(self, event_id: UUID) -> None:
        self.selected = event_id
        self._enable_actions()
        self._run("Opening the event", lambda: self._controller.expand(event_id),
                  lambda expanded: self._show(results.expanded_event(expanded)))

    def _act(self, method: str, description: str, renderer: Callable[[Any], str]) -> None:
        event_id = self.selected
        if event_id is not None:
            self._run(description, lambda: getattr(self._controller, method)(event_id),
                      lambda result: self._show(renderer(result)))

    def save(self) -> None:
        if self.selected is None:
            return
        try:
            saved = self._controller.save(self.selected)
        except Exception as exc:
            self.message.setText(f"Error: {describe_error(exc)}")
            return
        self.message.setText(f"Saved to your workspace: {saved.title}")

    def _show(self, rich_text: str) -> None:
        self.output.setHtml(rich_text)
        self.message.clear()

    def _run(self, description: str, work: Callable[[], Any], done: Callable[[Any], None]) -> None:
        self.message.setText(f"{description}… model requests can take a minute.")
        self._runner.run(description, work, done, lambda exc: self.message.setText(f"Error: {describe_error(exc)}"))
