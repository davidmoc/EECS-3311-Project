"""A database the GUI shares with its worker thread."""

import sqlite3
import threading

from praxis.persistence import Database


def count_in_thread(database):
    outcome = {}

    def work():
        try:
            outcome["rows"] = database.connection.execute("SELECT count(*) FROM documents").fetchone()[0]
        except sqlite3.ProgrammingError as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=work)
    thread.start()
    thread.join()
    return outcome


def test_by_default_the_connection_stays_in_its_thread():
    database = Database()
    assert "error" in count_in_thread(database)
    database.close()


def test_a_database_shared_with_a_worker_can_be_used_from_it():
    database = Database(shared_with_worker=True)
    assert count_in_thread(database) == {"rows": 0}
    database.close()
