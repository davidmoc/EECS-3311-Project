"""The research page: the agent's requests in one place.

Stage 1's ``ResearchView`` and ``ResearchController``. The reader picks what
to do (ask a question, research, trace history, analyse, compare traditions,
get readings, build a learning path), types the topic, and may ask for more
or less detail or a general answer for this request only (F14). The request
runs in the background; the result is shown with its passages, and each
passage links to the text on the library page.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from praxis.app import Application
from praxis.gui import render, results
from praxis.gui.tasks import TaskRunner, describe_error
from praxis.reader_model import ExplanationDepth, ReaderProfile
from praxis.reader_model.personalization import RequestPreferences


@dataclass(frozen=True)
class Mode:
    key: str
    label: str
    placeholder: str
    feature: str
    uses_detail: bool = False  # whether its prompt follows the explanation depth
    topic_optional: bool = False


MODES = (
    Mode("ask", "Ask a question", "What do you want to know?", "F04", uses_detail=True),
    Mode("research", "Research in several steps", "Your research question", "F03", uses_detail=True),
    Mode("history", "Trace the history", "A topic, event or period", "F09"),
    Mode("analyze", "Marxist analysis", "An issue, event or question", "F11"),
    Mode("traditions", "Compare leftist traditions", "A topic or theoretical question", "F12"),
    Mode("recommend", "Recommend readings", "A topic (leave empty to use your interests)", "F07",
         topic_optional=True),
    Mode("path", "Build a learning path", "A topic you want to understand", "F08"),
)


class ResearchController:
    """Each method makes one request and returns the service's result."""

    def __init__(self, application: Application) -> None:
        self._application = application

    def _profile(self, preferences: RequestPreferences | None) -> ReaderProfile:
        profile = self._application.profiles.get_profile()
        return preferences.apply(profile) if preferences else profile

    def ask(self, question: str, preferences: RequestPreferences | None = None):
        return self._application.agent.answer_question(question, preferences)

    def research(self, objective: str, preferences: RequestPreferences | None = None):
        return self._application.agent.research(objective, preferences=preferences)

    def history(self, topic: str, preferences: RequestPreferences | None = None, broad: bool = False):
        return self._application.agent.explore_history(topic, allow_broad=broad, preferences=preferences)

    def analyze(self, issue: str, preferences: RequestPreferences | None = None, framework: str | None = None):
        return self._application.agent.analyze(issue, framework or None, preferences)

    def traditions(self, topic: str, preferences: RequestPreferences | None = None):
        return self._application.traditions.compare_traditions(topic, self._profile(preferences))

    def recommend(self, topic: str, preferences: RequestPreferences | None = None):
        profile = self._profile(preferences)
        service = self._application.recommendations
        return service.recommend_readings(topic, profile) if topic.strip() else service.recommend_next(profile)

    def path(self, topic: str, preferences: RequestPreferences | None = None):
        return self._application.prerequisites.build_learning_path(topic, self._profile(preferences))


RENDERERS: dict[str, Callable[[Any], str]] = {
    "ask": results.answer,
    "research": results.research,
    "history": results.history,
    "analyze": results.analysis,
    "traditions": results.traditions,
    "recommend": results.recommendations,
    "path": results.learning_path,
}


class ResearchView(QWidget):
    def __init__(
        self,
        controller: ResearchController,
        runner: TaskRunner,
        open_reading: Callable[[str, int], None] | None = None,
    ) -> None:
        """``open_reading(document_id, paragraph)`` shows a text on the
        library page when a passage link is clicked."""
        super().__init__()
        self._controller = controller
        self._runner = runner
        self._open_reading = open_reading
        self.result: Any = None

        self.mode_box = QComboBox()
        for mode in MODES:
            self.mode_box.addItem(f"{mode.label} ({mode.feature})", mode)
        self.mode_box.currentIndexChanged.connect(self._mode_changed)
        self.input = QLineEdit()
        self.input.returnPressed.connect(self.submit)
        self.run_button = QPushButton("Run")
        self.run_button.clicked.connect(self.submit)
        top = QHBoxLayout()
        top.addWidget(self.mode_box)
        top.addWidget(self.input, stretch=1)
        top.addWidget(self.run_button)

        self.framework = QLineEdit()
        self.framework.setPlaceholderText("Framework to apply (optional), e.g. the state as an instrument of class rule")
        self.broad = QCheckBox("Trace even if broad")
        self.detail_box = QComboBox()
        self.detail_box.addItem("Detail: as in my profile", None)
        for depth in ExplanationDepth:
            self.detail_box.addItem(f"Detail: {depth.value}", depth)
        self.general = QCheckBox("General answer (not adapted to me)")
        options = QHBoxLayout()
        for widget in (self.framework, self.broad, self.detail_box, self.general):
            options.addWidget(widget)
        options.addStretch()

        self.output = QTextBrowser()
        self.output.setOpenLinks(False)
        self.output.anchorClicked.connect(self._link_clicked)
        self.message = QLabel()
        self.message.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(options)
        layout.addWidget(self.output, stretch=1)
        layout.addWidget(self.message)

        runner.busy_changed.connect(lambda busy: self.run_button.setEnabled(not busy))
        self._mode_changed()

    @property
    def mode(self) -> Mode:
        return self.mode_box.currentData()

    def choose(self, key: str) -> None:
        self.mode_box.setCurrentIndex(next(i for i, m in enumerate(MODES) if m.key == key))

    def _mode_changed(self) -> None:
        mode = self.mode
        self.input.setPlaceholderText(mode.placeholder)
        self.framework.setVisible(mode.key == "analyze")
        self.broad.setVisible(mode.key == "history")
        self.detail_box.setVisible(mode.uses_detail)
        self.general.setVisible(mode.key != "path")

    def preferences(self) -> RequestPreferences | None:
        depth = self.detail_box.currentData() if self.mode.uses_detail else None
        general = self.general.isChecked() and self.general.isVisibleTo(self)
        if depth is None and not general:
            return None
        return RequestPreferences(depth=depth, personalized=not general)

    def submit(self) -> None:
        mode, text = self.mode, " ".join(self.input.text().split())
        if not text and not mode.topic_optional:
            self.message.setText("Type a question or topic first.")
            return
        preferences = self.preferences()
        method = getattr(self._controller, mode.key)
        extra: dict[str, Any] = {}
        if mode.key == "analyze":
            extra["framework"] = self.framework.text().strip()
        elif mode.key == "history":
            extra["broad"] = self.broad.isChecked()

        def done(result: Any) -> None:
            self.result = result
            self.output.setMarkdown(RENDERERS[mode.key](result))
            self.message.clear()

        def failed(exc: Exception) -> None:
            self.output.clear()
            self.message.setText(f"Error: {describe_error(exc)}")

        self.message.setText("Working… model requests can take a minute.")
        self._runner.run(mode.label, lambda: method(text, preferences, **extra), done, failed)

    def _link_clicked(self, url: QUrl) -> None:
        target = render.parse_read_link(url.toString())
        if target is not None and self._open_reading is not None:
            self._open_reading(*target)
