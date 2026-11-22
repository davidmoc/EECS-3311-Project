"""AI annotations on passages of a text (F06, UC06, SD04).

``AnnotationService.generate_annotation`` follows SD04: it takes the
passage with the paragraphs around it, searches the library for other
passages when the kind of annotation needs them, asks the model, and
returns an ``Annotation`` kept apart from the author's text. What the model
says it could not verify is kept on the annotation as its uncertainties.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from uuid import UUID

from praxis.agent import check_citations
from praxis.agent.corpus import ResearchCorpus
from praxis.agent.prompts import PromptBuilder, reader_context
from praxis.documents import Annotation, AnnotationType, Document, Passage
from praxis.llm import LLMClient, LLMError
from praxis.reader_model import ReaderProfile
from praxis.persistence import AnnotationRepository
from praxis.tools import ToolManager

PASSAGE_SEARCH = "passage_search"
# Paragraphs on each side of the passage given to the model as context.
SURROUNDING_PARAGRAPHS = 1
# A passage shorter than this is often unclear on its own (UC06: "If the
# selected passage is too ambiguous without surrounding context"), so it
# gets WIDER_SURROUNDING paragraphs on each side instead.
SHORT_PASSAGE_WORDS = 40
WIDER_SURROUNDING = 2
# Other library passages an annotation may draw on.
CONTEXT_PASSAGES = 3
# Searched for, so that matches inside the surrounding text can be skipped.
CONTEXT_SEARCH_LIMIT = 12

NO_LLM_ERROR = (
    "No language model is configured (set OPENAI_API_KEY), so annotations "
    "cannot be generated. Existing annotations can still be read."
)
UNKNOWN_CITATION_WARNING = (
    "The annotation refers to {labels}, which {verb} not among its sources; "
    "treat those statements as unsupported."
)
NOT_STORED_WARNING = "The annotation could not be stored, so it will not be shown again: {}"
NO_CONTEXT_WARNING = (
    "No other library passage bears on this passage, so the annotation "
    "rests on the text itself and general background."
)


class AnnotationError(Exception):
    """No annotation could be generated; the message says why."""


@dataclass(frozen=True)
class AnnotationResult:
    """What ``generate_annotation`` hands back to the controller.

    ``annotation`` is None when the model replied only that it could not
    annotate the passage (SD04's "insufficient evidence" branch); the
    reasons are then in ``limitations``.
    """

    annotation: Annotation | None
    limitations: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    tokens_used: int = 0
    searched_library: bool = False


class AnnotationService:
    def __init__(
        self,
        tools: ToolManager,
        llm: LLMClient | None = None,
        prompts: PromptBuilder | None = None,
        repository: AnnotationRepository | None = None,
    ) -> None:
        """Without ``repository``, annotations are generated but not stored."""
        self._tools = tools
        self._llm = llm
        self._prompts = prompts or PromptBuilder()
        self._repository = repository

    # --- existing annotations (UC06 step 4) ----------------------------------

    def get_annotations(self, passage_id: UUID) -> list[Annotation]:
        """The passage's stored annotations, oldest first."""
        return self._repository.for_passage(passage_id) if self._repository else []

    def annotations_for(self, document: Document) -> list[Annotation]:
        """All of the document's stored annotations, in text order."""
        return self._repository.for_document(document.id) if self._repository else []

    def find_annotation(self, id_prefix: str) -> UUID:
        """The stored annotation whose id starts with ``id_prefix``."""
        prefix = id_prefix.strip().lower()
        if not prefix:
            raise AnnotationError("An annotation id is required.")
        matches = self._repository.find_ids(prefix) if self._repository else []
        if not matches:
            raise AnnotationError(f"No annotation with id starting '{prefix}'.")
        if len(matches) > 1:
            raise AnnotationError(f"Id '{prefix}' matches {len(matches)} annotations; use more characters.")
        return matches[0]

    def remove_annotation(self, annotation_id: UUID) -> None:
        if self._repository is None or not self._repository.delete(annotation_id):
            raise AnnotationError(f"There is no annotation {annotation_id}.")

    # --- new annotations (SD04) ----------------------------------------------

    def generate_annotation(
        self,
        document: Document,
        passage: Passage,
        annotation_type: AnnotationType,
        profile: ReaderProfile | None = None,
    ) -> AnnotationResult:
        """Annotate ``passage`` of ``document``.

        Raises ``AnnotationError`` if no model is configured or the model
        call fails: unlike an answer to a question, an annotation has no
        retrieved passages worth showing without the model's commentary.
        """
        if passage.document_id != document.id:
            raise ValueError("The passage does not belong to this document.")
        if self._llm is None:
            raise AnnotationError(NO_LLM_ERROR)

        warnings: list[str] = []
        surrounding = surrounding_passages(document, passage)
        corpus = None
        if annotation_type.searches_library:
            corpus = self._search_context(passage, surrounding, warnings)

        prompt = self._prompts.build_annotation_prompt(
            document, passage, surrounding, annotation_type, corpus, profile
        )
        try:
            response = self._llm.generate(prompt)
        except LLMError as exc:
            raise AnnotationError(f"The annotation could not be generated: {exc}") from exc

        content, uncertainties = self._prompts.parse_annotation(response.text)
        if not content:
            return AnnotationResult(
                None,
                limitations=tuple(uncertainties)
                or ("The model returned no annotation for this passage.",),
                warnings=tuple(warnings),
                tokens_used=response.total_tokens,
                searched_library=corpus is not None,
            )

        sources = corpus.sources if corpus is not None else []
        _, unknown = check_citations(content, corpus or ResearchCorpus())
        if unknown:
            warnings.append(UNKNOWN_CITATION_WARNING.format(
                labels=", ".join(f"[{n}]" for n in unknown),
                verb="is" if len(unknown) == 1 else "are",
            ))

        annotation = Annotation(
            passage_id=passage.id,
            type=annotation_type,
            content=content,
            document_id=document.id,
            locator=passage.locator,
            sources=tuple(source.citation for source in sources),
            uncertainties=tuple(uncertainties),
            personalized=reader_context(profile) is not None,
        )
        if self._repository is not None:
            try:
                self._repository.save(annotation)
            except sqlite3.Error as exc:
                warnings.append(NOT_STORED_WARNING.format(exc))
        return AnnotationResult(
            annotation,
            warnings=tuple(warnings),
            tokens_used=response.total_tokens,
            searched_library=corpus is not None,
        )

    def _search_context(
        self, passage: Passage, surrounding: list[Passage], warnings: list[str]
    ) -> ResearchCorpus:
        """Other library passages that share the passage's words.

        The passage text itself is the query: the index ranks rare shared
        words (names, places, terms) highest. Matches the model already
        sees as surrounding text are skipped.
        """
        corpus = ResearchCorpus()
        result = self._tools.execute_tool(
            PASSAGE_SEARCH, {"query": passage.text, "limit": CONTEXT_SEARCH_LIMIT}
        )
        if not result.success:
            warnings.append(
                f"Library search failed ({result.error}), so the annotation "
                "rests on the text itself and general background."
            )
            return corpus
        skipped = {p.id for p in surrounding} | {passage.id}
        for match in result.items:
            if len(corpus) >= CONTEXT_PASSAGES:
                break
            if match.passage.id not in skipped:
                corpus.add_passage(match.document, match.passage)
        if corpus.is_empty:
            warnings.append(NO_CONTEXT_WARNING)
        return corpus


def surrounding_passages(document: Document, passage: Passage) -> list[Passage]:
    """``passage`` with the paragraphs on either side of it, in order.

    Short passages get a wider window, since a heading-like line or a
    one-sentence paragraph often cannot be understood on its own.
    """
    passages = document.passages()
    index = next((i for i, p in enumerate(passages) if p.id == passage.id), None)
    if index is None:
        return [passage]
    reach = (
        WIDER_SURROUNDING
        if len(passage.text.split()) < SHORT_PASSAGE_WORDS
        else SURROUNDING_PARAGRAPHS
    )
    return passages[max(0, index - reach) : index + reach + 1]
