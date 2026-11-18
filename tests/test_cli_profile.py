def test_new_profile_says_nothing_is_known(run):
    result = run("profile", "show")

    assert result.exit_code == 0
    assert "Nothing is known about you yet" in result.output


def test_stated_knowledge_is_shown_as_stated(run):
    assert run("profile", "know", "Surplus Value", "Intermediate").exit_code == 0

    assert "surplus value: intermediate (you said)" in run("profile", "show").output


def test_invalid_level_is_explained(run):
    result = run("profile", "know", "value", "expert")

    assert result.exit_code == 1
    assert "none, introductory, intermediate, advanced" in result.output


def test_forget_removes_an_assessment(run):
    run("profile", "know", "value", "advanced")

    assert "Removed." in run("profile", "forget", "value").output
    assert "No assessment" in run("profile", "forget", "value").output


def test_interests_can_be_added_and_removed(run):
    run("profile", "interest", "imperialism")
    assert "  imperialism" in run("profile", "show").output

    run("profile", "interest", "imperialism", "--remove")
    assert "  imperialism" not in run("profile", "show").output


def test_preferences_are_saved(run):
    run("profile", "depth", "brief")
    run("profile", "personalize", "false")
    run("profile", "background", "I study engineering.")

    output = run("profile", "show").output
    assert "explanation depth: brief" in output
    assert "personalization: off" in output
    assert "background: I study engineering." in output


def test_reset_asks_for_confirmation(run):
    run("profile", "interest", "labour")

    run("profile", "reset", input="n\n")
    assert "  labour" in run("profile", "show").output

    run("profile", "reset", "--yes")
    assert "Nothing is known" in run("profile", "show").output


def test_reading_in_the_library_updates_the_profile(run):
    run("library", "seed")
    letter_id = run("library", "search", "American Workingmen").output.split()[0]

    run("library", "read", letter_id, "--count", "1000")

    output = run("profile", "show").output
    assert "A Letter to American Workingmen: finished" in output
    assert "imperialism: introductory (inferred from 1 activity)" in output
    assert "  imperialism" in output.split("Interests")[1]


def test_keyword_lookup_is_not_recorded_as_reading(run):
    run("library", "seed")
    letter_id = run("library", "search", "American Workingmen").output.split()[0]

    run("library", "read", letter_id, "--find", "imperialism")

    assert "Nothing is known" in run("profile", "show").output
