"""The learning paths page: stored paths and progress through them (F08,
UC08 steps 7–8).

Each step is marked from the path itself: its "Mark done", "I already
know this", "Skip" and "Undo" links. Marking a step done or already known publishes ``PrerequisiteMarkedKnown``,
so the reader model records the topic as known (SD07's Observer), exactly
as ``praxis path mark`` does. Skipping publishes nothing.
"""

from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QListWidgetItem,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from praxis.app import Application
from praxis.gui import results
from praxis.gui.render import notice
from praxis.gui.tasks import TaskRunner, describe_error
from praxis.gui.widgets import OpenReading, item_list, lock_while_busy, result_browser
from praxis.persistence.learning_paths import LearningPathSummary
from praxis.reader_model.events import PrerequisiteMarkedKnown
from praxis.reading import LearningPath, StepStatus

class PathsController:
    def __init__(self, application: Application) -> None:
        self._application = application
        self._paths = application.prerequisites

    def paths(self) -> list[LearningPathSummary]:
        return self._paths.list_paths(100)

    def open(self, path_id: UUID) -> LearningPath:
        return self._paths.get_path(path_id)

    def mark(self, path_id: UUID, step: int, status: StepStatus) -> LearningPath:
        path = self._paths.set_step_status(path_id, step, status)
        if status in (StepStatus.DONE, StepStatus.KNOWN):
            self._application.events.publish(PrerequisiteMarkedKnown(path.steps[step - 1].name))
        return path


class PathsView(QWidget):
    def __init__(self, controller: PathsController, runner: TaskRunner, open_reading: OpenReading | None = None) -> None:
        super().__init__()
        self._controller = controller
        self.path: LearningPath | None = None

        self.path_list = item_list()
        self.path_list.itemClicked.connect(
            lambda item: self.open_path(UUID(item.data(Qt.ItemDataRole.UserRole)))
        )
        self.output = result_browser(open_reading, self._link)
        self.message = QLabel()
        self.message.setWordWrap(True)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.output, stretch=1)
        right_layout.addWidget(self.message)
        splitter = QSplitter()
        splitter.addWidget(self.path_list)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 3)
        QVBoxLayout(self).addWidget(splitter)

        self._runner = runner
        lock_while_busy(runner, self.path_list)
        self.refresh()

    def refresh(self) -> None:
        self.path_list.clear()
        summaries = self._controller.paths()
        for summary in summaries:
            item = QListWidgetItem(f"{summary.target}\n{summary.settled_count}/{summary.step_count} steps")
            item.setData(Qt.ItemDataRole.UserRole, str(summary.id))
            self.path_list.addItem(item)
        if not summaries:
            self.output.setHtml(notice("No learning paths yet. Build one on the Research page."))

    def open_path(self, path_id: UUID) -> None:
        try:
            self._show(self._controller.open(path_id))
        except Exception as exc:
            self.message.setText(f"Error: {describe_error(exc)}")

    def _show(self, path: LearningPath, keep_position: bool = False) -> None:
        """Show ``path``; after marking a step, at the same place."""
        self.path = path
        position = self.output.verticalScrollBar().value()
        self.output.setHtml(results.learning_path(path, interactive=True))
        if keep_position:
            self.output.verticalScrollBar().setValue(position)

    def _link(self, url: str) -> None:
        """A step's "Mark done", "I already know this", "Skip" or "Undo"."""
        action = results.parse_step_link(url)
        if action is not None and not self._runner.busy:
            self.mark(*action)

    def mark(self, step: int, status: StepStatus) -> None:
        if self.path is None:
            return
        try:
            path = self._controller.mark(self.path.id, step, status)
        except Exception as exc:
            self.message.setText(f"Error: {describe_error(exc)}")
            return
        name = path.steps[step - 1].name
        note = f"Step {step} ({name}): {status.value}."
        if status in (StepStatus.DONE, StepStatus.KNOWN):
            note += f" Your reader model now counts you as knowing {name}."
        self.message.setText(note)
        self._show(path, keep_position=True)
        self.refresh()
