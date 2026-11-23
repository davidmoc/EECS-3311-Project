# Praxis

Praxis is a research and learning tool for current events, history and
political theory, read through a Marxist analytical framework. It keeps a
library of public-domain texts and a feed of current news, and an AI
agent answers from those sources: it shows the passages it relied on
first and cites them as `[n]`.

You can use it through a **desktop window** (GUI) or the **command line**
(CLI). Both reach all fifteen features (F01–F15) of the
[Stage 1 design](Stage%201%20-%20Proposal/).

**Contents:** [Quick start](#quick-start) ·
[What it can do](#what-it-can-do) ·
[Using the window](#using-the-window-gui) ·
[Using the command line](#using-the-command-line-cli) ·
[How each feature works](#how-each-feature-works) ·
[Troubleshooting](#troubleshooting) ·
[For developers](#for-developers)

---

## Quick start

You need **Python 3.10 or newer**. An **OpenAI API key** is optional, but
without one Praxis can find passages and cannot explain them.

```bash
# 1. Install (once)
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Add your API key (once)
cp .env.example .env               # then open .env and paste your key

# 3. Load the bundled texts (once; no network needed)
python -m praxis library seed

# 4. Start
python -m praxis gui               # the window
python -m praxis ask "What did Marx say about the state?"   # or the CLI
```

In the window, step 3 is the **Load bundled library** button on the Home
page.

Each new terminal needs `source .venv/bin/activate` before `python -m
praxis` will work.

### Settings in `.env`

`.env` is ignored by git, so your key is never committed.

| Variable | Required | Meaning |
|---|---|---|
| `OPENAI_API_KEY` | for AI features | Your own key |
| `OPENAI_MODEL` | no | Chat model to use (default `gpt-5-mini`; a mini-tier model is enough) |
| `OPENAI_BASE_URL` | no | Use another OpenAI-compatible provider |
| `PRAXIS_DATABASE_PATH` | no | Where your data is stored (default `data/praxis.db`) |
| `PRAXIS_WEB_DISCOVERY` | no | `off` stops Praxis looking beyond the library for texts (default on) |

### Beyond the library

The library is not a limit. When you ask a question, research, trace a
history, analyse an issue or build a learning path, Praxis first looks on
the web for texts on that subject (articles, analyses, reports and
primary documents, including Marxist and left publications, plus
Wikipedia background), saves the new ones to your library tagged with
the topic, and then works from the library as usual. The result says
which texts were added. Web search needs an OpenAI key and adds about
30–60 seconds; Wikipedia works without a key. Texts from the web are
shown and quoted in excerpts with a link to the original; Wikipedia
articles (CC BY-SA) are shown in full.

---

## What it can do

| Feature | What you get | In the window | On the command line |
|---|---|---|---|
| F01 News dashboard | Today's news grouped into events from several outlets, each with an AI summary | News | `news dashboard` |
| F02 Event view | One event's reports, where they differ, library background, an AI account | News → open an event | `news event` |
| F03 Multi-step research | The agent plans searches, gathers sources, assesses them and writes an analysis; runs can be continued | Research, Past research | `research`, `sessions` |
| F04 Source-first answers | The library passages that answer your question, then an explanation | Research → Ask a question | `ask` |
| F05 Reading library | Search, browse by topic, read, download, import from Project Gutenberg | Library | `library` |
| F06 Annotated reading | AI notes on a paragraph (terms, context, argument, framing, fact check, connections), kept apart from the author's text | Library | `annotate`, `annotations` |
| F07 Recommendations | Library texts to read on a topic, ranked, each with a reason | Research → Recommend readings | `recommend` |
| F08 Learning paths | What a topic or text assumes you know, in order, with passages for each step | Research → Build a learning path; Learning paths | `path` |
| F09 Historical context | Origins, a dated chronology, disputed views and gaps | Research → Trace the history | `history` |
| F10 Source comparison | How two to four texts (or news outlets) treat one subject | Compare | `compare`, `comparisons` |
| F11 Marxist analysis | Evidence, the theory that applies, and how they connect | Research → Marxist analysis | `analyze` |
| F12 Leftist traditions | Marxism beside traditions that differ on a topic, from their own texts | Research → Compare leftist traditions | `traditions` |
| F13 Reader model | What the system believes you know and why; correct any of it | Profile | `profile` |
| F14 Personalization | Explanations pitched to what you know; override per request | Profile, Research options | `--detail`, `--general` |
| F15 Workspace | Save texts, paragraphs, answers, research, events, comparisons and notes; pick up where you left off | Workspace, Save buttons | `workspace`, `--save` |

---

## Using the window (GUI)

```bash
python -m praxis gui            # or: python -m praxis.gui
```

Choose a page on the left:

- **Home**: where to start. **In the news** shows the most widely reported
  events as cards, fetched when the app starts (press Refresh to fetch
  again); click one to open it on the News page. **Pick up where you left
  off** shows texts you have begun and not finished, with your progress;
  click one to continue at the paragraph you reached. **Your learning
  path** shows the path in progress and its next step; Continue opens that
  step's reading. Home also says whether a language model is set up, and
  on first run offers to load the fourteen bundled texts.
- **Library**: search the texts or filter them by topic, then click one to
  read it. The reader fills the page and shows the whole text as one
  scroll; how far you get is saved in your profile. Click a paragraph's
  number (¶12) for the **Ask about** menu: pick an annotation type, and the
  reader says it is being written, then shows it under the paragraph in its
  own colour, apart from the author's words. Annotations are kept. The same
  menu saves the paragraph to your workspace; **◀ Library** goes back to the
  list.
- **News**: fetch the latest news, or show what is already stored. Each
  event groups reports from several outlets and has an AI summary. Open an
  event for its reports, background from the library and an AI account.
  From there you can research it, compare its outlets, trace its history
  or save it.
- **Research**: pick a task (ask a question, research in several steps,
  trace the history, Marxist analysis, compare leftist traditions,
  recommend readings, build a learning path), type the topic, and
  optionally ask for more or less detail, or a general answer, for this
  request only. Results show their passages first; each passage has a link
  that opens the text at that paragraph.
- **Past research**: every research run. Reopen one as it was left,
  continue it with a new focus, or follow up with an analysis, a
  comparison of the texts behind it, or a comparison of traditions.
- **Compare**: tick two to four texts and name a subject. Earlier
  comparisons are listed to reopen.
- **Learning paths**: your stored paths. Mark a step done, already known
  or skipped; done and known steps are added to what the system knows
  about you.
- **Workspace**: everything you saved, to search, add notes to, or
  remove. "Continue" goes back to where the item came from; a text opens
  where you stopped reading. The Save buttons are on the Library,
  Research and News pages.
- **Profile**: what the system believes you know and where each belief
  came from, your interests and your reading. Correct or remove any of
  them, set how detailed explanations are, turn personalization on or
  off, and describe your background in your own words.

AI requests run in the background one at a time, so the window stays
responsive. The status bar shows what is running.

**Only on the command line:** importing a book from Project Gutenberg,
saving a text as a `.txt` file, removing an annotation, comparing named
paragraphs (rather than a subject), and resetting the whole profile.

---

## Using the command line (CLI)

Every command has `--help`, for example `python -m praxis research --help`.
The examples can be copied as they are.

**Three things that work everywhere:**

- **Ids.** Texts, events, sessions, paths and comparisons have ids, shown
  in brackets in lists and search results. You only need to type the first
  few characters (e.g. `59983f05`). The ids below are examples; use your
  own.
- **Saving.** `ask`, `research`, `sessions continue`, `compare` and
  `news event` take `--save`, plus `-t <tag>` (repeatable) to tag what
  you saved.
- **One-off personalization.** `--detail brief|standard|detailed` (on
  `ask`, `research`, `sessions continue`, `annotate`) and `--general` (on
  those and on `history`, `analyze`, `traditions`, `recommend`) change one
  request without touching your profile.

### Ask and research

```bash
python -m praxis ask "What did Marx say about the state?"         # passages, then an explanation (F04)
python -m praxis ask "Where does surplus value come from?" --detail brief

python -m praxis research "Why did the 1848 revolution in Germany fail?"   # multi-step (F03)
python -m praxis research "What is imperialism?" --max-steps 3 --max-tool-calls 4
python -m praxis research "Why did 1848 fail?" --save -t 1848

python -m praxis sessions list                                    # every research run is stored
python -m praxis sessions show 27004bab
python -m praxis sessions continue 27004bab                       # run the steps a limit left unrun
python -m praxis sessions continue 27004bab --focus "the role of the peasantry"
python -m praxis sessions analyze 27004bab                        # Marxist analysis of its sources (F11)
python -m praxis sessions compare 27004bab                        # compare the texts behind it (F10)
python -m praxis sessions traditions 27004bab                     # compare traditions on its question (F12)
```

### History, analysis and traditions

```bash
python -m praxis history "the defeat of the 1848 revolution in Vienna"     # F09
python -m praxis history "the history of capitalism" --broad      # trace it even if judged too broad

python -m praxis analyze "the condition of English factory workers in the 1840s"   # F11
python -m praxis analyze "1848 in Germany" --framework "the state as an instrument of class rule"

python -m praxis traditions "the abolition of the state after the revolution"      # F12
```

### Library and annotations

```bash
python -m praxis library seed                         # load the 14 bundled texts (no network)
python -m praxis library topics                       # topics and how many texts each has
python -m praxis library browse --topic imperialism
python -m praxis library search "class struggle"
python -m praxis library read 59983f05 --start 1 --count 5        # records your progress
python -m praxis library read 59983f05 --find "hitherto existing"
python -m praxis library read abdc2552 --start 259 --count 1 --annotations
python -m praxis library download 59983f05 --to downloads         # save as .txt
python -m praxis library import 1346 -t history                   # any Project Gutenberg book number
python -m praxis library discover "Libya since 2011" -s "oil" -s "NATO war"   # find texts on the web and add them

python -m praxis annotate abdc2552 259 --type historical-context  # F06
python -m praxis annotations list abdc2552
python -m praxis annotations remove 1a3c3cde
```

Annotation types: `terminology`, `historical-context`, `argument`,
`framing`, `fact-check`, `connection`.

### News

```bash
python -m praxis news dashboard                       # fetch, group into events, summarise (F01)
python -m praxis news dashboard --offline --limit 12 --days 2     # from stored news only
python -m praxis news event e19d03b8                  # open an event (F02)
python -m praxis news event e19d03b8 --compare        # how the outlets cover it (F10)
python -m praxis news event e19d03b8 --history        # its historical background (F09)
python -m praxis news event e19d03b8 --research       # research it, starting from its reports
python -m praxis news event e19d03b8 --save -t libya
python -m praxis news refresh                         # fetch and store only
python -m praxis news list --days 2 --outlet guardian
python -m praxis news feeds                           # the outlets (data/news/feeds.json)
python -m praxis library read 5ce83d9c                # an article's feed summary
```

### Compare sources

```bash
python -m praxis compare b67c02e1 abdc2552 --on "the peasantry"   # 2–4 texts, one subject
python -m praxis compare 59983f05:20-22 abdc2552:61,66            # named paragraphs instead
python -m praxis comparisons list
python -m praxis comparisons show 55a52998
```

### Recommendations and learning paths

```bash
python -m praxis recommend "the state"                # F07
python -m praxis recommend                            # from your strongest interests

python -m praxis path build "surplus value"           # F08
python -m praxis path build --text b67c02e1           # what a library text assumes
python -m praxis path list
python -m praxis path show 30a812b3
python -m praxis path mark 30a812b3 1 done            # done, known, skip or todo
```

### Your profile

```bash
python -m praxis profile show                         # everything believed about you, and why (F13)
python -m praxis profile know "surplus value" introductory   # none, introductory, intermediate, advanced
python -m praxis profile forget "surplus value"
python -m praxis profile interest imperialism
python -m praxis profile interest imperialism --remove       # and do not re-infer it
python -m praxis profile depth detailed               # brief, standard or detailed
python -m praxis profile personalize false            # true or false (F14)
python -m praxis profile background "History student, new to Marx"
python -m praxis profile reset                        # forget everything (asks first)
```

Reading with `library read` updates your progress, interests and inferred
knowledge automatically. What you state with `profile know` always wins
over what is inferred.

### Workspace

```bash
python -m praxis workspace save-text 59983f05 --note "start here" -t basics   # F15
python -m praxis workspace save-passage 59983f05 14 --note "key thesis"
python -m praxis workspace note "Question for class" "Is the state neutral?" -t state
python -m praxis workspace list
python -m praxis workspace list --kind research       # document, passage, annotation, event,
                                                      # research, comparison or note
python -m praxis workspace search "state"
python -m praxis workspace open <item-id>             # shows the item and how to continue from it
python -m praxis workspace remove <item-id>
```

---

## How each feature works

These sections explain what happens behind each command, and how Praxis
keeps the AI tied to its sources. The window uses the same methods.

<details>
<summary><b>Research and sessions (F03)</b></summary>

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
any steps a limit left unrun, then the usual assessment. Earlier sources
keep their numbers, earlier searches are not repeated, each round has its
own budget and may add up to 10 sources, and the analysis is rewritten
over all of them. Research cut short by a limit is listed as incomplete.

</details>

<details>
<summary><b>Source-first answers (F04)</b></summary>

`ask` searches the library's paragraphs, shows the ones that address the
question, and only then asks the model to explain them, citing `[n]`. If
no passage fits, it says so instead of answering from the model's memory.
Without an API key it still shows the passages.

</details>

<details>
<summary><b>Annotations (F06)</b></summary>

`annotate` annotates one paragraph. The model sees the paragraph with the
paragraphs around it (two on each side for a short paragraph). For
historical context, fact checks and connections, it also sees up to three
other library passages that share the paragraph's words, which it cites
as `[n]`. Annotations are printed behind a `┃` bar and marked as
AI-generated. Anything the model could not verify is listed under "Could
not be verified", and references to paragraphs the model was not shown
are warned about. Annotations are stored with the text, and `library
read` marks the paragraphs that have them (✎).

</details>

<details>
<summary><b>Source comparison (F10)</b></summary>

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

</details>

<details>
<summary><b>News and events (F01, F02)</b></summary>

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

`news event` opens one event. It shows the reports with their links,
library passages that may give background (found with the model's
keywords), and other stored reports from around the same days that
resemble it but were not grouped with it. The model then writes an
account citing the reports: what happened, where the reports differ (each
account is set out, not resolved), background from the library
(presented as interpretation), and open questions. An event whose latest
report is from today or yesterday is marked as still developing.
`--compare` compares one report per outlet with `compare`'s method.
`--research` starts a research session whose first sources are the
event's reports. `--history` traces the background starting from the
event's reports. `--save` keeps the event in the workspace.

</details>

<details>
<summary><b>Recommendations (F07)</b></summary>

`recommend` searches the library's passages for the topic (news is left
out), ranks texts the catalogue tags with the topic ahead of texts that
only match its words, and asks the model to rank up to five of them with a
reason and a difficulty. Texts you have finished go last; your progress is
shown beside each. The model may also name well-known works the library
lacks; these are marked as not checked. Without a model the texts are
ranked by matching passages. When little is known about you, or
personalization is off, you are told the ranking rests on the topic alone.

</details>

<details>
<summary><b>Learning paths (F08)</b></summary>

`path build` asks the model what the target assumes (concepts, events,
theories, earlier texts), in learning order, and drops what you said you
know (`profile know`). Texts on the target and each step are then found
on the web and added to the library (see "Beyond the library"). Each
remaining step gets up to two passages, first from the texts found for
that step, then from the rest of the library, never from the target text
and never repeated across steps; a step nothing is found for gets a short
AI orientation and is reported as a gap. Steps are "needed" only when the model calls them
essential and your knowledge is on record; knowledge inferred from your
reading turns a step into a suggestion rather than dropping it. Paths
are stored; `path mark` records each step as done, already known or
skipped. Done and known steps are published to the reader model, which
records the topic as known at introductory level, so later paths leave it
out.

</details>

<details>
<summary><b>Historical context (F09)</b></summary>

`history` asks the model whether the topic is narrow enough to trace from
a few passages (if not, it suggests narrower topics) and for searches from
the origins onward. It searches the library only (not other news), then
asks the model to organise the passages into an overview, origins, a
dated chronology with turning points marked, continuities, disputed
interpretations (labelled as interpretation), and gaps the passages
leave. Every item must cite a retrieved passage or it is left out. The
texts it cites are listed to read further.

</details>

<details>
<summary><b>Marxist analysis (F11)</b></summary>

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

</details>

<details>
<summary><b>Leftist traditions (F12)</b></summary>

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

</details>

<details>
<summary><b>Reader model and personalization (F13, F14)</b></summary>

The reader model records what you know (stated by you or inferred from
your reading), your interests, your reading progress, your preferred
detail and your background. `profile show` lists each belief with where
it came from. Reading with `library read` updates progress, interests and
inferred knowledge automatically; `profile know` always overrides
inference, and an interest you remove is not inferred again.

Explanations are adapted to your profile: what you are recorded as
knowing about the request's own topic is put first, and if nothing is
recorded the model is told not to assume you know it. Inferred knowledge
is described to the model as a guess. When little is known about you, or
personalization is off, answers stay general.

</details>

---

## Troubleshooting

| Problem | What to do |
|---|---|
| `No module named praxis` | Run from the project folder with the virtual environment active (`source .venv/bin/activate`). |
| "The library is empty" | Run `python -m praxis library seed`, or press the button on the GUI's Home page. |
| Passages appear but no explanation | No API key was found. Put `OPENAI_API_KEY` in `.env` (see [Settings](#settings-in-env)). The Home page shows whether a model is configured. |
| A news feed fails | The other feeds are still read. Use `news dashboard --offline` to work from stored news. |
| An id is not found, or matches several items | Type more characters of the id, or copy it from the list command. |
| Start over with no data | Delete `data/praxis.db` (or the file `PRAXIS_DATABASE_PATH` points at), then seed the library again. |

Known limitations are recorded in
[`docs/collaboration-log.md`](docs/collaboration-log.md).

---

## For developers

### Run the tests

```bash
python -m pytest
```

The tests use a fake LLM client and an in-memory database, so they need no
API key and no network access.

### Layout

| Path | Contents |
|---|---|
| `praxis/app.py` | Composition root shared by CLI and GUI |
| `praxis/agent/` | `PoliticalResearchAgent` facade, `ResearchCorpus`, `PromptBuilder` |
| `praxis/research/` | Research session, commands, plan, planner, concrete situation, assessment method, stopping policy, historical context (F09), Marxist analysis (F11) |
| `praxis/reading/` | `AnnotationService` (F06), `RecommendationService` (F07), `PrerequisiteService` and `LearningPath` (F08), `IdeologicalContextService` (F12) |
| `praxis/comparison/` | `SourceComparison`, `SourceProfile`, `CompareSourcesCommand` (F10) |
| `praxis/news/` | `NewsProvider`, `RSSNewsAdapter`, `NewsService`, `EventClusterer`, `NewsSummaryService`, `Event` (F01, F02) |
| `praxis/library/` | `LibraryService`, `DocumentProvider`, Gutenberg adapter (F05) |
| `praxis/discovery/` | `SourceDiscoveryService`, `SourceFinder` (web search, Wikipedia), `WebPageReader`: finding texts beyond the library |
| `praxis/documents/` | Documents, passages, citations, annotations |
| `praxis/reader_model/` | Reader profile, its service, event bus and updater, `PersonalizationService` (F13, F14) |
| `praxis/workspace/` | Saved items, workspace and its service (F15) |
| `praxis/tools/` | Agent tools, tool manager and tool factory |
| `praxis/llm/` | `LLMClient` and `WebSearchClient` interfaces and their OpenAI adapters |
| `praxis/persistence/` | SQLite database and repositories |
| `praxis/cli/` | Typer command-line interface |
| `praxis/gui/` | PySide6 graphical interface: main window, views and their controllers, task runner, qt-material theme |
| `praxis/config.py` | Local settings and API-key handling |
| `data/library/` | Bundled public-domain texts and their catalogue |
| `data/news/feeds.json` | The news feeds `news refresh` reads |
| `tests/` | Automated tests |
| `Stage 1 - Proposal/` | Design: features, class and sequence diagrams, use cases, traceability |
| `docs/collaboration-log.md` | AI–human collaboration record |
