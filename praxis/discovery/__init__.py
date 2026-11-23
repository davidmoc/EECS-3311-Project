"""Finding texts beyond the library and adding them to it."""

from praxis.discovery.finders import (
    DiscoveryError,
    SourceFinder,
    WebSearchSourceFinder,
    WikipediaSourceFinder,
    parse_found_sources,
    wikipedia_text,
)
from praxis.discovery.models import DiscoveryReport, DiscoveryRequest, FinderResult, FoundSource
from praxis.discovery.pages import RawPage, WebPage, WebPageReader, extract_page
from praxis.discovery.service import SourceDiscoveryService

__all__ = [
    "DiscoveryError",
    "DiscoveryReport",
    "DiscoveryRequest",
    "FinderResult",
    "FoundSource",
    "RawPage",
    "SourceDiscoveryService",
    "SourceFinder",
    "WebPage",
    "WebPageReader",
    "WebSearchSourceFinder",
    "WikipediaSourceFinder",
    "extract_page",
    "parse_found_sources",
    "wikipedia_text",
]
