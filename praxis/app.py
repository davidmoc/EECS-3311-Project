"""Composition root: builds the application's objects once, in one place.

The CLI and the GUI both start here, so they share the same services and the
same database instead of each wiring things up differently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from praxis.agent import PoliticalResearchAgent
from praxis.config import Settings, load_settings
from praxis.library import (
    DEFAULT_CATALOGUE,
    LibraryService,
    PublicTextArchiveAdapter,
    directory_fetcher,
)
from praxis.llm import LLMClient, OpenAILLMAdapter
from praxis.persistence import (
    Database,
    SQLDocumentRepository,
    SQLReaderProfileRepository,
    SQLWorkspaceRepository,
)
from praxis.reader_model.events import LearningEventBus
from praxis.reader_model.service import ReaderProfileService
from praxis.reader_model.updater import ReaderModelUpdater
from praxis.tools import ToolFactory, ToolManager
from praxis.workspace.service import WorkspaceService


@dataclass
class Application:
    settings: Settings
    database: Database
    library: LibraryService
    profiles: ReaderProfileService
    events: LearningEventBus
    workspace: WorkspaceService
    agent: PoliticalResearchAgent
    # False when the caller passed in a database it will close itself.
    owns_database: bool = True
    _closed: bool = field(default=False, repr=False)

    def close(self) -> None:
        if self.owns_database and not self._closed:
            self.database.close()
            self._closed = True


def build_application(
    settings: Settings | None = None,
    database: Database | None = None,
    llm: LLMClient | None = None,
) -> Application:
    """``llm`` replaces the configured model (tests pass a fake). Without
    one, the OpenAI adapter is used when an API key is configured; with no
    key the agent still retrieves passages but cannot explain them."""
    settings = settings or load_settings()
    owns_database = database is None
    database = database or Database(settings.database_path)
    documents = SQLDocumentRepository(database)
    library = LibraryService(documents, PublicTextArchiveAdapter())
    profiles = ReaderProfileService(SQLReaderProfileRepository(database))
    events = LearningEventBus()
    events.subscribe(ReaderModelUpdater(profiles))
    tools = ToolManager()
    for tool in ToolFactory(documents).create_all():
        tools.register_tool(tool)
    if llm is None and settings.openai_api_key:
        llm = OpenAILLMAdapter.from_settings(settings)
    return Application(
        settings=settings,
        database=database,
        library=library,
        profiles=profiles,
        events=events,
        workspace=WorkspaceService(SQLWorkspaceRepository(database)),
        agent=PoliticalResearchAgent(tools, profiles, llm),
        owns_database=owns_database,
    )


def bundled_library_service(app: Application) -> LibraryService:
    """A library service that imports from the texts shipped in the repo."""
    folder = Path(DEFAULT_CATALOGUE).parent
    return LibraryService(
        SQLDocumentRepository(app.database),
        PublicTextArchiveAdapter(fetcher=directory_fetcher(folder)),
    )
