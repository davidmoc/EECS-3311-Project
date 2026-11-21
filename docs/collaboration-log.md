# AI–Human Collaboration Log

Running record for the Stage 2 report (sections 5 and 6). Entries are added as
work happens. "Human contribution" records only what was actually decided or
reviewed; where review has not happened yet, it says so.

## AI tools used

| Tool | LLM model | Purpose | Token / money cost |
|---|---|---|---|
| Claude Code (CLI) | Claude Fable 5.2 (`claude-fable-5-2`) on 2026-11-16; Claude Opus 5.5 (`claude-opus-5-5`) on 2026-11-18 and 2026-11-19 | Design review, code generation, tests | _to be filled from `/cost` at the end of each session_ |

### Cost per session

Development cost comes from `/cost` in Claude Code at the end of each session.
Application cost (the app's own OpenAI calls) comes from the Usage page on
platform.openai.com.

| Date | Claude Code tokens | Claude Code cost | OpenAI app cost | Work done |
|---|---|---|---|---|
| 2026-11-16 | 5.7m | $5.90 | $0 | Design review, stack and scope decisions, foundation layers |
| 2026-11-18 | _from `/cost`_ | _from `/cost`_ | $0 | Library, reader model, workspace, CLI |
| 2026-11-19 | _from `/cost`_ | _from `/cost`_ | _from OpenAI usage page_ | Source-first question answering (F04) |

## Interactions

### 2026-11-16 — Review of Stage 1 design against Stage 2 requirements

- **Task:** Understand what Stage 2 requires and whether the Stage 1 design is ready to implement.
- **Input/Instruction:** "instructions/ contains the instructions I was given… Don't build anything yet, just examine."
- **AI contribution:** Read the three instruction documents and the full Stage 1 proposal. Reported inconsistencies: F12 has two different names; section 4 cites an SD08 that does not exist; sequence diagrams use methods and types (`compareSources()`, `AgentResponse`, `ToolResult`, `LearningPath`) missing from the class diagram; SD01 bypasses `ResearchCommand.execute()`.
- **Human contribution:** Approved carrying these fixes into the implementation as documented design changes.
- **Outcome:** List of design changes to record in the Stage 2 report.

### 2026-11-16 — Technology stack

- **Task:** Choose the implementation language and libraries.
- **Input/Instruction:** "What tech stack would you recommend?" followed by "would Go instead of Python be better or worse, assuming I know Go but not Python."
- **AI contribution:** Checked the KUMA repository (Stage 3 testing tool) and found it is a Python SDK that calls the agent in-process. Recommended Python, PySide6 GUI, Typer CLI, SQLite, OpenAI behind an adapter. Argued Go was a worse fit (no class inheritance for the UML design, KUMA would need a bridge) while noting its advantage of developer familiarity.
- **Human contribution:** Raised the Go alternative; confirmed Java is not required; chose Python, an OpenAI mini-tier model, and a single local user with no accounts.
- **Outcome:** Stack fixed as recommended.

### 2026-11-16 — Scope

- **Task:** Decide how to fit 15 designed features into the remaining time.
- **AI contribution:** Proposed three tiers: eight features at full depth (F01, F03, F04, F05, F06, F10, F13, F15), five lighter features reusing the same services (F02, F07, F08, F09, F11), and two to decide later (F12, F14).
- **Human contribution:** Accepted the tiers; set the working cadence of several small commits per day.
- **Outcome:** Build order: shared foundation first, then features by tier.

### 2026-11-16 — Foundation layers

- **Task:** Build the layers every feature depends on.
- **AI contribution:** Wrote configuration loading, the document model, the `LLMClient` interface with `OpenAILLMAdapter`, the SQLite `DocumentRepository`, and the tool layer (`Tool`, `ToolManager`, `ToolFactory`, `LibrarySearchTool`), with 64 automated tests.
- **Design changes from Stage 1 introduced here:**
  - `ToolResult`, `LLMResponse` and `Prompt` added as explicit classes (used but undefined in Stage 1).
  - `Citation` carries the document title and author so it can be displayed on its own.
  - `LibrarySearchTool` reads from `DocumentRepository` for now; Stage 1 routes it through `DocumentProvider`.
  - `ToolManager` returns failures as `ToolResult` values instead of raising, so the agent can re-plan.
- **Human contribution:** _Code review pending._
- **Outcome:** Committed on branch `stage2`.

### 2026-11-18 — Reading library, reader model, workspace and CLI

- **Task:** Implement F05, F13 and F15 end to end with a command-line interface.
- **Input/Instruction:** "Let's continue building the eecs 3311 project."
- **AI contribution:** Chose this slice from the scope tiers. Wrote `DocumentProvider` with `PublicTextArchiveAdapter` (Project Gutenberg), `LibraryService`, a bundled sample library of five public-domain texts, the reader model (`ReaderProfile`, `KnowledgeProfile`, `InterestProfile`, `ReadingHistory`), `ReaderProfileService`, the Observer pair `LearningEventBus`/`ReaderModelUpdater`, `Workspace`/`SavedItem`/`WorkspaceService`, their SQLite repositories, and the Typer CLI (`library`, `profile`, `workspace` commands). 174 automated tests.
- **Problems met:** Project Gutenberg's main site was down for maintenance, so texts were fetched from the `gutenberg.pglaf.org` mirror and committed to `data/library/` so seeding works offline. Two AI-written tests had wrong expectations (a phrase quoted from a different edition of the Manifesto; a miscounted topic) and were corrected against the real data.
- **Design changes from Stage 1 introduced here:**
  - `LibraryService` imports through `DocumentProvider`; `LibrarySearchTool` still reads `DocumentRepository` directly.
  - The reader model records whether each knowledge level was inferred or stated by the reader; stated levels are never overridden by inference (supports F13's "correct inaccurate assessments").
  - `ActivityObserver.onActivity()` is implemented as `on_activity()`; event types `DocumentRead`, `TopicResearched` and `PrerequisiteMarkedKnown` were added (Stage 1 left events untyped).
  - `SavedItem` stores a content snapshot so saved material survives the source disappearing (F15 error case). F15 had no sequence diagram in Stage 1 (section 4 cites a nonexistent SD08).
  - `Application` (`praxis/app.py`) added as a composition root shared by the CLI and the future GUI.
- **Human contribution:** _Code review pending._
- **Outcome:** Ten commits pushed to `main`.

### 2026-11-19 — Defects found from call traces

- **Task:** Check the implemented features against the design by tracing real executions.
- **Input/Instruction:** "show me traces of the features you implemented", then "i noticed those things, fix them".
- **AI contribution:** Ran each CLI feature under a profiler and printed the `praxis` call tree. The traces exposed three defects, which were then fixed, each with a regression test:
  1. `ReaderModelUpdater` loaded and saved the whole profile once per topic (10 loads, 9 saves to finish one text). Now one load and one save per event.
  2. Looking a text up by short id loaded every document's full text (about 1.3 MB); so did the "is the library empty" check. Now an id-only SQL query and `COUNT(*)`.
  3. Gutenberg volunteer credits ("Produced by …") and scan notes became paragraph 1 of two texts, so they could be cited as the author's words. Now stripped from the opening paragraphs.
- **Human contribution:** Reviewed the traces and asked for the three defects to be fixed.
- **Outcome:** Three fix commits (`458c10a`, `903b0bb`, `a99da9f`); 184 tests pass.

### 2026-11-19 — Source-first question answering (F04)

- **Task:** Implement F04 (UC04, SD02) end to end.
- **Input/Instruction:** "lets do the next part of praxis".
- **AI contribution:** Chose F04 as the next slice because it introduces the agent facade that F03 builds on. Added a full-text passage index (SQLite FTS5) to `SQLDocumentRepository`, the `passage_search` tool, `ResearchCorpus`, `AgentResponse`, `PromptBuilder`, `PoliticalResearchAgent.answer_question()`, the `praxis ask` command and `ask --save`. 243 automated tests. One live run against `gpt-5-mini` ("What did Marx say about the state?") returned six passages, all cited; a quotation falling outside the displayed excerpt was checked against ¶23 of the Manifesto and is genuine.
- **Problems met:** Searching the raw question ranked prefaces that mention Marx above passages about the state, because "Marx" is a rare word in the index. Fixed by asking the model for search keywords first and searching the raw question only to top up. One AI-written CLI test assumed "money" appears nowhere in the library; it appears in several texts, so the test question was changed.
- **Design changes from Stage 1 introduced here:**
  - Retrieval is by passage, through a new `passage_search` tool and `DocumentRepository.search_passages()`; SD02 shows `LibrarySearch` returning documents. Paragraphs under eight words (headings, credits) are not indexed, so they cannot be cited.
  - `answer_question()` makes two model calls: one to choose search keywords (falls back to the question if it fails) and one to explain. SD02 shows one.
  - If the model fails after passages were found, the passages are still returned with a warning; SD02 shows only `displayError()`. The same applies when no API key is configured.
  - Every `[n]` in the explanation is checked against the retrieved sources. References to sources that were not retrieved, and explanations that cite nothing, produce warnings.
  - `AgentResponse` (used but undefined in Stage 1) has a status (`ANSWERED`, `NO_SOURCES`, `EXPLANATION_FAILED`), keeps passages and explanation separate, and records whether reader context was used.
  - `ResearchController` is not a separate class yet; the `ask` CLI command plays that role.
- **Human contribution:** _Code review pending._
- **Outcome:** Seven code commits and this documentation commit, pushed to `main`.

### 2026-11-21 — Defects found from F04 call traces

- **Task:** Check the F04 implementation by tracing real executions.
- **Input/Instruction:** "show me the traces of what's just been built", then the two fixes to apply: "check the limit before each search, not only after adding a passage" and "add a small indexed_documents table with a primary key, so the check becomes cheap".
- **AI contribution:** Traced `ask` (answered, no sources, model failure, no API key, `--save`) and the passage-index backfill through the CLI, printing the `praxis` call tree and every SQL statement; the model was scripted so the traces cost nothing. Two defects found and fixed, each with a regression test confirmed to fail before the fix:
  1. `_retrieve` ran the second passage search even when the keyword search had already filled the corpus, then discarded the results. The limit is now checked before each search.
  2. The startup check for unindexed documents read the whole FTS index (1,240 rows) on every application start. A keyed `indexed_documents` table now answers it. This also stopped documents with no indexable passages from being re-indexed on every open.
- **Human contribution:** Reviewed the traces and chose both fixes.
- **Outcome:** Two fix commits; 247 tests pass. Existing databases re-index once on first open, because `indexed_documents` starts empty.
