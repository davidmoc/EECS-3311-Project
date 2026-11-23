"""The library page: find texts (F05), read them, and ask for AI
annotations of a paragraph (F06).

Stage 1's ``LibraryView`` and ``ReaderView`` share one page here: the list
of texts on the left, the reader on the right. ``LibraryController`` finds
texts; ``ReadingController`` opens pages of a text, which records reading
progress through the ``LearningEventBus`` (F13), and requests annotations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from praxis.app import Application
from praxis.documents import Annotation, AnnotationType, Document, Passage
from praxis.gui import render
from praxis.gui.tasks import TaskRunner, describe_error
from praxis.reader_model.events import DocumentRead
from praxis.reader_model.personalization import RequestPreferences
from praxis.reading import AnnotationResult

PAGE_SIZE = 10
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


@dataclass(frozen=True)
class ReaderPage:
    document: Document
    passages: list[Passage]
    start: int  # number of the first paragraph shown
    total: int
    annotations: dict[UUID, list[Annotation]] = field(default_factory=dict)

    @property
    def end(self) -> int:
        return self.start + len(self.passages) - 1


class ReadingController:
    def __init__(self, application: Application) -> None:
        self._application = application

    def open_page(self, document_id: UUID | str, start: int = 1, count: int = PAGE_SIZE) -> ReaderPage:
        """Paragraphs ``start`` to ``start + count - 1``. Reading them is
        recorded as progress, as ``library read`` does."""
        document = self._application.library.get_document(document_id)
        passages = document.passages()
        start = max(1, min(start, len(passages) or 1))
        shown = passages[start - 1 : start - 1 + count]
        if shown:
            self._application.events.publish(DocumentRead(document, start - 1 + len(shown)))
        by_passage: dict[UUID, list[Annotation]] = {}
        for annotation in self._application.annotations.annotations_for(document):
            by_passage.setdefault(annotation.passage_id, []).append(annotation)
        return ReaderPage(document, shown, start, len(passages), by_passage)

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


def lock_while_busy(runner: TaskRunner, *widgets: QWidget) -> None:
    """Disable ``widgets`` while a request runs: they reach the database,
    which the running request is using (see ``praxis.gui.tasks``)."""
    runner.busy_changed.connect(lambda busy: [w.setEnabled(not busy) for w in widgets])


class LibraryView(QWidget):
    def __init__(self, library: LibraryController, reading: ReadingController, runner: TaskRunner) -> None:
        super().__init__()
        self._library = library
        self._reading = reading
        self._runner = runner
        self.page: ReaderPage | None = None

        # Left: finding texts.
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search the library…")
        self.search_box.returnPressed.connect(self.search)
        self.topic_box = QComboBox()
        self.topic_box.currentIndexChanged.connect(self.filter_by_topic)
        self.text_list = QListWidget()
        self.text_list.itemActivated.connect(self._open_item)
        self.text_list.itemClicked.connect(self._open_item)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.search_box)
        left_layout.addWidget(self.topic_box)
        left_layout.addWidget(self.text_list)

        # Right: the reader.
        self.title = QLabel("Choose a text to read.")
        self.title.setWordWrap(True)
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.reader = QTextBrowser()
        self.previous_button = QPushButton("◀ Previous")
        self.previous_button.clicked.connect(lambda: self.turn(-PAGE_SIZE))
        self.next_button = QPushButton("Next ▶")
        self.next_button.clicked.connect(lambda: self.turn(PAGE_SIZE))
        self.position = QLabel()
        pages = QHBoxLayout()
        pages.addWidget(self.previous_button)
        pages.addWidget(self.position, stretch=1)
        pages.addWidget(self.next_button)

        self.paragraph_box = QSpinBox()
        self.paragraph_box.setPrefix("¶")
        self.type_box = QComboBox()
        for annotation_type in AnnotationType:
            self.type_box.addItem(annotation_type.label, annotation_type)
        self.annotate_button = QPushButton("Annotate (AI)")
        self.annotate_button.clicked.connect(self.annotate)
        annotate_row = QHBoxLayout()
        annotate_row.addWidget(QLabel("Annotate paragraph"))
        annotate_row.addWidget(self.paragraph_box)
        annotate_row.addWidget(self.type_box)
        annotate_row.addWidget(self.annotate_button)
        annotate_row.addStretch()
        self.annotation = QTextBrowser()
        self.annotation.setMaximumHeight(260)
        self.message = QLabel()
        self.message.setWordWrap(True)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.title)
        right_layout.addWidget(self.reader, stretch=1)
        right_layout.addLayout(pages)
        right_layout.addLayout(annotate_row)
        right_layout.addWidget(self.annotation)
        right_layout.addWidget(self.message)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 3)
        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        lock_while_busy(
            runner, self.search_box, self.topic_box, self.text_list,
            self.previous_button, self.next_button, self.annotate_button,
        )
        self.refresh()
        self._update_controls()

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
        if not documents:
            self.message.setText("No text matches.")
        else:
            self.message.clear()

    # --- reading ---------------------------------------------------------------

    def _open_item(self, item: QListWidgetItem) -> None:
        self.open_text(item.data(Qt.ItemDataRole.UserRole))

    def open_text(self, document_id: str, start: int = 1) -> None:
        if self._runner.busy:
            return
        try:
            self.page = self._reading.open_page(document_id, start)
        except Exception as exc:
            self.message.setText(f"Error: {describe_error(exc)}")
            return
        page = self.page
        self.title.setText(f"{page.document.title} — {page.document.author}")
        self.reader.setMarkdown(render.paragraphs(page.document, page.passages, page.annotations))
        self.position.setText(
            f"¶{page.start}–{page.end} of {page.total}" if page.passages else "No paragraphs."
        )
        self.paragraph_box.setRange(page.start, max(page.end, page.start))
        self.paragraph_box.setValue(page.start)
        self.annotation.clear()
        self.message.clear()
        self._update_controls()

    def turn(self, by: int) -> None:
        if self.page is not None:
            self.open_text(str(self.page.document.id), self.page.start + by)

    def _update_controls(self) -> None:
        page = self.page
        self.previous_button.setEnabled(page is not None and page.start > 1)
        self.next_button.setEnabled(page is not None and page.end < page.total)
        self.annotate_button.setEnabled(page is not None and bool(page.passages))

    # --- annotating (F06) ------------------------------------------------------

    def annotate(self) -> None:
        if self.page is None:
            return
        page = self.page
        paragraph = self.paragraph_box.value()
        annotation_type = self.type_box.currentData()

        def done(result: AnnotationResult) -> None:
            if result.annotation is not None:
                text = render.annotation_markdown(result.annotation)
            else:
                text = "**No annotation was written:**\n\n" + "\n".join(
                    render.line(limitation) for limitation in result.limitations
                )
            self.annotation.setMarkdown(render.join(text, render.warnings(result.warnings, result.tokens_used)))
            self._update_controls()

        def failed(exc: Exception) -> None:
            self.annotation.setMarkdown(f"**Error:** {render.escape(describe_error(exc))}")
            self._update_controls()

        self.annotation.setMarkdown(f"*Asking for a {annotation_type.label} annotation of ¶{paragraph}…*")
        self._runner.run(
            f"Annotating ¶{paragraph}",
            lambda: self._reading.annotate(page.document, paragraph, annotation_type),
            done, failed,
        )
