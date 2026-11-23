"""The profile page: inspect and correct the reader model (F13, F14)."""

from praxis.gui.profile import SPARSE
from praxis.reader_model import ExplanationDepth, KnowledgeLevel


def rows(table):
    return [
        tuple(table.item(r, c).text() for c in range(table.columnCount()))
        for r in range(table.rowCount())
    ]


def test_an_empty_profile_says_nothing_is_known(gui):
    window, _ = gui()
    page = window.show_page("Profile")

    assert page.notice.text() == SPARSE
    assert page.knowledge.rowCount() == 0


def test_inferred_knowledge_is_shown_with_its_origin_and_can_be_corrected(gui):
    window, application = gui(seed=True)
    library = window.show_page("Library")
    letter = application.library.browse("imperialism")
    letter = next(d for d in letter if d.title == "A Letter to American Workingmen")
    library.open_text(str(letter.id), start=10_000)  # the last page: finishing infers knowledge
    page = window.show_page("Profile")

    inferred = [row for row in rows(page.knowledge) if row[2].startswith("inferred")]
    assert inferred, rows(page.knowledge)
    assert page.reading.item(0).text() == "A Letter to American Workingmen: finished"
    topic = inferred[0][0]

    page.knowledge.selectRow([r[0] for r in rows(page.knowledge)].index(topic))
    assert page.topic_box.text() == topic
    page.level_box.setCurrentIndex(page.level_box.findData(KnowledgeLevel.ADVANCED))
    page.state_button.click()

    assert (topic, "advanced", "you said") in rows(page.knowledge)
    assert application.profiles.get_profile().knowledge.get_level(topic) is KnowledgeLevel.ADVANCED

    page.forget_button.click()
    assert topic not in [r[0] for r in rows(page.knowledge)]
    assert page.message.text() == f"Removed {topic}."


def test_interests_and_preferences_are_saved(gui):
    window, application = gui()
    page = window.show_page("Profile")

    page.interest_box.setText("Imperialism")
    page.add_interest_button.click()
    page.depth_box.setCurrentIndex(page.depth_box.findData(ExplanationDepth.BRIEF))
    page.set_depth()
    page.personalize_box.click()
    page.background_box.setText("History student")
    page.background_button.click()

    profile = application.profiles.get_profile()
    assert profile.interests.top() == ["imperialism"]
    assert profile.explanation_depth is ExplanationDepth.BRIEF
    assert not profile.personalization_enabled
    assert profile.background == "History student"

    page.interests.setCurrentRow(0)
    page.remove_interest_button.click()
    assert application.profiles.get_profile().interests.top() == []
    assert page.interests.count() == 0


def test_stating_a_level_without_a_topic_is_refused(gui):
    window, _ = gui()
    page = window.show_page("Profile")

    page.state_button.click()

    assert page.message.text() == "Error: Name the topic first."
