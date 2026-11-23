"""Composition root: builds the application's objects once, in one place.

The CLI and the GUI both start here, so they share the same services and the
same database instead of each wiring things up differently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from praxis.agent import PoliticalResearchAgent
from praxis.config import Settings, load_settings
from praxis.discovery import (
    SourceDiscoveryService,
    SourceFinder,
    WebSearchSourceFinder,
    WikipediaSourceFinder,
)
from praxis.library import (
    DEFAULT_CATALOGUE,
    LibraryService,
    PublicTextArchiveAdapter,
    directory_fetcher,
)
from praxis.llm import LLMClient, OpenAILLMAdapter, OpenAIWebSearchAdapter
from praxis.news import NewsProvider, RSSNewsAdapter, read_feeds
from praxis.news.exploration import EventExplorer
from praxis.news.service import NewsService
from praxis.news.summary import NewsSummaryService
from praxis.persistence.events import SQLEventRepository
from praxis.persistence import (
    Database,
    SQLAnnotationRepository,
    SQLDocumentRepository,
    SQLReaderProfileRepository,
    SQLWorkspaceRepository,
)
from praxis.persistence.comparisons import SQLComparisonRepository
from praxis.persistence.learning_paths import SQLLearningPathRepository
from praxis.persistence.research import SQLResearchRepository
from praxis.reader_model.events import LearningEventBus
from praxis.reader_model.service import ReaderProfileService
from praxis.reader_model.updater import ReaderModelUpdater
from praxis.reading import (
    AnnotationService,
    IdeologicalContextService,
    PrerequisiteService,
    RecommendationService,
)
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
    annotations: AnnotationService
    recommendations: RecommendationService
    prerequisites: PrerequisiteService
    traditions: IdeologicalContextService
    news: NewsService
    # The model the agent and services use, or None if none is configured.
    llm: LLMClient | None = None
    # Finds texts beyond the library, or None when web discovery is off.
    discovery: SourceDiscoveryService | None = None
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
    news_providers: list[NewsProvider] | None = None,
    discovery: SourceDiscoveryService | None = None,
) -> Application:
    """``llm`` replaces the configured model (tests pass a fake). Without
    one, the OpenAI adapter is used when an API key is configured; with no
    key the agent still retrieves passages but cannot explain them.
    ``news_providers`` replaces the feeds in ``data/news/feeds.json``.
    ``discovery`` replaces the configured source discovery; without one, it
    is built when ``settings.web_discovery`` is on: Wikipedia always, and
    web search when an OpenAI key is configured."""
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
    if discovery is None and settings.web_discovery:
        finders: list[SourceFinder] = [WikipediaSourceFinder()]
        if settings.openai_api_key:
            # After Wikipedia, so a Wikipedia page both find keeps the clean
            # API copy rather than a scraped one.
            finders.append(WebSearchSourceFinder(OpenAIWebSearchAdapter.from_settings(settings)))
        discovery = SourceDiscoveryService(documents, finders)
    return Application(
        settings=settings,
        database=database,
        library=library,
        profiles=profiles,
        events=events,
        workspace=WorkspaceService(SQLWorkspaceRepository(database)),
        agent=PoliticalResearchAgent(
            tools, profiles, llm,
            research_repository=SQLResearchRepository(database),
            comparison_repository=SQLComparisonRepository(database),
            discovery=discovery,
        ),
        annotations=AnnotationService(
            tools, llm, repository=SQLAnnotationRepository(database)
        ),
        recommendations=RecommendationService(tools, llm),
        prerequisites=PrerequisiteService(
            tools, llm, repository=SQLLearningPathRepository(database), discovery=discovery
        ),
        traditions=IdeologicalContextService(tools, library, llm),
        news=NewsService(
            news_providers if news_providers is not None
            else [RSSNewsAdapter(feed) for feed in read_feeds()],
            documents,
            summaries=NewsSummaryService(llm),
            events=SQLEventRepository(database, documents),
            explorer=EventExplorer(documents, llm),
        ),
        llm=llm,
        discovery=discovery,
        owns_database=owns_database,
    )


def bundled_library_service(app: Application) -> LibraryService:
    """A library service that imports from the texts shipped in the repo."""
    folder = Path(DEFAULT_CATALOGUE).parent
    return LibraryService(
        SQLDocumentRepository(app.database),
        PublicTextArchiveAdapter(fetcher=directory_fetcher(folder)),
    )
