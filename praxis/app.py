"""Composition root: builds the application's objects once, in one place.

The CLI and the GUI both start here, so they share the same services and the
same database instead of each wiring things up differently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from praxis.config import Settings, load_settings
from praxis.library import (
    DEFAULT_CATALOGUE,
    LibraryService,
    PublicTextArchiveAdapter,
    directory_fetcher,
)
from praxis.persistence import Database, SQLDocumentRepository


@dataclass
class Application:
    settings: Settings
    database: Database
    library: LibraryService
    # False when the caller passed in a database it will close itself.
    owns_database: bool = True
    _closed: bool = field(default=False, repr=False)

    def close(self) -> None:
        if self.owns_database and not self._closed:
            self.database.close()
            self._closed = True


def build_application(
    settings: Settings | None = None, database: Database | None = None
) -> Application:
    settings = settings or load_settings()
    owns_database = database is None
    database = database or Database(settings.database_path)
    documents = SQLDocumentRepository(database)
    library = LibraryService(documents, PublicTextArchiveAdapter())
    return Application(
        settings=settings,
        database=database,
        library=library,
        owns_database=owns_database,
    )


def bundled_library_service(app: Application) -> LibraryService:
    """A library service that imports from the texts shipped in the repo."""
    folder = Path(DEFAULT_CATALOGUE).parent
    return LibraryService(
        SQLDocumentRepository(app.database),
        PublicTextArchiveAdapter(fetcher=directory_fetcher(folder)),
    )
