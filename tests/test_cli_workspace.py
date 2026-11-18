from uuid import uuid4

import pytest

from praxis.persistence import SQLWorkspaceRepository
from praxis.workspace import SavedItem, SavedItemKind
from praxis.workspace.service import WorkspaceService


@pytest.fixture
def manifesto_id(run):
    run("library", "seed")
    return run("library", "search", "Communist Manifesto").output.split()[0]


def _item_id(output):
    return output.rsplit("[", 1)[1].split("]")[0]


def test_empty_workspace_explains_how_to_save(run):
    assert "Your workspace is empty" in run("workspace", "list").output


def test_save_text_and_list_it(run, manifesto_id):
    result = run("workspace", "save-text", manifesto_id, "--note", "Start here")

    assert result.exit_code == 0
    listing = run("workspace", "list").output
    assert "[document] The Communist Manifesto — Karl Marx and Friedrich Engels" in listing
    assert "note: Start here" in listing
    assert "tags: bourgeoisie, capitalism, class struggle" in listing


def test_saved_passage_opens_with_text_and_resume_command(run, manifesto_id):
    saved = run("workspace", "save-passage", manifesto_id, "12", "-t", "history")
    assert saved.exit_code == 0, saved.output

    opened = run("workspace", "open", _item_id(saved.output))

    assert "[passage] Karl Marx and Friedrich Engels, “The Communist Manifesto”, ¶12" in opened.output
    assert f"praxis library read {manifesto_id} --start 12" in opened.output


def test_paragraph_out_of_range_is_explained(run, manifesto_id):
    result = run("workspace", "save-passage", manifesto_id, "100000")

    assert result.exit_code == 1
    assert "has only" in result.output


def test_opening_a_saved_text_resumes_after_reading_progress(run, manifesto_id):
    item = _item_id(run("workspace", "save-text", manifesto_id).output)
    run("library", "read", manifesto_id, "--count", "7")

    assert "--start 8" in run("workspace", "open", item).output


def test_saved_item_survives_its_source_leaving_the_library(run, cli_database):
    WorkspaceService(SQLWorkspaceRepository(cli_database)).save_item(
        SavedItem(SavedItemKind.PASSAGE, "Gone, ¶1", reference=f"{uuid4()}#¶1", content="kept words")
    )
    item = run("workspace", "list").output.split()[0]

    output = run("workspace", "open", item).output

    assert "kept words" in output
    assert "no longer in the library" in output


def test_notes_search_and_remove(run):
    note = _item_id(run("workspace", "note", "Why 1848?", "Compare France and Germany", "-t", "revolution").output)

    assert "Why 1848?" in run("workspace", "search", "germany").output
    assert "Nothing saved matches" in run("workspace", "search", "russia").output
    assert "[note]" in run("workspace", "list", "--kind", "note").output

    assert "Removed Why 1848?." in run("workspace", "remove", note).output
    assert run("workspace", "remove", note).exit_code == 1
