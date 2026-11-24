"""The library page: find texts (F05), read them, and ask for AI
annotations of a paragraph (F06).

Stage 1's ``LibraryView`` and ``ReaderView`` share one page here, one at a
time: the list of texts until one is chosen, then the reader, which fills
the page. ``LibraryController`` finds texts; ``ReadingController`` opens
them, records how far the reader got through the ``LearningEventBus``
(F13), and requests annotations.

In the reader, clicking a paragraph's number opens the "Ask about" menu of
annotation types. The request runs in the background; the reader shows that
it is running under the paragraph, then the annotation in its place.
"""

from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from praxis.app import Application
from praxis.documents import Annotation, AnnotationType, Document
from praxis.gui.reader import ReaderPane, ReaderText
from praxis.gui.tasks import TaskRunner, describe_error
from praxis.gui.widgets import item_list, lock_while_busy
from praxis.reader_model.events import DocumentRead
from praxis.reader_model.personalization import RequestPreferences
from praxis.reading import AnnotationResult

ALL_TOPICS = "All topics"


class LibraryController:
    def __init__(self, application: Application) -> None:
        self._library = application.library

    def texts(self, topic: str | None = None) -> list[Document]:
        return self._library.browse(topic)

    def search(self, query: str) -> list[Document]:
        query = query.strip()
        return self._library.search(query) if query else self._library.browse()

    def topics(self) -> list[tuple[str, int]]:
        return self._library.topics()


class ReadingController:
    def __init__(self, application: Application) -> None:
        self._application = application

    def open_text(self, document_id: UUID | str) -> ReaderText:
        """The whole text, with the annotations stored for it."""
        document = self._application.library.get_document(document_id)
        by_passage: dict[UUID, list[Annotation]] = {}
        for annotation in self._application.annotations.annotations_for(document):
            by_passage.setdefault(annotation.passage_id, []).append(annotation)
        return ReaderText(document, document.passages(), by_passage)

    def record_progress(self, document: Document, paragraph: int) -> None:
        """The reader reached ``paragraph``, as ``library read`` records."""
        self._application.events.publish(DocumentRead(document, paragraph))

    def save_text(self, document: Document):
        return self._application.workspace.save_document(document)

    def save_paragraph(self, document: Document, paragraph: int):
        return self._application.workspace.save_passage(document, document.paragraph(paragraph))

    def annotate(
        self,
        document: Document,
        paragraph: int,
        annotation_type: AnnotationType,
        preferences: RequestPreferences | None = None,
    ) -> AnnotationResult:
        profile = self._application.profiles.get_profile()
        if preferences is not None:
            profile = preferences.apply(profile)
        return self._application.annotations.generate_annotation(
            document, document.paragraph(paragraph), annotation_type, profile
        )


class LibraryView(QWidget):
    def __init__(self, library: LibraryController, reading: ReadingController, runner: TaskRunner) -> None:
        super().__init__()
        self._library = library
        self._reading = reading
        self._runner = runner
        self.text: ReaderText | None = None
        self.opened_at = 0  # the paragraph the open text was opened at
        self._recorded = 0  # furthest paragraph recorded for the open text

        # The list of texts.
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search the library…")
        self.search_box.returnPressed.connect(self.search)
        self.topic_box = QComboBox()
        # Sized to a fixed length, not to the longest topic: by default a
        # combo box widens to fit its longest item, and one long topic
        # name made the window wider than the screen.
        self.topic_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.topic_box.setMinimumContentsLength(16)
        self.topic_box.currentIndexChanged.connect(self.filter_by_topic)
        filters = QHBoxLayout()
        filters.addWidget(self.search_box, stretch=3)
        filters.addWidget(self.topic_box, stretch=1)
        self.text_list = item_list()
        self.text_list.itemActivated.connect(self._open_item)
        self.text_list.itemClicked.connect(self._open_item)
        self.list_message = QLabel()
        self.list_message.setWordWrap(True)
        shelf = QWidget()
        shelf_layout = QVBoxLayout(shelf)
        shelf_layout.addLayout(filters)
        shelf_layout.addWidget(self.text_list, stretch=1)
        shelf_layout.addWidget(self.list_message)

        # The reader.
        self.back_button = QPushButton("◀ Library")
        self.back_button.clicked.connect(self.show_list)
        self.title = QLabel()
        self.title.setWordWrap(True)
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.position = QLabel()
        self.save_text_button = QPushButton("Save text")
        self.save_text_button.clicked.connect(self.save_text)
        header = QHBoxLayout()
        header.addWidget(self.back_button)
        header.addWidget(self.title, stretch=1)
        header.addWidget(self.position)
        header.addWidget(self.save_text_button)
        self.reader = ReaderPane()
        self.reader.paragraph_clicked.connect(self._paragraph_clicked)
        self.reader.reached.connect(self.record_progress)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.hide()
        reading = QWidget()
        reading_layout = QVBoxLayout(reading)
        reading_layout.setContentsMargins(0, 0, 0, 0)
        reading_layout.addLayout(header)
        reading_layout.addWidget(self.reader, stretch=1)
        reading_layout.addWidget(self.message)

        self._views = QStackedWidget()
        self._views.addWidget(shelf)
        self._views.addWidget(reading)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._views)

        lock_while_busy(runner, self.search_box, self.topic_box, self.text_list, self.save_text_button)
        # Progress is not written while a request uses the database; catch up after.
        runner.busy_changed.connect(lambda busy: busy or self.record_progress(self.reader.furthest_visible()))
        self.refresh()

    @property
    def reading(self) -> bool:
        """Whether the reader, not the list, is showing."""
        return self._views.currentIndex() == 1

    # --- finding texts ---------------------------------------------------------

    def refresh(self) -> None:
        self.topic_box.blockSignals(True)  # refilling it is not a choice of topic
        self.topic_box.clear()
        self.topic_box.addItem(ALL_TOPICS, None)
        for topic, count in self._library.topics():
            self.topic_box.addItem(f"{topic} ({count})", topic)
        self.topic_box.blockSignals(False)
        self._show_texts(self._library.texts())

    def search(self) -> None:
        self._show_texts(self._library.search(self.search_box.text()))

    def filter_by_topic(self) -> None:
        self._show_texts(self._library.texts(self.topic_box.currentData()))

    def _show_texts(self, documents: list[Document]) -> None:
        self.text_list.clear()
        for document in documents:
            year = f" ({document.publication_date.year})" if document.publication_date else ""
            item = QListWidgetItem(f"{document.title}{year}\n{document.author}")
            item.setData(Qt.ItemDataRole.UserRole, str(document.id))
            self.text_list.addItem(item)
        self.list_message.setText("" if documents else "No text matches.")

    def show_list(self) -> None:
        self.record_progress(self.reader.furthest_visible())
        self._views.setCurrentIndex(0)

    # --- reading ---------------------------------------------------------------

    def _open_item(self, item: QListWidgetItem) -> None:
        self.open_text(item.data(Qt.ItemDataRole.UserRole))

    def open_text(self, document_id: str, paragraph: int = 1) -> None:
        """Show the text at ``paragraph``, which counts as read so far."""
        if self._runner.busy:
            self._say("Wait for the current request to finish.")
            return
        try:
            text = self._reading.open_text(document_id)
        except Exception as exc:
            self.list_message.setText(f"Error: {describe_error(exc)}")
            self._say(f"Error: {describe_error(exc)}")
            return
        self.text = text
        self._recorded = 0
        self.title.setText(f"{text.document.title} — {text.document.author}")
        self.position.setText(f"{text.total} paragraphs" if text.total else "No paragraphs.")
        self._say("")
        self._views.setCurrentIndex(1)
        paragraph = max(1, min(paragraph, text.total or 1))
        self.opened_at = paragraph
        self.reader.show_text(text, paragraph)
        self.record_progress(paragraph)

    def record_progress(self, paragraph: int) -> None:
        """Record ``paragraph`` as reached, if it is further than before."""
        text = self.text
        if text is None or not text.passages or self._runner.busy:
            return
        paragraph = min(paragraph, text.total)
        if paragraph <= self._recorded:
            return
        self._recorded = paragraph
        self.position.setText(f"¶{paragraph} of {text.total}")
        try:
            self._reading.record_progress(text.document, paragraph)
        except Exception as exc:
            self._say(f"Progress was not recorded: {describe_error(exc)}")

    # --- the "Ask about" menu (F06) and saving (F15) ---------------------------

    def paragraph_menu(self, paragraph: int) -> QMenu:
        """What can be done with ``paragraph``: ask for an annotation of
        each type, or save it."""
        menu = QMenu(self)
        busy = self._runner.busy
        header = menu.addAction(f"Ask about ¶{paragraph}" + (" (wait for the current request)" if busy else ""))
        header.setEnabled(False)
        for annotation_type in AnnotationType:
            action = menu.addAction(f"    {annotation_type.label.capitalize()}")
            action.setData(annotation_type)
            action.setEnabled(not busy)
            action.triggered.connect(lambda _=False, t=annotation_type: self.ask(paragraph, t))
        menu.addSeparator()
        save = menu.addAction("Save paragraph to workspace")
        save.setEnabled(not busy)
        save.triggered.connect(lambda: self.save_paragraph(paragraph))
        return menu

    def _paragraph_clicked(self, paragraph: int) -> None:
        self.paragraph_menu(paragraph).exec(QCursor.pos())

    def ask(self, paragraph: int, annotation_type: AnnotationType) -> None:
        """Request an annotation; the reader shows it is on its way, then
        shows it under the paragraph."""
        text = self.text
        if text is None:
            return
        document = text.document
        text.failed.pop(paragraph, None)
        text.pending[paragraph] = annotation_type
        self.reader.rerender()

        def finish() -> None:
            text.pending.pop(paragraph, None)
            if self.text is text:  # still the text on screen
                self.reader.rerender()

        def done(result: AnnotationResult) -> None:
            if result.annotation is not None:
                text.annotations.setdefault(result.annotation.passage_id, []).append(result.annotation)
            else:
                text.failed[paragraph] = "No annotation was written: " + " ".join(result.limitations)
            notes = list(result.warnings)
            if result.tokens_used:
                notes.append(f"({result.tokens_used} model tokens)")
            self._say(" ".join(notes))
            finish()

        def failed(exc: Exception) -> None:
            text.failed[paragraph] = f"Error: {describe_error(exc)}"
            finish()

        started = self._runner.run(
            f"Asking about the {annotation_type.label} of ¶{paragraph}",
            lambda: self._reading.annotate(document, paragraph, annotation_type),
            done, failed,
        )
        if not started:
            text.pending.pop(paragraph, None)
            self.reader.rerender()

    def save_text(self) -> None:
        if self.text is not None:
            document = self.text.document
            self._save(lambda: self._reading.save_text(document))

    def save_paragraph(self, paragraph: int) -> None:
        if self.text is not None:
            document = self.text.document
            self._save(lambda: self._reading.save_paragraph(document, paragraph))

    def _save(self, action) -> None:
        try:
            saved = action()
        except Exception as exc:
            self._say(f"Error: {describe_error(exc)}")
            return
        self._say(f"Saved to your workspace: {saved.title}")

    def _say(self, text: str) -> None:
        self.message.setText(text)
        self.message.setVisible(bool(text))
