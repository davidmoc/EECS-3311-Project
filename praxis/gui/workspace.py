"""The workspace page: saved texts, passages, answers, research, comparisons,
events and notes, to browse, search and continue from (F15, UC15).

Stage 1's ``WorkspaceView`` and ``WorkspaceController``. "Continue" goes to
the page the item came from: a text opens where the reader stopped, a
research session on the past research page, a comparison on the compare
page, an event on the news page. If a saved text has left the library, the
saved copy is what remains, and the reader is told.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from praxis.app import Application
from praxis.gui.render import escape
from praxis.gui.tasks import TaskRunner, describe_error
from praxis.gui.widgets import lock_while_busy
from praxis.library import LibraryError
from praxis.workspace import SavedItem, SavedItemKind

GONE = "The original text is no longer in the library; the saved copy is what remains."


@dataclass(frozen=True)
class Resume:
    """Where continuing from a saved item leads."""

    kind: str  # "text", "research", "comparison", "event" or "" (a note)
    target: UUID | None = None
    paragraph: int = 1
    available: bool = True


class WorkspaceController:
    def __init__(self, application: Application) -> None:
        self._application = application
        self._workspace = application.workspace

    def items(self, query: str = "", kind: SavedItemKind | None = None) -> list[SavedItem]:
        found = self._workspace.search(query) if query.strip() else self._workspace.get_workspace().newest_first()
        return [item for item in found if kind is None or item.kind is kind]

    def add_note(self, title: str, text: str) -> SavedItem:
        if not title.strip():
            raise ValueError("Give the note a title.")
        return self._workspace.add_note(title.strip(), text.strip())

    def remove(self, item: SavedItem) -> SavedItem:
        return self._workspace.remove_item(str(item.id))

    def resume(self, item: SavedItem) -> Resume:
        workspace = self._workspace
        if (research := workspace.research_session_of(item)) is not None:
            return Resume("research", research)
        if (comparison := workspace.comparison_of(item)) is not None:
            return Resume("comparison", comparison)
        if (event := workspace.event_of(item)) is not None:
            return Resume("event", event)
        document_id = workspace.document_id_of(item)
        if document_id is None:
            return Resume("")
        try:
            self._application.library.get_document(document_id)
        except LibraryError:
            return Resume("text", document_id, available=False)
        paragraph = workspace.paragraph_of(item)
        if paragraph is None:
            record = self._application.profiles.get_profile().history.get(document_id)
            paragraph = record.furthest_paragraph + 1 if record and not record.completed else 1
        return Resume("text", document_id, paragraph)


_CONTINUE_LABELS = {
    "text": "Continue reading",
    "research": "Open the research",
    "comparison": "Open the comparison",
    "event": "Open the event",
}


class WorkspaceView(QWidget):
    def __init__(
        self,
        controller: WorkspaceController,
        runner: TaskRunner,
        go_to: Callable[[Resume], None] | None = None,
    ) -> None:
        """``go_to`` shows the page a saved item continues on."""
        super().__init__()
        self._controller = controller
        self._go_to = go_to
        self.item: SavedItem | None = None
        self.resume: Resume | None = None

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search your workspace…")
        self.search_box.textChanged.connect(lambda _text: self.refresh())
        self.kind_box = QComboBox()
        self.kind_box.addItem("Everything", None)
        for kind in SavedItemKind:
            self.kind_box.addItem(kind.value, kind)
        self.kind_box.currentIndexChanged.connect(lambda _index: self.refresh())
        self.item_list = QListWidget()
        self.item_list.itemClicked.connect(lambda item: self.open_item(item.data(Qt.ItemDataRole.UserRole)))

        self.note_title = QLineEdit()
        self.note_title.setPlaceholderText("New note: title")
        self.note_text = QPlainTextEdit()
        self.note_text.setPlaceholderText("Note")
        self.note_text.setMaximumHeight(90)
        self.note_button = QPushButton("Save note")
        self.note_button.clicked.connect(self.add_note)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        for widget in (self.search_box, self.kind_box):
            left_layout.addWidget(widget)
        left_layout.addWidget(self.item_list, stretch=1)
        for widget in (self.note_title, self.note_text, self.note_button):
            left_layout.addWidget(widget)

        self.output = QTextBrowser()
        self.continue_button = QPushButton("Continue")
        self.continue_button.clicked.connect(self.continue_from)
        self.remove_button = QPushButton("Remove from workspace")
        self.remove_button.clicked.connect(self.remove)
        buttons = QHBoxLayout()
        buttons.addWidget(self.continue_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch()
        self.message = QLabel()
        self.message.setWordWrap(True)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.output, stretch=1)
        right_layout.addLayout(buttons)
        right_layout.addWidget(self.message)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 2)
        QVBoxLayout(self).addWidget(splitter)
        lock_while_busy(runner, self.item_list, self.note_button, self.continue_button, self.remove_button)
        runner.busy_changed.connect(lambda busy: busy or self._update_buttons())
        self.refresh()

    def refresh(self) -> None:
        self.item_list.clear()
        self._items = {str(i.id): i for i in self._controller.items(self.search_box.text(), self.kind_box.currentData())}
        for key, saved in self._items.items():
            entry = QListWidgetItem(f"[{saved.kind.value}] {saved.title}\n{saved.saved_at:%Y-%m-%d %H:%M}"
                                    + (f" · {', '.join(saved.tags)}" if saved.tags else ""))
            entry.setData(Qt.ItemDataRole.UserRole, key)
            self.item_list.addItem(entry)
        if not self._items:
            self.output.setMarkdown("Nothing saved yet." if not self.search_box.text().strip()
                                    else "Nothing in your workspace matches.")
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.remove_button.setEnabled(self.item is not None)
        can_continue = self.resume is not None and bool(self.resume.kind) and self.resume.available
        self.continue_button.setEnabled(can_continue)
        if self.resume is not None and self.resume.kind:
            self.continue_button.setText(_CONTINUE_LABELS[self.resume.kind])

    def open_item(self, key: str) -> None:
        saved = self._items[key]
        try:
            self.resume = self._controller.resume(saved)
        except Exception as exc:
            self.message.setText(f"Error: {describe_error(exc)}")
            return
        self.item = saved
        parts = [f"## [{saved.kind.value}] {escape(saved.title)}"]
        if saved.content:
            parts.append(escape(saved.content))
        if saved.note:
            parts.append(f"**Note:** {escape(saved.note)}")
        self.output.setMarkdown("\n\n".join(parts))
        self.message.setText("" if self.resume.available else GONE)
        self._update_buttons()

    def continue_from(self) -> None:
        if self.resume is not None and self.resume.kind and self._go_to is not None:
            self._go_to(self.resume)

    def add_note(self) -> None:
        try:
            self._controller.add_note(self.note_title.text(), self.note_text.toPlainText())
        except Exception as exc:
            self.message.setText(f"Error: {describe_error(exc)}")
            return
        self.note_title.clear()
        self.note_text.clear()
        self.message.setText("Note saved.")
        self.refresh()

    def remove(self) -> None:
        if self.item is None:
            return
        removed = self._controller.remove(self.item)
        self.item, self.resume = None, None
        self.output.clear()
        self.message.setText(f"Removed: {removed.title}")
        self.refresh()
