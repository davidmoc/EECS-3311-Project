# EECS-3311-Project — Praxis

An AI-agent platform for researching current events, history and political
theory through a Marxist analytical framework. The Stage 1 design is in
[`Stage 1 - Proposal/`](Stage%201%20-%20Proposal/).

> **Status:** Stage 2 implementation in progress. Working now through the
> CLI: the multi-step research agent (F03), source-first question
> answering (F04), the reading library (F05), AI-annotated reading (F06),
> source and framing comparison (F10), the reader model (F13) and the
> workspace (F15). The news dashboard and GUI are not built yet.

## Prerequisites

- Python 3.10 or newer
- An OpenAI API key (only needed for features that call the LLM)

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Local configuration

Real keys are never committed. Copy the example file and put your own key in
the copy, which git ignores:

```bash
cp .env.example .env
```

Then edit `.env`:

| Variable | Required | Meaning |
|---|---|---|
| `OPENAI_API_KEY` | for LLM features | Your own key |
| `OPENAI_MODEL` | no | Chat model to use (a mini-tier model is enough) |
| `OPENAI_BASE_URL` | no | Another OpenAI-compatible provider |
| `PRAXIS_DATABASE_PATH` | no | SQLite file location (default `data/praxis.db`) |

## Command-line interface

Run `python -m praxis --help` (or `praxis --help` after `pip install -e .`).
Every command has `--help`.

```bash
# Multi-step research (F03): plan, gather sources step by step, then analyse
python -m praxis research "Why did the 1848 revolution in Germany fail?"
python -m praxis research "What is imperialism?" --max-steps 3 --max-tool-calls 4
python -m praxis research "Why did 1848 fail?" --save -t 1848   # keep it in the workspace

# Research sessions (F03): every research run is stored and can be continued
python -m praxis sessions list
python -m praxis sessions show 27004bab                # id prefix from the list
python -m praxis sessions continue 27004bab            # run the steps a limit left unrun
python -m praxis sessions continue 27004bab --focus "the role of the peasantry"

# Source-first questions (F04): passages first, then an AI explanation
python -m praxis ask "What did Marx say about the state?"
python -m praxis ask "Why are wages low?" --save -t wages   # keep it in the workspace

# Reading library (F05): five public-domain texts ship in data/library
python -m praxis library seed                # load them (no network needed)
python -m praxis library search "class struggle"
python -m praxis library browse --topic imperialism
python -m praxis library read 59983f05 --start 1 --count 5   # id prefix from search
python -m praxis library read 59983f05 --find "hitherto existing"
python -m praxis library download 59983f05 --to downloads
python -m praxis library import 1346 -t history   # any Project Gutenberg book

# Annotated reading (F06): AI annotations kept beside the author's text
python -m praxis annotate abdc2552 259 --type historical-context
python -m praxis library read abdc2552 --start 259 --count 1 --annotations
python -m praxis annotations list abdc2552
python -m praxis annotations remove 1a3c3cde        # id shown in brackets

# Source and framing comparison (F10): two to four texts, on one subject
python -m praxis compare b67c02e1 abdc2552 --on "the peasantry"
python -m praxis compare 59983f05:20-22 abdc2552:61,66   # named paragraphs
python -m praxis compare b67c02e1 abdc2552 --on "the bourgeoisie" --save -t 1848
python -m praxis comparisons list                # every comparison is stored
python -m praxis comparisons show 55a52998
python -m praxis sessions compare 1d668655       # the texts behind a research session

# Reader model (F13): see and correct what the system believes about you
python -m praxis profile show
python -m praxis profile know "surplus value" introductory
python -m praxis profile interest imperialism
python -m praxis profile depth detailed

# Workspace (F15): save and resume
python -m praxis workspace save-passage 59983f05 14 --note "key thesis"
python -m praxis workspace list
python -m praxis workspace open <item-id>
```

`research` asks the model for a short plan of typed steps (evidence,
theory, history) and runs them as library searches within a budget,
retrying a failed step once. When the planned steps run out, the model
assesses the passages (material relations, contradictions, historical
development, sources that disagree) and proposes follow-up searches,
which are added to the plan. Findings that cite no retrieved passage are
left out. Research stops when the assessment finds it sufficient, when
it proposes nothing new, or when the budget or the 20-source limit is
reached. The model then writes findings, historical context, theoretical
connections, contradictions and open questions, citing `[n]`. The command
prints every step (assessments are marked ◆), the concrete situation the
assessments established, and anything it could not do.

Every research run is stored with its sources, findings and plan.
`sessions continue` runs another round of a stored session: the reader's
`--focus` is searched first as typed, then the model's plan for it, then
any steps a limit left unrun, then the usual assessment. Earlier sources keep their numbers,
earlier searches are not repeated, each round has its own budget and may
add up to 10 sources, and the analysis is rewritten over all of them.
Research cut short by a limit is listed as incomplete.

`ask` searches the library's paragraphs, shows the ones that address the
question, and only then asks the model to explain them, citing `[n]`. If
no passage fits, it says so instead of answering from the model's memory.
Without an API key it still shows the passages.

`annotate` annotates one paragraph. The `--type` is `terminology`,
`historical-context`, `argument`, `framing`, `fact-check` or `connection`.
The model sees the paragraph with the paragraphs around it (two on each
side for a short paragraph). For historical context, fact checks and
connections, it also sees up to three other library passages that share
the paragraph's words, which it cites as `[n]`. Annotations are printed
behind a `┃` bar and marked as AI-generated. Anything the model could not
verify is listed under "Could not be verified", and references to
paragraphs the model was not shown are warned about. Annotations are
stored with the text, and `library read` marks the paragraphs that have
them (✎).

`compare` retrieves each chosen text separately: the paragraphs named
after the id, or the passages that best match `--on` and the model's
keywords for it. It prints each source (lettered A, B, …, with what the
library records about it) and its numbered passages first. The model then
judges whether the sources are comparable (if not, the reader is warned
that a direct comparison could mislead) and lists shared ground,
differences (terminology, emphasis, framing, assumptions, omission,
evidence), factual disagreements, and observations on framing, which are
marked as interpretation. Every point must cite passages from at least two
of the sources (an observation, from one); points that do not are left
out and counted. Without an API key the passages are still shown.
Comparisons of two or more sources are stored with their passages.
`sessions compare` compares the texts a research session drew on (up to
four, those that supplied most passages), on the research question, using
the passages the research retrieved; at most six passages are taken from
one text, and the reader is told which.

Reading with `library read` updates your reading progress, interests and
inferred knowledge automatically; `profile know` always overrides inference.

## Run the tests

```bash
python -m pytest
```

The tests use a fake LLM client and an in-memory database, so they need no
API key and no network access.

## Layout

| Path | Contents |
|---|---|
| `praxis/agent/` | `PoliticalResearchAgent` facade, `ResearchCorpus`, `PromptBuilder` |
| `praxis/app.py` | Composition root shared by CLI and GUI |
| `praxis/comparison/` | `SourceComparison`, `SourceProfile`, `CompareSourcesCommand` (F10) |
| `praxis/cli/` | Typer command-line interface |
| `praxis/config.py` | Local settings and API-key handling |
| `praxis/documents/` | Documents, passages, citations, annotations |
| `praxis/library/` | `LibraryService`, `DocumentProvider`, Gutenberg adapter |
| `praxis/llm/` | `LLMClient` interface and the OpenAI adapter |
| `praxis/persistence/` | SQLite database and repositories |
| `praxis/research/` | Research session, commands, plan, planner, concrete situation, assessment method, stopping policy |
| `praxis/reading/` | `AnnotationService` (F06) |
| `praxis/reader_model/` | Reader profile, its service, event bus and updater |
| `praxis/tools/` | Agent tools, tool manager and tool factory |
| `praxis/workspace/` | Saved items, workspace and its service |
| `data/library/` | Bundled public-domain texts and their catalogue |
| `tests/` | Automated tests |
| `docs/collaboration-log.md` | AI–human collaboration record |
