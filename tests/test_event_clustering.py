"""Event and EventClusterer (F01, SD03)."""

from datetime import date

import pytest

from praxis.documents import NewsArticle
from praxis.news.clustering import EventClusterer
from praxis.news.events import Event, Grouping, event_id

DAY = date(2026, 11, 22)


def report(title, outlet, text="", day=DAY):
    return NewsArticle(
        title=title, author="Staff", outlet=outlet, text=text, publication_date=day,
        source_url=f"https://{outlet.replace(' ', '').lower()}.example/{title.replace(' ', '-')}",
    )


FIRE = [
    report("Dozens missing as deadly fire hits Indonesian candy factory", "Wire A",
           "A fire at a confectionery factory in Indonesia killed three workers."),
    report("Fire at Indonesian candy factory leaves 3 dead, dozens of workers missing", "Wire B",
           "Rescuers searched the burned factory in Indonesia."),
    report("Three killed and dozens missing after fire at Indonesian factory", "Wire C"),
]
CLIMATE = [
    report("COP31 climate talks collapse without a deal on fossil fuels", "Wire A",
           "Delegates at the COP31 summit rejected the final text."),
    report("COP31 fails to reach climate deal as talks expose divisions", "Wire B",
           "The COP31 climate summit ended without agreement on fossil fuels."),
]
LONE = report("Liverpool thrash ten-man United", "Wire C", "A football match report.")


def test_reports_of_the_same_event_are_grouped():
    events = EventClusterer().cluster([*FIRE, *CLIMATE, LONE])

    groups = [{r.title for r in e.reports} for e in events]
    assert {r.title for r in FIRE} in groups
    assert {r.title for r in CLIMATE} in groups
    assert {LONE.title} in groups
    assert len(events) == 3


def test_events_with_most_outlets_come_first():
    events = EventClusterer().cluster([LONE, *CLIMATE, *FIRE])
    assert [len(e.outlets) for e in events] == [3, 2, 1]


def test_a_lone_report_is_marked_as_such():
    [event] = EventClusterer().cluster([LONE])
    assert event.grouping is Grouping.SINGLE_REPORT
    assert event.headline == LONE.title


def test_reports_far_apart_in_time_are_not_grouped():
    later = report(FIRE[1].title, "Wire B", FIRE[1].text, day=date(2026, 12, 5))
    events = EventClusterer().cluster([FIRE[0], later])
    assert len(events) == 2


def test_a_weak_join_marks_the_grouping_uncertain():
    events = EventClusterer(join_threshold=0.05, confident_threshold=0.99).cluster(CLIMATE)
    [event] = events
    assert event.grouping is Grouping.UNCERTAIN


def test_the_same_reports_give_the_same_event_id():
    assert event_id(tuple(FIRE)) == event_id(tuple(reversed(FIRE)))
    assert event_id(tuple(FIRE)) != event_id(tuple(FIRE[:2]))
    assert Event(tuple(FIRE), Grouping.CONFIDENT).id == event_id(tuple(FIRE))


def test_event_dates_and_outlets():
    early = report("Early report on the fire", "Wire A", day=date(2026, 11, 21))
    event = Event((FIRE[1], early, FIRE[0]), Grouping.CONFIDENT)
    assert event.first_date == date(2026, 11, 21)
    assert event.last_date == DAY
    assert event.outlets == ("Wire B", "Wire A")


def test_an_event_needs_a_report():
    with pytest.raises(ValueError):
        Event((), Grouping.SINGLE_REPORT)


def test_duplicate_reports_are_counted_once():
    events = EventClusterer().cluster([FIRE[0], FIRE[0]])
    assert len(events[0].reports) == 1


def test_related_reports_resemble_the_event_but_were_not_grouped():
    from praxis.news.clustering import related_reports

    event = Event(tuple(FIRE[:2]), Grouping.CONFIDENT)
    found = related_reports(event, [FIRE[0], FIRE[2], LONE, *CLIMATE], limit=4)
    assert found == [FIRE[2]]
