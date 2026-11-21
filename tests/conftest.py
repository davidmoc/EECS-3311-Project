import pytest
from typer.testing import CliRunner

from praxis import app as app_module
from praxis.cli import commands
from praxis.config import Settings
from praxis.documents import Book
from praxis.llm import LLMClient, LLMResponse
from praxis.persistence import Database, SQLDocumentRepository


@pytest.fixture
def cli_database(monkeypatch):
    """Every CLI command in a test shares one in-memory database."""
    database = Database()
    settings = Settings(openai_api_key=None)
    monkeypatch.setattr(
        commands, "application_factory",
        lambda: app_module.build_application(settings, database),
    )
    yield database
    database.close()


@pytest.fixture
def run(cli_database):
    runner = CliRunner()

    def invoke(*args, input=None):
        return runner.invoke(commands.app, list(args), input=input)

    return invoke


# --- shared by the research-agent tests (F03) --------------------------------

MANIFESTO_PASSAGES = (
    "The history of all hitherto existing society is the history of class "
    "struggles, freeman and slave, patrician and plebeian, lord and serf.",
    "The average price of wage labour is the minimum wage, the quantum of "
    "the means of subsistence requisite to keep the labourer in existence.",
    "The executive of the modern state is but a committee for managing the "
    "common affairs of the whole bourgeoisie.",
)
REVOLUTION_PASSAGES = (
    "In 1848 the revolution broke out in Paris and spread across Germany, "
    "where the bourgeoisie soon made peace with the monarchy.",
    "The workers of Vienna and Berlin fought on the barricades while the "
    "liberal bourgeoisie feared them more than the old order.",
)


class ScriptedLLM(LLMClient):
    """Replies in order; an exception in the list is raised instead."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return LLMResponse(reply, "fake", prompt_tokens=10, completion_tokens=5)


@pytest.fixture
def library_database():
    """An in-memory database holding two short texts."""
    database = Database()
    documents = SQLDocumentRepository(database)
    documents.save(Book(
        title="The Communist Manifesto",
        author="Karl Marx and Friedrich Engels",
        text="\n\n".join(MANIFESTO_PASSAGES),
        license="Public Domain",
    ))
    documents.save(Book(
        title="Revolution and Counter-Revolution in Germany",
        author="Friedrich Engels",
        text="\n\n".join(REVOLUTION_PASSAGES),
        license="Public Domain",
    ))
    yield database
    database.close()
