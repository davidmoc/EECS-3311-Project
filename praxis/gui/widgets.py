"""Small pieces shared by the views."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QListWidget, QTextBrowser, QWidget

from praxis.gui.render import parse_read_link
from praxis.gui.tasks import TaskRunner

OpenReading = Callable[[str, int], None]


def lock_while_busy(runner: TaskRunner, *widgets: QWidget) -> None:
    """Disable ``widgets`` while a request runs: they reach the database,
    which the running request is using (see ``praxis.gui.tasks``)."""
    runner.busy_changed.connect(lambda busy: [w.setEnabled(not busy) for w in widgets])


def result_browser(open_reading: OpenReading | None = None) -> QTextBrowser:
    """A pane for results whose passage links (``render.read_link``)
    open the text on the library page."""
    browser = QTextBrowser()
    browser.setOpenLinks(False)

    def clicked(url: QUrl) -> None:
        target = parse_read_link(url.toString())
        if target is not None and open_reading is not None:
            open_reading(*target)

    browser.anchorClicked.connect(clicked)
    return browser


def item_list() -> QListWidget:
    """A list whose entries run to several lines (an event card, a saved
    item with its date), shaded alternately and spaced so each entry reads
    as one. A live run showed the news cards running together without it."""
    widget = QListWidget()
    widget.setWordWrap(True)
    widget.setAlternatingRowColors(True)
    widget.setSpacing(3)
    return widget
