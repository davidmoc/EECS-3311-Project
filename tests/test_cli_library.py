import pytest


@pytest.fixture
def seeded(run):
    result = run("library", "seed")
    assert result.exit_code == 0, result.output


def test_empty_library_explains_how_to_seed(run):
    result = run("library", "browse")

    assert result.exit_code == 0
    assert "praxis library seed" in result.output


def test_seed_imports_bundled_texts_offline(run):
    result = run("library", "seed")

    assert result.exit_code == 0
    assert "Imported The Communist Manifesto" in result.output
    assert "14 imported, 0 skipped." in result.output


def test_seeding_twice_does_not_duplicate(seeded, run):
    run("library", "seed")

    assert run("library", "browse").output.count("Communist Manifesto") == 1


def test_search_lists_matches_with_short_ids(seeded, run):
    result = run("library", "search", "Brumaire")

    assert "The Eighteenth Brumaire of Louis Bonaparte (1852) — Karl Marx" in result.output


def test_search_with_no_match_suggests_broadening(seeded, run):
    assert "No texts match" in run("library", "search", "xyzzy").output


def test_browse_by_topic(seeded, run):
    result = run("library", "browse", "--topic", "imperialism")

    assert "A Letter to American Workingmen" in result.output
    assert "Communist Manifesto" not in result.output


def test_topics_are_listed_with_counts(seeded, run):
    assert "  6  history" in run("library", "topics").output


def _id_of(run, title_word):
    return run("library", "search", title_word).output.split()[0]


def test_read_shows_paragraphs_with_locators_and_paging_hint(seeded, run):
    result = run("library", "read", _id_of(run, "Manifesto"), "--count", "2")

    assert result.exit_code == 0
    assert "[¶1]" in result.output and "[¶2]" in result.output
    assert "[¶3]" not in result.output
    assert "Next: --start 3" in result.output


def test_read_can_filter_paragraphs(seeded, run):
    result = run("library", "read", _id_of(run, "Manifesto"), "--find", "hitherto existing societies")

    assert "history of class struggles" in result.output


def test_read_unknown_id_fails_cleanly(seeded, run):
    result = run("library", "read", "zzzzzzzz")

    assert result.exit_code == 1
    assert "No text with id" in result.output


def test_download_saves_text_file(seeded, run, tmp_path):
    result = run("library", "download", _id_of(run, "Manifesto"), "--to", str(tmp_path))

    assert result.exit_code == 0
    assert (tmp_path / "the-communist-manifesto.txt").exists()
