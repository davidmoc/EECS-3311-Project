"""Facade over the agent subsystem.

Controllers call ``PoliticalResearchAgent`` and nothing else; retrieval,
prompt construction, the LLM and citation checking stay behind it.
"""

from __future__ import annotations

import re

from praxis.agent.corpus import ResearchCorpus, Source
from praxis.agent.prompts import PromptBuilder, reader_context
from praxis.agent.response import AgentResponse, ResponseStatus
from praxis.llm import LLMClient, LLMError
from praxis.reader_model.service import ReaderProfileService
from praxis.tools import ToolManager

PASSAGES_PER_QUESTION = 6
PASSAGE_SEARCH = "passage_search"

# "[2]" or "[1, 3]" in the model's explanation.
_CITATION_MARK = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")

NO_SOURCES_WARNING = (
    "No passage in the library addresses this question, so no answer was "
    "generated. Try other words, or import texts on this subject."
)
NO_LLM_WARNING = (
    "No language model is configured (set OPENAI_API_KEY), so only the "
    "passages are shown."
)
UNCITED_WARNING = (
    "The explanation does not cite any passage; treat it as unsupported "
    "commentary."
)


class AgentError(Exception):
    """The request itself was unusable (for example, an empty question)."""


class PoliticalResearchAgent:
    def __init__(
        self,
        tools: ToolManager,
        profiles: ReaderProfileService,
        llm: LLMClient | None = None,
        prompts: PromptBuilder | None = None,
    ) -> None:
        """``llm`` may be None: the agent then still retrieves passages but
        cannot explain them."""
        self._tools = tools
        self._profiles = profiles
        self._llm = llm
        self._prompts = prompts or PromptBuilder()

    # --- F04: source-first question answering ------------------------------

    def answer_question(self, question: str) -> AgentResponse:
        question = question.strip()
        if not question:
            raise AgentError("Ask a question first.")

        profile = self._profiles.get_profile()
        usage = _Usage()
        warnings: list[str] = []

        terms = self._search_terms(question, usage)
        corpus = self._retrieve(question, terms, warnings)
        if corpus.is_empty:
            return AgentResponse(
                question,
                ResponseStatus.NO_SOURCES,
                warnings=(*warnings, NO_SOURCES_WARNING),
                tokens_used=usage.tokens,
                search_terms=tuple(terms),
            )

        sources = tuple(corpus.sources)
        if self._llm is None:
            return AgentResponse(
                question,
                ResponseStatus.EXPLANATION_FAILED,
                sources,
                warnings=(*warnings, NO_LLM_WARNING),
                search_terms=tuple(terms),
            )

        prompt = self._prompts.build_question_prompt(question, corpus, profile)
        try:
            response = self._llm.generate(prompt)
        except LLMError as exc:
            # The passages are the primary answer, so they are still returned.
            return AgentResponse(
                question,
                ResponseStatus.EXPLANATION_FAILED,
                sources,
                warnings=(*warnings, f"The explanation could not be generated: {exc}"),
                tokens_used=usage.tokens,
                search_terms=tuple(terms),
            )
        usage.tokens += response.total_tokens

        cited, unknown = check_citations(response.text, corpus)
        if unknown:
            labels = ", ".join(f"[{n}]" for n in unknown)
            warnings.append(
                f"The explanation refers to {labels}, which "
                f"{'is' if len(unknown) == 1 else 'are'} not among the sources; "
                "treat those statements as unsupported."
            )
        if not cited:
            warnings.append(UNCITED_WARNING)

        return AgentResponse(
            question,
            ResponseStatus.ANSWERED,
            sources,
            explanation=response.text,
            cited=tuple(cited),
            warnings=tuple(warnings),
            personalized=reader_context(profile) is not None,
            tokens_used=usage.tokens,
            search_terms=tuple(terms),
        )

    # --- steps ---------------------------------------------------------------

    def _search_terms(self, question: str, usage: _Usage) -> list[str]:
        """Keywords chosen by the model, or none if it cannot help.

        The question is always searched as well, so a failure here only
        makes retrieval less focused; it never stops the answer.
        """
        if self._llm is None:
            return []
        try:
            response = self._llm.generate(self._prompts.build_search_terms_prompt(question))
        except LLMError:
            return []
        usage.tokens += response.total_tokens
        return self._prompts.parse_search_terms(response.text)

    def _retrieve(
        self, question: str, terms: list[str], warnings: list[str]
    ) -> ResearchCorpus:
        """Passages for the model's keywords first, then for the question
        as asked, until ``PASSAGES_PER_QUESTION`` distinct passages."""
        queries = ([" ".join(terms)] if terms else []) + [question]
        corpus = ResearchCorpus()
        for query in queries:
            result = self._tools.execute_tool(
                PASSAGE_SEARCH, {"query": query, "limit": PASSAGES_PER_QUESTION}
            )
            if not result.success:
                warnings.append(f"Library search failed: {result.error}")
                continue
            for match in result.items:
                if len(corpus) >= PASSAGES_PER_QUESTION:
                    return corpus
                corpus.add_passage(match.document, match.passage)
        return corpus


def check_citations(text: str, corpus: ResearchCorpus) -> tuple[list[Source], list[int]]:
    """The sources ``text`` cites, in order of first mention, and any cited
    numbers that are not in ``corpus``."""
    numbers: dict[int, None] = {}
    for group in _CITATION_MARK.findall(text):
        for number in group.split(","):
            numbers.setdefault(int(number), None)
    cited = [corpus.source(n) for n in numbers if corpus.has_source(n)]
    unknown = [n for n in numbers if not corpus.has_source(n)]
    return cited, unknown


class _Usage:
    """Tokens spent on one request, across all of its model calls."""

    def __init__(self) -> None:
        self.tokens = 0
