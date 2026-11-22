"""Reading RSS and Atom feeds into NewsArticle documents (F01)."""

from datetime import date
from uuid import NAMESPACE_URL, uuid5

import pytest

from praxis.news import FeedSource, NewsProviderError, RSSNewsAdapter, parse_feed, read_feeds
from praxis.news.providers import MAX_SUMMARY_CHARS

FEED = FeedSource("wire", "Example Wire", "https://example.org/rss")

RSS2 = b"""<?xml version="1.0"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel><title>Example</title>
<item>
  <title>Dockworkers strike &amp; ports close</title>
  <link>https://example.org/strike</link>
  <description>&lt;p&gt;Dockworkers walked out on Monday.&lt;/p&gt;&lt;p&gt;Ports along the coast closed.&lt;/p&gt;</description>
  <category>Labour</category><category>Ports</category><category>Labour</category>
  <pubDate>Sun, 22 Nov 2026 23:50:00 -0500</pubDate>
  <dc:creator>A. Reporter</dc:creator>
</item>
<item><title>No link here</title></item>
<item><link>https://example.org/no-title</link></item>
</channel></rss>"""

RDF = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel><title>World</title></channel>
<item rdf:about="https://example.org/a">
  <title>Talks stall</title><link>https://example.org/a</link>
  <description>Negotiators left without agreement.</description>
  <dc:date>2026-11-21T08:00:00Z</dc:date>
</item>
</rdf:RDF>"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Atom example</title>
<entry>
  <title type="html">Election &lt;b&gt;results&lt;/b&gt;</title>
  <link rel="alternate" href="https://example.org/election"/>
  <link rel="enclosure" href="https://example.org/photo.jpg"/>
  <published>2026-11-20T12:00:00+02:00</published>
  <author><name>B. Writer</name></author>
  <summary>The count finished overnight.</summary>
  <category term="Elections"/>
</entry>
</feed>"""


def test_rss2_items_become_news_articles():
    articles = parse_feed(RSS2, FEED)

    assert len(articles) == 1  # items without a title or a link are skipped
    article = articles[0]
    assert article.kind == "news"
    assert article.title == "Dockworkers strike & ports close"
    assert article.outlet == "Example Wire"
    assert article.author == "A. Reporter"
    assert article.text == "Dockworkers walked out on Monday.\n\nPorts along the coast closed."
    assert article.topics == ("Labour", "Ports")
    # 23:50 at UTC-5 is the next day in UTC.
    assert article.publication_date == date(2026, 11, 23)
    assert article.source_url == "https://example.org/strike"
    assert article.id == uuid5(NAMESPACE_URL, "https://example.org/strike")


def test_feed_summaries_are_not_reproducible_text():
    article = parse_feed(RSS2, FEED)[0]
    assert not article.can_reproduce()
    assert not article.downloadable
    assert "Example Wire" in article.license


def test_rss1_rdf_items_are_read():
    [article] = parse_feed(RDF, FEED)
    assert article.title == "Talks stall"
    assert article.author == "Example Wire"  # no author: the outlet
    assert article.publication_date == date(2026, 11, 21)


def test_atom_entries_are_read():
    [article] = parse_feed(ATOM, FEED)
    assert article.title == "Election results"
    assert article.source_url == "https://example.org/election"
    assert article.author == "B. Writer"
    assert article.text == "The count finished overnight."
    assert article.topics == ("Elections",)
    assert article.publication_date == date(2026, 11, 20)


def test_long_summaries_are_cut_at_a_word():
    long = ("word " * 1000).encode()
    data = RSS2.replace(b"Dockworkers walked out on Monday.", long)
    article = parse_feed(data, FEED)[0]
    assert len(article.text) <= MAX_SUMMARY_CHARS + 2
    assert article.text.endswith("word …")


@pytest.mark.parametrize("data", [b"<html><body>Not found</body></html>", b"not xml at all <"])
def test_a_page_that_is_not_a_feed_is_an_error(data):
    with pytest.raises(NewsProviderError):
        parse_feed(data, FEED)


def test_adapter_fetches_the_feeds_url():
    requested = []

    def fetch(url):
        requested.append(url)
        return RSS2

    articles = RSSNewsAdapter(FEED, fetch).get_recent_news()
    assert requested == ["https://example.org/rss"]
    assert len(articles) == 1


def test_bundled_feed_list_is_readable():
    feeds = read_feeds()
    assert len(feeds) >= 2
    assert all(f.url.startswith("https://") for f in feeds)


def test_unreadable_feed_list_is_an_error(tmp_path):
    with pytest.raises(NewsProviderError):
        read_feeds(tmp_path / "missing.json")
