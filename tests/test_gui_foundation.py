"""The GUI's task runner, main window and home page."""

import threading

from PySide6.QtCore import QCoreApplication

from praxis.gui.home import NO_MODEL
from praxis.gui.tasks import BUSY_MESSAGE, InlineTaskRunner, ThreadTaskRunner


def test_the_threaded_runner_works_on_a_worker_and_answers_on_the_gui_thread(qt_app):
    runner = ThreadTaskRunner()
    gui_thread = threading.get_ident()
    seen = {}
    busy = []
    runner.busy_changed.connect(busy.append)

    def work():
        seen["worker"] = threading.get_ident()
        return 42

    assert runner.run("Counting", work, lambda result: seen.update(result=result, done=threading.get_ident()))
    assert runner.busy
    assert runner.wait(5000)
    for _ in range(50):  # deliver the queued result
        QCoreApplication.processEvents()
        if "result" in seen:
            break

    assert seen["result"] == 42
    assert seen["worker"] != gui_thread
    assert seen["done"] == gui_thread
    assert busy == [True, False] and not runner.busy


def test_a_second_request_waits_for_the_first(qt_app):
    runner = InlineTaskRunner()
    messages, results = [], []
    runner.status.connect(messages.append)

    def nested():
        # Another request while this one runs is refused.
        results.append(runner.run("Second", lambda: 2, results.append))
        return 1

    assert runner.run("First", nested, results.append)
    assert results == [False, 1]
    assert BUSY_MESSAGE in messages


def test_a_failed_request_is_reported_and_frees_the_runner(qt_app):
    runner = InlineTaskRunner()
    errors = []

    def broken():
        raise ValueError("no such text")

    runner.run("Opening", broken, lambda _: None, errors.append)

    assert [str(e) for e in errors] == ["no such text"]
    assert not runner.busy


def test_home_offers_the_bundled_library_when_it_is_empty(gui):
    window, application = gui()
    home = window.page("Home")

    assert window.page_titles[0] == "Home"
    assert "The library holds 0 texts." in home.summary.text()
    assert NO_MODEL in home.summary.text()
    assert not home.load_button.isHidden()

    home.load_button.click()

    assert len(application.library.browse()) == 14
    assert "14 imported, 0 skipped." == home.message.text()
    assert "The library holds 14 texts." in home.summary.text()
    assert home.load_button.isHidden()
