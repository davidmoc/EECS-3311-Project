"""The single local SQLite database shared by all repositories."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id               TEXT PRIMARY KEY,
    kind             TEXT NOT NULL,
    title            TEXT NOT NULL,
    author           TEXT NOT NULL,
    text             TEXT NOT NULL,
    publication_date TEXT,
    source_url       TEXT NOT NULL,
    license          TEXT NOT NULL,
    downloadable     INTEGER NOT NULL,
    topics           TEXT NOT NULL,
    outlet           TEXT NOT NULL DEFAULT ''
);

-- Single local user, so there is exactly one profile row (id = 1).
CREATE TABLE IF NOT EXISTS reader_profile (
    id   INTEGER PRIMARY KEY CHECK (id = 1),
    data TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path | str = ":memory:") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path))
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)

    def close(self) -> None:
        self.connection.close()
