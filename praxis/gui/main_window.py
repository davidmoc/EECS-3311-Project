"""The main window: a list of pages on the left, the chosen page on the right.

Each page is a View from Stage 1's MVC design (``LibraryView``,
``ProfileView``, …). Views collect input and show results; their Controllers
call the application's services. The window only switches between pages and
shows what the task runner is doing.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QProgressBar,
    QStackedWidget,
    QWidget,
)

from praxis.gui.tasks import TaskRunner

TITLE = "Praxis"


class MainWindow(QMainWindow):
    def __init__(self, runner: TaskRunner) -> None:
        super().__init__()
        self.setWindowTitle(TITLE)
        self.resize(1200, 800)
        self._pages: dict[str, QWidget] = {}

        self._navigation = QListWidget()
        self._navigation.setFixedWidth(190)
        self._stack = QStackedWidget()
        self._navigation.currentRowChanged.connect(self._stack.setCurrentIndex)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.addWidget(self._navigation)
        layout.addWidget(self._stack, stretch=1)
        self.setCentralWidget(central)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # no known length: a moving bar
        self._progress.setMaximumWidth(160)
        self._progress.hide()
        self.statusBar().addPermanentWidget(self._progress)
        runner.status.connect(self.statusBar().showMessage)
        runner.busy_changed.connect(self._progress.setVisible)

    def add_page(self, title: str, page: QWidget) -> None:
        self._pages[title] = page
        self._navigation.addItem(title)
        self._stack.addWidget(page)
        if self._navigation.currentRow() < 0:
            self._navigation.setCurrentRow(0)

    def show_page(self, title: str) -> QWidget:
        page = self._pages[title]
        self._navigation.setCurrentRow(list(self._pages).index(title))
        return page

    def page(self, title: str) -> QWidget:
        return self._pages[title]

    @property
    def page_titles(self) -> list[str]:
        return list(self._pages)

    @property
    def current_title(self) -> str:
        return list(self._pages)[self._stack.currentIndex()]
