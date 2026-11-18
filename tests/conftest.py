import pytest
from typer.testing import CliRunner

from praxis import app as app_module
from praxis.cli import commands
from praxis.config import Settings
from praxis.persistence import Database


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
