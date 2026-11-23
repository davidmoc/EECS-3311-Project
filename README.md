# EECS-3311-Project — Praxis

An AI-agent platform for researching current events, history and political
theory through a Marxist analytical framework. The Stage 1 design is in
[`Stage 1 - Proposal/`](Stage%201%20-%20Proposal/).

> **Status:** Stage 2 implementation. All fifteen Stage 1 features (F01–F15)
> work through both the CLI and the GUI. A few options are CLI-only:
> removing annotations, naming the paragraphs to compare, and resetting
> the whole reader profile. Answers depend on a language model
> (see below); without one, passages are still found but nothing is
> explained. The collaboration log (`docs/collaboration-log.md`) records known
> limitations.

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

## Graphical interface

```bash
python -m praxis gui            # or: python -m praxis.gui
```

The window has a page per area, chosen on the left:

- **Home**: whether a language model is configured, and a button to load
  the fourteen bundled texts into an empty library.
- **Library** (F05, F06): search the texts or filter them by topic, read
  one ten paragraphs at a time (progress is recorded in your profile), and
  ask for an AI annotation of a paragraph. Annotations are kept and shown
  under their paragraph, set apart from the author's words.
- **News** (F01, F02): fetch the latest news from the feeds, or show what
  is stored; events are grouped from several outlets, each with an AI
  summary. Open an event for its reports, background from the library and
  an AI account, then research it, compare its outlets, trace its
  history or save it.
- **Research** (F03, F04, F07–F09, F11, F12, F14): choose what to do (ask a
  question, research in several steps, trace the history, Marxist
  analysis, compare leftist traditions, recommend readings, build a
  learning path), type the topic, and optionally ask for more or less
  detail or a general answer for this request only. Results show their
  passages first; each has a link that opens the text at that paragraph.
- **Past research** (F03, F10–F12): every research run, to reopen as it was
  left, continue with a new focus, or follow up with an analysis, a
  comparison of the texts behind it, or a comparison of traditions.
- **Compare** (F10): tick two to four texts and name a subject; earlier
  comparisons are listed to reopen.
- **Workspace** (F15): everything you saved (texts, paragraphs, answers,
  research, events, notes), to search, add notes to, or remove.
  "Continue" goes back to where the item came from: a text opens where you
  stopped reading. Save buttons are on the Library, Research and News pages.
- **Learning paths** (F08): stored paths; mark a step done, already known
  or skipped. Done and known steps are added to your reader model.
- **Profile** (F13, F14): what the system believes you know and where each
  belief came from, your interests and reading; correct or remove any of
  them, and set the explanation detail and personalization.

Requests to the model run in the background, one at a time, so the window
stays responsive; the status bar shows what is running.

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

# Reading library (F05): fourteen public-domain texts ship in data/library
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

# News dashboard (F01): current events from the feeds in data/news/feeds.json
python -m praxis news dashboard               # fetch, group into events, summarise
python -m praxis news dashboard --offline --limit 12   # from stored news only
python -m praxis news event e19d03b8          # open an event (F02): id from the dashboard
python -m praxis news event e19d03b8 --compare   # how the outlets cover it (F10)
python -m praxis news event e19d03b8 --research  # research it, starting from its reports
python -m praxis news event e19d03b8 --save -t libya
python -m praxis news refresh                 # fetch and keep (needs network)
python -m praxis news list --days 2
python -m praxis news list --outlet guardian
python -m praxis library read 5ce83d9c        # an article's feed summary

# Reading recommendations (F07): ranked library texts, each with why
python -m praxis recommend "the state"
python -m praxis recommend                     # from your strongest interests

# Learning paths (F08): the background a topic or text assumes
python -m praxis path build "surplus value"
python -m praxis path build --text b67c02e1     # for a library text
python -m praxis path list                       # every path is stored
python -m praxis path mark 30a812b3 1 done       # or known, skip, todo
python -m praxis path show 30a812b3

# Historical context (F09): origins, chronology, disputed views, gaps
python -m praxis history "the defeat of the 1848 revolution in Vienna"
python -m praxis history "the history of capitalism" --broad   # trace it even if too broad
python -m praxis news event 56eefcd0 --history   # the background of a news event

# Marxist theoretical analysis (F11): evidence, theory, and how they connect
python -m praxis analyze "the condition of English factory workers in the 1840s"
python -m praxis analyze "1848 in Germany" --framework "the state as an instrument of class rule"
python -m praxis sessions analyze 27004bab        # on a research session's sources

# Leftist traditions (F12): Marxism beside traditions that differ on a topic
python -m praxis traditions "the abolition of the state after the revolution"
python -m praxis sessions traditions 27004bab     # on a research session's question

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

# Personalized assistance (F14): explanations use what you know of the topic;
# override it for one request without changing your profile
python -m praxis ask "Where does surplus value come from?" --detail brief
python -m praxis research "the state in 1848" --general   # not adapted to you

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

`news refresh` reads six RSS and Atom feeds (BBC News, Al Jazeera, The
Guardian, Deutsche Welle, CBC News, Peoples Dispatch). Only what a feed
publishes for syndication is kept: headline, summary, link, date, author
and categories. An unreachable feed is reported and the others are still
read, and stored news stays available offline. News is kept out of
`library browse` and `library search`, but `ask`, `research` and
`compare` can draw on it.

`news dashboard` refreshes the feeds (unless `--offline`), then groups the
last two days' reports into events without a model: reports whose
headlines and opening words share rare words (names, places) are grouped
if they are at most two days apart. Events covered by most outlets come
first. For each event with two or more reports, the model writes a
neutral title, a two- or three-sentence summary citing the reports as
`[n]`, and categories, and says whether the reports are really about one
event. A summary that cites no report, or a report that does not exist,
is not shown: the card lists the headlines instead. A single report is
marked as such and shows the outlet's own summary. Weakly grouped events
are marked "grouping uncertain". Cards are stored, so an unchanged event
is not summarised again.

`news event` opens one event (F02). It shows the reports with their
links, library passages that may give background (found with the
model's keywords), and other stored reports from around the same days
that resemble it but were not grouped with it. The model then writes an
account citing the reports: what happened, where the reports differ (each
account is set out, not resolved), background from the library
(presented as interpretation), and open questions. An event whose latest
report is from today or yesterday is marked as still developing.
`--compare` compares one report per outlet with `compare`'s method.
`--research` starts a research session whose first sources are the
event's reports. `--save` keeps the event in the workspace.

`recommend` searches the library's passages for the topic (news is left
out), ranks texts the catalogue tags with the topic ahead of texts that
only match its words, and asks the model to rank up to five of them with a
reason and a difficulty. Texts you have finished go last; your progress is
shown beside each. The model may also name well-known works the library
lacks; these are marked as not checked. Without a model the texts are
ranked by matching passages. When little is known about you, or
personalization is off, you are told the ranking rests on the topic alone.

`path build` asks the model what the target assumes (concepts, events,
theories, earlier texts), in learning order, and drops what you said you
know (`profile know`). Each remaining step gets up to two library
passages, never from the target text and never repeated across steps; a
step the library has nothing on gets a short AI orientation and is
reported as a gap. Steps are "needed" only when the model calls them
essential and your knowledge is on record; knowledge inferred from your
reading turns a step into a suggestion rather than dropping it. Paths
are stored; `path mark` records each step as done, already known or
skipped. Done and known steps are published to the reader model, which
records the topic as known at introductory level, so later paths leave it
out.

`history` asks the model whether the topic is narrow enough to trace from
a few passages (if not, it suggests narrower topics) and for searches from
the origins onward. It searches the library only (not other news), then
asks the model to organise the passages into an overview, origins, a
dated chronology with turning points marked, continuities, disputed
interpretations (labelled as interpretation), and gaps the passages
leave. Every item must cite a retrieved passage or it is left out. The
texts it cites are listed to read further. `news event --history` starts
from the event's reports and traces their background.

`analyze` searches the library for evidence on the issue (or, with
`sessions analyze`, reuses a research session's sources and findings), asks
the model which Marxist concepts the evidence gives reason to apply (a
`--framework` you name comes first), and searches for theoretical passages
on each. The model then writes what the evidence shows, how each concept
applies (citing both a theory passage and an evidence passage, or it is
left out), interpretations marked supported or tentative, other readings
within Marxist analysis, and the limits where a concept does not fit. An
analysis with no supported claim is flagged as tentative. The theoretical
texts it cites are listed to study further.

`traditions` asks the model which leftist traditions hold a materially
different position on the topic, and which library authors represent each
(Marxism, including Lenin, comes first). If none differs, none is
introduced. Each tradition's passages are searched in its representatives'
own texts first; a tradition with no text of its own is described from
other authors, and you are told; one with no material at all is left out.
The model then states each position, the conditions it developed in, where
the traditions disagree (citing passages from both sides), and the Marxist
assessment of the others, kept apart from their own positions. Each
tradition's texts are listed to read in its own words.

Explanations are adapted to your reader profile (F14): what you are
recorded as knowing about the request's own topic is put first, and if
nothing is recorded the model is told not to assume you know it. Inferred
knowledge is described to the model as a guess. When little is known about
you, or personalization is off, answers stay general. `--detail
brief|standard|detailed` (on `ask`, `research`, `sessions continue` and
`annotate`) and `--general` (on those and on `history`, `analyze`,
`traditions` and `recommend`) apply to one request only.

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
| `praxis/gui/` | PySide6 graphical interface: main window, views and their controllers, task runner |
| `praxis/config.py` | Local settings and API-key handling |
| `praxis/documents/` | Documents, passages, citations, annotations |
| `praxis/library/` | `LibraryService`, `DocumentProvider`, Gutenberg adapter |
| `praxis/news/` | `NewsProvider`, `RSSNewsAdapter`, `NewsService`, `EventClusterer`, `NewsSummaryService`, `Event` (F01) |
| `praxis/llm/` | `LLMClient` interface and the OpenAI adapter |
| `praxis/persistence/` | SQLite database and repositories |
| `praxis/research/` | Research session, commands, plan, planner, concrete situation, assessment method, stopping policy, historical context (F09), Marxist analysis (F11) |
| `praxis/reading/` | `AnnotationService` (F06), `RecommendationService` (F07), `PrerequisiteService` and `LearningPath` (F08), `IdeologicalContextService` (F12) |
| `praxis/reader_model/` | Reader profile, its service, event bus and updater, `PersonalizationService` (F14) |
| `praxis/tools/` | Agent tools, tool manager and tool factory |
| `praxis/workspace/` | Saved items, workspace and its service |
| `data/library/` | Bundled public-domain texts and their catalogue |
| `data/news/feeds.json` | The news feeds `news refresh` reads |
| `tests/` | Automated tests |
| `docs/collaboration-log.md` | AI–human collaboration record |
