"""Research, questions and learning paths use texts found beyond the library."""

from conftest import ScriptedLLM
from test_discovery import FakeFinder, long_article_html, page_reader

from praxis.agent import PoliticalResearchAgent, ResponseStatus
from praxis.config import Settings, load_settings
from praxis.discovery import DiscoveryRequest, FoundSource, SourceDiscoveryService
from praxis.persistence import Database, SQLDocumentRepository, SQLReaderProfileRepository
from praxis.reader_model.service import ReaderProfileService
from praxis.reading.prerequisites import PrerequisiteService
from praxis.tools import PassageSearchTool, SourceRetrievalTool, ToolManager

# --- features use what was found ---------------------------------------------------

LIBYA_PATH = """\
prerequisite: The 2011 NATO intervention | event | essential
search: NATO bombing resolution 1973
why: The present crisis begins there.
orientation: NATO bombed Libya in 2011.
"""


def test_a_learning_path_reads_first_from_texts_found_for_its_steps(library_database):
    documents = SQLDocumentRepository(library_database)
    finder = FakeFinder("web", FoundSource("https://example.org/libya", subtopic="The 2011 NATO intervention"))
    discovery = SourceDiscoveryService(documents, [finder], page_reader({"https://example.org/libya": long_article_html()}))
    tools = ToolManager()
    tools.register_tool(PassageSearchTool(documents))
    tools.register_tool(SourceRetrievalTool(documents))

    path = PrerequisiteService(tools, ScriptedLLM(LIBYA_PATH), discovery=discovery).build_learning_path("Libya")

    assert finder.requests[0] == DiscoveryRequest("Libya", ("The 2011 NATO intervention",))
    step = path.steps[0]
    assert not step.is_gap
    assert step.readings[0].document_title == "Ten years after NATO destroyed Libya"
    assert any("added them to your library" in w or "added it to your library" in w for w in path.warnings)


def test_a_question_is_answered_from_texts_found_for_it(library_database):
    documents = SQLDocumentRepository(library_database)
    finder = FakeFinder("web", FoundSource("https://example.org/libya"), tokens=40)
    discovery = SourceDiscoveryService(documents, [finder], page_reader({"https://example.org/libya": long_article_html()}))
    tools = ToolManager()
    tools.register_tool(PassageSearchTool(documents))
    llm = ScriptedLLM("Libya, Tobruk", "NATO bombed Libya [1].")
    agent = PoliticalResearchAgent(
        tools, ReaderProfileService(SQLReaderProfileRepository(library_database)), llm, discovery=discovery
    )

    response = agent.answer_question("What happened to Libya after 2011?")

    assert finder.requests[0].subtopics == ("Libya Tobruk",)
    assert response.status is ResponseStatus.ANSWERED
    assert response.sources[0].citation.document_title == "Ten years after NATO destroyed Libya"
    assert response.tokens_used == 15 + 40 + 15
    assert "added it to your library" in response.warnings[0]


# --- configuration and the web search adapter ----------------------------------------

def test_web_discovery_is_on_by_default_only_through_load_settings():
    assert Settings(openai_api_key=None).web_discovery is False
    assert load_settings(env={}).web_discovery is True
    assert load_settings(env={"PRAXIS_WEB_DISCOVERY": "off"}).web_discovery is False


# --- the CLI ---------------------------------------------------------------------------

def test_library_discover_lists_what_was_added(monkeypatch):
    from typer.testing import CliRunner

    from praxis import app as app_module
    from praxis.cli import commands

    database = Database()
    finder = FakeFinder("web", FoundSource("https://example.org/libya"), FoundSource("https://example.org/gone"))

    def factory():
        discovery = SourceDiscoveryService(
            SQLDocumentRepository(database), [finder],
            page_reader({"https://example.org/libya": long_article_html()}),
        )
        return app_module.build_application(Settings(openai_api_key=None), database, discovery=discovery)

    monkeypatch.setattr(commands, "application_factory", factory)
    result = CliRunner().invoke(commands.app, ["library", "discover", "Libya", "-s", "oil"])
    database.close()

    assert result.exit_code == 0, result.output
    assert "Added   Ten years after NATO destroyed Libya — A. Writer" in result.output
    assert "Skipped https://example.org/gone" in result.output
    assert "1 added, 0 already in the library, 1 skipped." in result.output
    assert finder.requests[0].subtopics == ("oil",)


def test_library_discover_explains_when_discovery_is_off(run):
    result = run("library", "discover", "Libya")
    assert result.exit_code == 1
    assert "Web discovery is off" in result.output
