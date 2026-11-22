"""SQLResearchRepository: storing and restoring research sessions (F03)."""

from datetime import timedelta
from uuid import uuid4

from conftest import ScriptedLLM

from praxis.agent import PoliticalResearchAgent, ResponseStatus
from praxis.persistence import SQLDocumentRepository, SQLReaderProfileRepository
from praxis.persistence.research import SQLResearchRepository
from praxis.reader_model.service import ReaderProfileService
from praxis.research import ResearchBudget
from praxis.tools import PassageSearchTool, ToolManager

OBJECTIVE = "Why did the German revolution of 1848 fail?"
PLAN = "history: 1848 revolution Germany\ntheory: bourgeoisie state"
ASSESSMENT = (
    "contradiction: bourgeoisie | workers | the bourgeoisie feared the workers [2]\n"
    "relation: class | The bourgeoisie made peace with the monarchy [1]\n"
    "development: Revolution spread from Paris to Germany [1]\n"
    "conflict: [1] vs [2] | whether the bourgeoisie led or betrayed\n"
    "question: What did the peasantry do?\n"
    "verdict: sufficient"
)
SYNTHESIS = "## Findings\nThe bourgeoisie made peace with the monarchy [1].\n\n## Open questions\n- Why Prussia?\n"


def research(database, *replies, budget=None):
    tools = ToolManager()
    tools.register_tool(PassageSearchTool(SQLDocumentRepository(database)))
    profiles = ReaderProfileService(SQLReaderProfileRepository(database))
    agent = PoliticalResearchAgent(tools, profiles, ScriptedLLM(*replies))
    return agent.research(OBJECTIVE, budget)


def test_a_stored_result_is_restored_unchanged(library_database):
    result = research(library_database, PLAN, ASSESSMENT, SYNTHESIS)
    repository = SQLResearchRepository(library_database)

    repository.save(result)
    restored = repository.get(result.session.id)

    assert restored == result  # dataclass equality: every field, recursively
    assert restored.situation.contradictions and restored.situation.conflicts
    assert [c.describe() for c in restored.plan.taken] == [c.describe() for c in result.plan.taken]
    assert restored.cited[0].citation.quoted_text == result.cited[0].citation.quoted_text


def test_an_incomplete_result_keeps_its_unfinished_steps(library_database):
    result = research(library_database, PLAN, SYNTHESIS, budget=ResearchBudget(max_tool_calls=1))
    repository = SQLResearchRepository(library_database)
    repository.save(result)

    restored = repository.get(result.session.id)
    summary = repository.list_recent()[0]

    assert restored.is_incomplete
    assert [c.describe() for c in restored.unfinished_steps] == [
        c.describe() for c in result.unfinished_steps
    ]
    assert summary.incomplete and summary.source_count == len(result.sources)


def test_saving_again_replaces_the_session_and_lists_newest_first(library_database):
    repository = SQLResearchRepository(library_database)
    older = research(library_database, PLAN, ASSESSMENT, SYNTHESIS)
    newer = research(library_database, "nothing usable", "verdict: sufficient", SYNTHESIS)
    repository.save(older)
    repository.save(newer)
    object.__setattr__(older, "created_at", newer.created_at + timedelta(seconds=1))
    repository.save(older)  # updated later, so listed first, and not duplicated

    listed = repository.list_recent()

    assert [s.id for s in listed] == [older.session.id, newer.session.id]
    assert listed[0].objective == OBJECTIVE and listed[0].status is ResponseStatus.ANSWERED


def test_sessions_are_found_by_id_prefix(library_database):
    repository = SQLResearchRepository(library_database)
    result = research(library_database, PLAN, ASSESSMENT, SYNTHESIS)
    repository.save(result)
    full = str(result.session.id)

    assert repository.find_ids(full[:6].upper()) == [result.session.id]
    assert repository.find_ids("%") == []
    assert repository.find_ids("") == []
    assert repository.get(uuid4()) is None
