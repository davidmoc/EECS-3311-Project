"""The past research page: reopen stored research and keep working on it
(F03, UC15 "Save and Resume Research").

Every research run is stored. Here the reader picks one, sees it as it was
left, and can run another round (with a new focus or the steps a limit left
unrun), analyse its sources with Marxist theory (F11), compare the texts
behind it (F10), or compare leftist traditions on its question (F12).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from praxis.app import Application
from praxis.gui import results
from praxis.gui.tasks import TaskRunner, describe_error
from praxis.gui.widgets import OpenReading, lock_while_busy, result_browser
from praxis.persistence.research import ResearchSessionSummary


class SessionsController:
    def __init__(self, application: Application) -> None:
        self._application = application
        self._agent = application.agent

    def sessions(self) -> list[ResearchSessionSummary]:
        return self._agent.list_research(limit=100)

    def open(self, session_id: UUID):
        return self._agent.get_research(session_id)

    def continue_research(self, session_id: UUID, focus: str = ""):
        return self._agent.continue_research(session_id, focus or None)

    def analyze(self, session_id: UUID):
        return self._agent.analyze_research(session_id)

    def compare_sources(self, session_id: UUID):
        return self._agent.compare_research_sources(session_id)

    def traditions(self, session_id: UUID):
        research = self._agent.get_research(session_id)
        return self._application.traditions.compare_traditions(
            research.objective, self._application.profiles.get_profile(),
            research_session=str(session_id)[:8],
        )


def describe(summary: ResearchSessionSummary) -> str:
    state = "incomplete" if summary.incomplete else summary.status.value
    rounds = f", {summary.rounds} rounds" if summary.rounds > 1 else ""
    return (f"{summary.objective}\n{summary.updated_at:%Y-%m-%d %H:%M} · "
            f"{summary.source_count} sources{rounds} · {state}")


class SessionsView(QWidget):
    def __init__(
        self,
        controller: SessionsController,
        runner: TaskRunner,
        open_reading: OpenReading | None = None,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._runner = runner

        self.session_list = QListWidget()
        self.session_list.itemClicked.connect(self._open_item)
        self.output = result_browser(open_reading)

        self.focus = QLineEdit()
        self.focus.setPlaceholderText("Follow up on… (optional; leave empty to run the unrun steps)")
        self.continue_button = QPushButton("Continue research")
        self.continue_button.clicked.connect(self.continue_research)
        self.analyze_button = QPushButton("Marxist analysis (F11)")
        self.analyze_button.clicked.connect(lambda: self._follow_up("analyze", "Analysing", results.analysis))
        self.compare_button = QPushButton("Compare its texts (F10)")
        self.compare_button.clicked.connect(
            lambda: self._follow_up("compare_sources", "Comparing", results.comparison)
        )
        self.traditions_button = QPushButton("Compare traditions (F12)")
        self.traditions_button.clicked.connect(
            lambda: self._follow_up("traditions", "Comparing traditions", results.traditions)
        )
        continue_row = QHBoxLayout()
        continue_row.addWidget(self.focus, stretch=1)
        continue_row.addWidget(self.continue_button)
        actions = QHBoxLayout()
        for button in (self.analyze_button, self.compare_button, self.traditions_button):
            actions.addWidget(button)
        actions.addStretch()
        self.message = QLabel()
        self.message.setWordWrap(True)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.output, stretch=1)
        right_layout.addLayout(continue_row)
        right_layout.addLayout(actions)
        right_layout.addWidget(self.message)
        splitter = QSplitter()
        splitter.addWidget(self.session_list)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 3)
        QVBoxLayout(self).addWidget(splitter)

        self._actions = (self.continue_button, self.analyze_button, self.compare_button, self.traditions_button)
        lock_while_busy(runner, self.session_list)
        # The actions also need a session chosen, so they are not simply unlocked.
        runner.busy_changed.connect(lambda _busy: self._enable_actions())
        self.selected: UUID | None = None
        self.refresh()

    def refresh(self) -> None:
        self.session_list.clear()
        sessions = self._controller.sessions()
        for summary in sessions:
            item = QListWidgetItem(describe(summary))
            item.setData(Qt.ItemDataRole.UserRole, str(summary.id))
            self.session_list.addItem(item)
        if not sessions:
            self.output.setMarkdown("No research yet. Run some from the Research page; every run is kept here.")
        self._enable_actions()

    def _enable_actions(self) -> None:
        for button in self._actions:
            button.setEnabled(self.selected is not None and not self._runner.busy)

    def _open_item(self, item: QListWidgetItem) -> None:
        self.open_session(UUID(item.data(Qt.ItemDataRole.UserRole)))

    def open_session(self, session_id: UUID) -> None:
        if self._runner.busy:
            return
        try:
            result = self._controller.open(session_id)
        except Exception as exc:
            self.message.setText(f"Error: {describe_error(exc)}")
            return
        self.selected = session_id
        self.output.setMarkdown(results.research(result))
        self.message.clear()
        self._enable_actions()

    def continue_research(self) -> None:
        session_id, focus = self.selected, self.focus.text().strip()
        if session_id is None:
            return

        def done(result: Any) -> None:
            self.output.setMarkdown(results.research(result))
            self.message.clear()
            self.focus.clear()
            self.refresh()

        self._run("Continuing the research", lambda: self._controller.continue_research(session_id, focus), done)

    def _follow_up(self, method: str, description: str, renderer: Callable[[Any], str]) -> None:
        session_id = self.selected
        if session_id is None:
            return

        def done(result: Any) -> None:
            self.output.setMarkdown(renderer(result))
            self.message.setText("Select the session again to see the research itself.")

        self._run(description, lambda: getattr(self._controller, method)(session_id), done)

    def _run(self, description: str, work: Callable[[], Any], done: Callable[[Any], None]) -> None:
        self.message.setText("Working… model requests can take a minute.")
        self._runner.run(description, work, done, lambda exc: self.message.setText(f"Error: {describe_error(exc)}"))
