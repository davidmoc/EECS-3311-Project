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

-- Full-text index of document passages, so questions can be answered from
-- the paragraphs that discuss them. Porter stemming lets "classes" match
-- "class". Rebuilt from documents.text, so it is never the only copy.
CREATE VIRTUAL TABLE IF NOT EXISTS passage_index USING fts5(
    text,
    passage_id  UNINDEXED,
    document_id UNINDEXED,
    locator     UNINDEXED,
    tokenize = 'porter unicode61'
);

-- Which documents passage_index covers. FTS5 columns cannot be indexed, so
-- asking passage_index this would read every row; this table answers it by
-- primary key. Written in the same transaction as the passages.
CREATE TABLE IF NOT EXISTS indexed_documents (
    document_id TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS saved_items (
    id        TEXT PRIMARY KEY,
    kind      TEXT NOT NULL,
    title     TEXT NOT NULL,
    reference TEXT NOT NULL,
    content   TEXT NOT NULL,
    note      TEXT NOT NULL,
    tags      TEXT NOT NULL,
    saved_at  TEXT NOT NULL
);

-- Research sessions, so research can be reread and continued (F03). The
-- whole result is in data (JSON); the other columns serve the session list.
CREATE TABLE IF NOT EXISTS research_sessions (
    id           TEXT PRIMARY KEY,
    objective    TEXT NOT NULL,
    status       TEXT NOT NULL,
    incomplete   INTEGER NOT NULL,
    rounds       INTEGER NOT NULL,
    source_count INTEGER NOT NULL,
    updated_at   TEXT NOT NULL,
    data         TEXT NOT NULL
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
