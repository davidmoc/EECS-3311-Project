"""The compare page: how two to four texts treat one subject (F10, UC10,
SD06), and the comparisons made before.

The reader ticks the texts and names the subject; the agent retrieves each
text's passages on it and the model compares them. Every comparison is
stored and can be reopened from the list below.
"""

from __future__ import annotations

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
from praxis.comparison import SourceComparison, SourceSelection
from praxis.documents import Document
from praxis.gui import results
from praxis.gui.tasks import TaskRunner, describe_error
from praxis.gui.widgets import OpenReading, item_list, lock_while_busy, result_browser
from praxis.persistence.comparisons import ComparisonSummary


class CompareController:
    def __init__(self, application: Application) -> None:
        self._application = application
        self._agent = application.agent

    def texts(self) -> list[Document]:
        return self._application.library.browse()

    def compare(self, document_ids: list[str], subject: str) -> SourceComparison:
        selections = [
            SourceSelection.of(self._application.library.get_document(document_id))
            for document_id in document_ids
        ]
        return self._agent.compare_sources(selections, subject)

    def comparisons(self) -> list[ComparisonSummary]:
        return self._agent.list_comparisons(limit=100)

    def open(self, comparison_id: UUID) -> SourceComparison:
        return self._agent.get_comparison(comparison_id)


class CompareView(QWidget):
    def __init__(self, controller: CompareController, runner: TaskRunner, open_reading: OpenReading | None = None) -> None:
        super().__init__()
        self._controller = controller
        self._runner = runner

        self.text_list = QListWidget()
        self.subject = QLineEdit()
        self.subject.setPlaceholderText("What to compare them on, e.g. the peasantry")
        self.subject.returnPressed.connect(self.compare)
        self.compare_button = QPushButton("Compare (AI)")
        self.compare_button.clicked.connect(self.compare)
        self.history = item_list()
        self.history.itemClicked.connect(
            lambda item: self.open_comparison(UUID(item.data(Qt.ItemDataRole.UserRole)))
        )

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Tick two to four texts:"))
        left_layout.addWidget(self.text_list, stretch=2)
        left_layout.addWidget(QLabel("Earlier comparisons:"))
        left_layout.addWidget(self.history, stretch=1)

        self.output = result_browser(open_reading)
        self.message = QLabel()
        self.message.setWordWrap(True)
        row = QHBoxLayout()
        row.addWidget(self.subject, stretch=1)
        row.addWidget(self.compare_button)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addLayout(row)
        right_layout.addWidget(self.output, stretch=1)
        right_layout.addWidget(self.message)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 3)
        QVBoxLayout(self).addWidget(splitter)
        lock_while_busy(runner, self.text_list, self.history, self.compare_button)
        self.refresh()

    def refresh(self) -> None:
        ticked = set(self.chosen())
        self.text_list.clear()
        for document in self._controller.texts():
            item = QListWidgetItem(f"{document.title} — {document.author}")
            item.setData(Qt.ItemDataRole.UserRole, str(document.id))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if str(document.id) in ticked else Qt.CheckState.Unchecked)
            self.text_list.addItem(item)
        self.history.clear()
        for summary in self._controller.comparisons():
            item = QListWidgetItem(f"{summary.subject}\n{' / '.join(summary.titles)}")
            item.setData(Qt.ItemDataRole.UserRole, str(summary.id))
            self.history.addItem(item)

    def chosen(self) -> list[str]:
        return [
            self.text_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.text_list.count())
            if self.text_list.item(row).checkState() == Qt.CheckState.Checked
        ]

    def compare(self) -> None:
        document_ids, subject = self.chosen(), self.subject.text().strip()

        def done(comparison: Any) -> None:
            self.output.setHtml(results.comparison(comparison))
            self.message.clear()
            self.refresh()

        self.message.setText("Comparing… model requests can take a minute.")
        self._runner.run(
            "Comparing the texts", lambda: self._controller.compare(document_ids, subject), done,
            lambda exc: self.message.setText(f"Error: {describe_error(exc)}"),
        )

    def open_comparison(self, comparison_id: UUID) -> None:
        try:
            self.output.setHtml(results.comparison(self._controller.open(comparison_id)))
            self.message.clear()
        except Exception as exc:
            self.message.setText(f"Error: {describe_error(exc)}")
