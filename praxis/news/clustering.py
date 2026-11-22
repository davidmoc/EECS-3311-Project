"""Grouping reports of the same event (F01, SD03's ``EventClusterer.cluster``).

Deterministic, no model call: each report becomes a weighted bag of the
words in its headline and the start of its summary (TF-IDF: words that
are rare among the day's reports, such as names and places, count most),
and two reports are similar when those bags point the same way (cosine
similarity). A report joins the event it is most similar to if the
similarity reaches ``JOIN_THRESHOLD`` and their dates are close; otherwise
it starts an event of its own.

Joins below ``CONFIDENT_THRESHOLD`` mark the event's grouping as
uncertain, so the dashboard does not present it as established.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date

from praxis.documents import NewsArticle
from praxis.news.events import Event, Grouping

JOIN_THRESHOLD = 0.30
CONFIDENT_THRESHOLD = 0.40
MAX_DAYS_APART = 2
# Words of the summary used, after the headline; later text drifts to background.
SUMMARY_WORDS = 40
HEADLINE_WEIGHT = 2

_WORD = re.compile(r"[a-z][a-z'-]+")
_STOPWORDS = frozenset(
    """about above after again against also among amid and are around because been
    before being between both but by can could did does doing down during each
    for from further had has have having here how into its itself just more most
    new news not now off once only other our out over own same says said say
    should some such than that the their them then there these they this those
    through under until very was were what when where which while who whom why
    will with would year years week weeks day days today yesterday told tells
    after first last latest live video watch update updates""".split()
)


def _words(article: NewsArticle) -> Counter:
    summary = " ".join(article.text.split()[:SUMMARY_WORDS])
    counts: Counter = Counter()
    for text, weight in ((article.title, HEADLINE_WEIGHT), (summary, 1)):
        for word in _WORD.findall(text.lower()):
            word = word.strip("'-")
            if word.endswith("'s"):
                word = word[:-2]
            if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
                word = word[:-1]  # "strikes" and "strike" are the same word
            if len(word) >= 3 and word not in _STOPWORDS:
                counts[word] += weight
    return counts


class EventClusterer:
    def __init__(
        self,
        join_threshold: float = JOIN_THRESHOLD,
        confident_threshold: float = CONFIDENT_THRESHOLD,
        max_days_apart: int = MAX_DAYS_APART,
    ) -> None:
        self._join = join_threshold
        self._confident = confident_threshold
        self._days = max_days_apart

    def cluster(self, articles: list[NewsArticle]) -> list[Event]:
        """Events, those reported by most outlets first, then by most
        reports, then the most recent."""
        articles = list({a.id: a for a in articles}.values())
        vectors = _tf_idf([_words(a) for a in articles])
        groups: list[list[int]] = []
        weakest: list[float] = []  # each group's weakest join so far

        # Newest first, so each event is anchored on its latest report.
        order = sorted(
            range(len(articles)),
            key=lambda i: (articles[i].publication_date is None, -(articles[i].publication_date or _EPOCH).toordinal(), articles[i].title),
        )
        for i in order:
            best, best_score = None, 0.0
            for g, members in enumerate(groups):
                if not all(self._close_in_time(articles[i], articles[m]) for m in members):
                    continue
                score = max(_cosine(vectors[i], vectors[m]) for m in members)
                if score > best_score:
                    best, best_score = g, score
            if best is not None and best_score >= self._join:
                groups[best].append(i)
                weakest[best] = min(weakest[best], best_score)
            else:
                groups.append([i])
                weakest.append(1.0)

        events = []
        for members, score in zip(groups, weakest):
            reports = tuple(articles[m] for m in members)
            if len(reports) == 1:
                grouping = Grouping.SINGLE_REPORT
            elif score < self._confident:
                grouping = Grouping.UNCERTAIN
            else:
                grouping = Grouping.CONFIDENT
            events.append(Event(reports, grouping))
        return sorted(events, key=_rank)

    def _close_in_time(self, a: NewsArticle, b: NewsArticle) -> bool:
        if a.publication_date is None or b.publication_date is None:
            return True
        return abs((a.publication_date - b.publication_date).days) <= self._days


_EPOCH = date(1970, 1, 1)


def _rank(event: Event) -> tuple:
    newest = event.last_date or _EPOCH
    return (-len(event.outlets), -len(event.reports), -newest.toordinal(), event.headline)


def _tf_idf(bags: list[Counter]) -> list[dict[str, float]]:
    documents = len(bags)
    frequency: Counter = Counter(word for bag in bags for word in bag)
    vectors = []
    for bag in bags:
        # The +1 keeps a word every report shares from counting for
        # nothing: with two reports, their shared words are the evidence.
        vector = {w: n * (math.log((1 + documents) / (1 + frequency[w])) + 1) for w, n in bag.items()}
        norm = math.sqrt(sum(v * v for v in vector.values())) or 1.0
        vectors.append({w: v / norm for w, v in vector.items()})
    return vectors


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(w, 0.0) for w, v in a.items())
