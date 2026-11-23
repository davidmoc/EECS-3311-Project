"""The first page: what the application can do right now, and the
bundled library to load if it is empty (F05)."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from praxis.app import Application, bundled_library_service
from praxis.gui.tasks import TaskRunner, describe_error
from praxis.library import ImportReport

NO_MODEL = (
    "No language model is configured: passages are still found, but nothing "
    "is explained. Copy .env.example to .env and set OPENAI_API_KEY."
)


@dataclass(frozen=True)
class HomeStatus:
    texts: int
    has_model: bool


class HomeController:
    def __init__(self, application: Application) -> None:
        self._application = application

    def status(self) -> HomeStatus:
        return HomeStatus(len(self._application.library.browse()), self._application.llm is not None)

    def load_bundled_library(self) -> ImportReport:
        return bundled_library_service(self._application).import_catalogue()


class HomeView(QWidget):
    def __init__(self, controller: HomeController, runner: TaskRunner) -> None:
        super().__init__()
        self._controller = controller
        self._runner = runner
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.load_button = QPushButton("Load the bundled library")
        self.load_button.clicked.connect(self.load_library)
        runner.busy_changed.connect(lambda busy: self.load_button.setEnabled(not busy))

        layout = QVBoxLayout(self)
        title = QLabel("<h1>Praxis</h1><p>Research current events, history and political "
                       "theory from primary sources, with an AI agent that cites them.</p>")
        title.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(self.summary)
        layout.addWidget(self.load_button)
        layout.addWidget(self.message)
        layout.addStretch()
        self.refresh()

    def refresh(self) -> None:
        status = self._controller.status()
        lines = [f"The library holds {status.texts} text{'s' if status.texts != 1 else ''}."]
        lines.append("A language model is configured." if status.has_model else NO_MODEL)
        self.summary.setText("\n\n".join(lines))
        self.load_button.setVisible(status.texts == 0)

    def load_library(self) -> None:
        def done(report: ImportReport) -> None:
            self.message.setText(f"{len(report.imported)} imported, {len(report.failures)} skipped.")
            self.refresh()

        self._runner.run(
            "Loading the bundled library", self._controller.load_bundled_library, done,
            lambda exc: self.message.setText(f"Error: {describe_error(exc)}"),
        )
