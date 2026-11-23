"""Starting the GUI: the composition root's objects, a window, and Qt's loop."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from praxis.app import Application, build_application
from praxis.config import load_settings
from praxis.gui.compare import CompareController, CompareView
from praxis.gui.home import HomeController, HomeView
from praxis.gui.library import LibraryController, LibraryView, ReadingController
from praxis.gui.main_window import MainWindow
from praxis.gui.news import NewsController, NewsView
from praxis.gui.paths import PathsController, PathsView
from praxis.gui.profile import ProfileController, ProfileView
from praxis.gui.research import ResearchController, ResearchView
from praxis.gui.sessions import SessionsController, SessionsView
from praxis.gui.tasks import TaskRunner, ThreadTaskRunner
from praxis.persistence import Database


def build_window(application: Application, runner: TaskRunner) -> MainWindow:
    """The window with every page, each View given its Controller."""
    window = MainWindow(runner)
    window.add_page("Home", HomeView(HomeController(application), runner))
    window.add_page("Library", LibraryView(
        LibraryController(application), ReadingController(application), runner
    ))
    def open_reading(document_id: str, paragraph: int) -> None:
        window.show_page("Library").open_text(document_id, paragraph)

    window.add_page("News", NewsView(NewsController(application), runner, open_reading))
    window.add_page("Research", ResearchView(ResearchController(application), runner, open_reading))
    window.add_page("Past research", SessionsView(SessionsController(application), runner, open_reading))
    window.add_page("Compare", CompareView(CompareController(application), runner, open_reading))
    window.add_page("Learning paths", PathsView(PathsController(application), runner, open_reading))
    window.add_page("Profile", ProfileView(ProfileController(application), runner))
    return window


def run(argv: list[str] | None = None) -> int:
    settings = load_settings()
    # Shared with the worker thread that runs model requests (see tasks.py).
    database = Database(settings.database_path, shared_with_worker=True)
    application = build_application(settings, database)
    qt = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    runner = ThreadTaskRunner()
    window = build_window(application, runner)
    window.show()
    try:
        return qt.exec()
    finally:
        runner.wait()
        database.close()
