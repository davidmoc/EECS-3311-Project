"""The profile page: see and correct what the system believes about you
(F13, UC13), and set how it adapts to you (F14).

Stage 1's ``ProfileView`` and ``ProfileController``. Every belief is shown
with where it came from, so inferred knowledge can be told apart from what
the reader stated, and corrected or removed.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from praxis.app import Application
from praxis.gui.library import lock_while_busy
from praxis.gui.tasks import TaskRunner, describe_error
from praxis.reader_model import ExplanationDepth, KnowledgeArea, KnowledgeLevel, ReaderProfile

SPARSE = (
    "Nothing is known about you yet, so answers are not adapted to you. "
    "Read, research, or state what you know below."
)


def origin(area: KnowledgeArea) -> str:
    if not area.is_inferred:
        return "you said"
    return f"inferred from {area.evidence} activit{'y' if area.evidence == 1 else 'ies'}"


class ProfileController:
    def __init__(self, application: Application) -> None:
        self._profiles = application.profiles

    def profile(self) -> ReaderProfile:
        return self._profiles.get_profile()

    def state_knowledge(self, topic: str, level: KnowledgeLevel) -> None:
        if not topic.strip():
            raise ValueError("Name the topic first.")
        self._profiles.correct_knowledge_assessment(topic, level)

    def forget_knowledge(self, topic: str) -> bool:
        return self._profiles.remove_knowledge_assessment(topic)

    def add_interest(self, topic: str) -> None:
        if not topic.strip():
            raise ValueError("Name the interest first.")
        self._profiles.add_interest(topic)

    def remove_interest(self, topic: str) -> bool:
        return self._profiles.remove_interest(topic)

    def set_depth(self, depth: ExplanationDepth) -> None:
        self._profiles.set_explanation_depth(depth)

    def set_personalization(self, enabled: bool) -> None:
        self._profiles.set_personalization(enabled)

    def set_background(self, text: str) -> None:
        self._profiles.set_background(text.strip())


class ProfileView(QWidget):
    def __init__(self, controller: ProfileController, runner: TaskRunner) -> None:
        super().__init__()
        self._controller = controller
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        self.message = QLabel()
        self.message.setWordWrap(True)

        # Knowledge (F13): what the system believes you know, and why.
        self.knowledge = QTableWidget(0, 3)
        self.knowledge.setHorizontalHeaderLabels(["Topic", "Level", "Where it came from"])
        self.knowledge.horizontalHeader().setStretchLastSection(True)
        self.knowledge.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.knowledge.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.knowledge.itemSelectionChanged.connect(self._fill_from_selection)
        self.topic_box = QLineEdit()
        self.topic_box.setPlaceholderText("Topic, e.g. surplus value")
        self.level_box = QComboBox()
        for level in KnowledgeLevel:
            self.level_box.addItem(level.name.lower(), level)
        self.state_button = QPushButton("Set my level")
        self.state_button.clicked.connect(self.state_knowledge)
        self.forget_button = QPushButton("Forget this topic")
        self.forget_button.clicked.connect(self.forget_knowledge)
        knowledge_row = QHBoxLayout()
        for widget in (self.topic_box, self.level_box, self.state_button, self.forget_button):
            knowledge_row.addWidget(widget)
        knowledge_group = QGroupBox("Knowledge")
        knowledge_layout = QVBoxLayout(knowledge_group)
        knowledge_layout.addWidget(self.knowledge)
        knowledge_layout.addLayout(knowledge_row)

        # Interests.
        self.interests = QListWidget()
        self.interest_box = QLineEdit()
        self.interest_box.setPlaceholderText("Add an interest")
        self.interest_box.returnPressed.connect(self.add_interest)
        self.add_interest_button = QPushButton("Add")
        self.add_interest_button.clicked.connect(self.add_interest)
        self.remove_interest_button = QPushButton("Remove selected")
        self.remove_interest_button.clicked.connect(self.remove_interest)
        interest_row = QHBoxLayout()
        for widget in (self.interest_box, self.add_interest_button, self.remove_interest_button):
            interest_row.addWidget(widget)
        interests_group = QGroupBox("Interests (removed ones are not inferred again)")
        interests_layout = QVBoxLayout(interests_group)
        interests_layout.addWidget(self.interests)
        interests_layout.addLayout(interest_row)

        # Reading history.
        self.reading = QListWidget()
        reading_group = QGroupBox("Reading")
        QVBoxLayout(reading_group).addWidget(self.reading)

        # Preferences (F14).
        self.depth_box = QComboBox()
        for depth in ExplanationDepth:
            self.depth_box.addItem(depth.value, depth)
        self.depth_box.activated.connect(self.set_depth)
        self.personalize_box = QCheckBox("Adapt explanations to me")
        self.personalize_box.clicked.connect(self.set_personalization)
        self.background_box = QLineEdit()
        self.background_box.setPlaceholderText("Anything the agent should know about you")
        self.background_button = QPushButton("Save")
        self.background_button.clicked.connect(self.set_background)
        background_row = QHBoxLayout()
        background_row.addWidget(self.background_box)
        background_row.addWidget(self.background_button)
        preferences = QGroupBox("Preferences")
        form = QFormLayout(preferences)
        form.addRow("Explanation detail", self.depth_box)
        form.addRow("", self.personalize_box)
        form.addRow("Your background", background_row)

        lower = QHBoxLayout()
        lower.addWidget(interests_group)
        lower.addWidget(reading_group)
        layout = QVBoxLayout(self)
        layout.addWidget(self.notice)
        layout.addWidget(knowledge_group, stretch=2)
        layout.addLayout(lower, stretch=1)
        layout.addWidget(preferences)
        layout.addWidget(self.message)

        lock_while_busy(
            runner, self.state_button, self.forget_button, self.add_interest_button,
            self.remove_interest_button, self.depth_box, self.personalize_box, self.background_button,
        )
        self.refresh()

    def refresh(self) -> None:
        profile = self._controller.profile()
        self.notice.setText(SPARSE if profile.is_sparse else "")
        self.notice.setVisible(profile.is_sparse)
        areas = sorted(profile.knowledge.areas.values(), key=lambda a: a.topic)
        self.knowledge.setRowCount(len(areas))
        for row, area in enumerate(areas):
            for column, text in enumerate((area.topic, area.level.name.lower(), origin(area))):
                self.knowledge.setItem(row, column, QTableWidgetItem(text))
        self.interests.clear()
        self.interests.addItems(profile.interests.top(20))
        self.reading.clear()
        for record in profile.history.recent(20):
            status = "finished" if record.completed else f"{record.progress:.0%}"
            self.reading.addItem(f"{record.title}: {status}")
        self.depth_box.setCurrentIndex(self.depth_box.findData(profile.explanation_depth))
        self.personalize_box.setChecked(profile.personalization_enabled)
        self.background_box.setText(profile.background)

    def _fill_from_selection(self) -> None:
        row = self.knowledge.currentRow()
        if row >= 0 and self.knowledge.item(row, 0) is not None:
            self.topic_box.setText(self.knowledge.item(row, 0).text())
            self.level_box.setCurrentText(self.knowledge.item(row, 1).text())

    def _change(self, action, done_message: str) -> None:
        try:
            result = action()
        except Exception as exc:
            self.message.setText(f"Error: {describe_error(exc)}")
            return
        self.message.setText(done_message if result is not False else "Nothing to change.")
        self.refresh()

    def state_knowledge(self) -> None:
        topic, level = self.topic_box.text(), self.level_box.currentData()
        self._change(
            lambda: self._controller.state_knowledge(topic, level),
            f"Recorded: {topic.strip().lower()} = {level.name.lower()} (stated by you).",
        )

    def forget_knowledge(self) -> None:
        topic = self.topic_box.text()
        self._change(lambda: self._controller.forget_knowledge(topic), f"Removed {topic.strip().lower()}.")

    def add_interest(self) -> None:
        topic = self.interest_box.text()
        self._change(lambda: self._controller.add_interest(topic), "Interest added.")
        self.interest_box.clear()

    def remove_interest(self) -> None:
        item = self.interests.currentItem()
        if item is not None:
            self._change(lambda: self._controller.remove_interest(item.text()), "Interest removed.")

    def set_depth(self) -> None:
        depth = self.depth_box.currentData()
        self._change(lambda: self._controller.set_depth(depth), f"Explanation detail set to {depth.value}.")

    def set_personalization(self) -> None:
        enabled = self.personalize_box.isChecked()
        self._change(
            lambda: self._controller.set_personalization(enabled),
            f"Personalization {'on' if enabled else 'off'}.",
        )

    def set_background(self) -> None:
        text = self.background_box.text()
        self._change(lambda: self._controller.set_background(text), "Background saved.")
