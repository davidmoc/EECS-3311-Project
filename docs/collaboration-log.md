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

### 2026-11-21 — Multi-step research agent, first slice (F03)

- **Task:** Implement a working first version of F03 (UC03, SD01): plan, run research commands within a budget, synthesise.
- **Input/Instruction:** "let's do the next slice of praxis. I know it's past the due date, that's fine. We'll do multiple slices today so don't worry about doing everything in one."
- **AI contribution:** Chose F03 as the next slice and split it into three: (1) this end-to-end skeleton; (2) `ConcreteSituation` and the dialectical assessment that drives plan revision; (3) persisting sessions and continuing research. Added the `praxis/research` package: `ResearchSession`, `ResearchBudget`, `StepRecord`, the Command pattern (`ResearchCommand` with `RetrieveEvidenceCommand`, `RetrieveTheoryCommand`, `TraceHistoricalDevelopmentCommand`), `ResearchContext`, `ResearchPlan`, `ResearchPlanner` (`create_initial_plan`, `revise_after_failure`), `ResearchStoppingPolicy`, `ResearchResult`. Added `PoliticalResearchAgent.research()`, the research prompts in `PromptBuilder`, and the `praxis research` command. 302 automated tests. One live run against `gpt-5-mini` ("Why did the 1848 revolution in Germany fail?", 44 s, 8,916 tokens): the model's plan parsed into three typed steps, 12 sources were gathered and all were cited. Two claims beyond the displayed excerpts (Radetzky; the Prussian bourgeoisie's "cooling down" after February) were checked against ¶176 and ¶137 of *Revolution and Counter-Revolution* and are in the text.
- **Problems met:**
  - `praxis.research` uses `praxis.agent.corpus`, and the agent facade uses `praxis.research`. Python runs a package's `__init__.py` before any of its modules, so importing `praxis.research.commands` first would have loaded the facade mid-import. `praxis/agent/__init__.py` now loads the facade's names lazily (PEP 562). A test imports each package first in a fresh interpreter.
  - The first stopping policy counted model calls against the loop. With a one-call budget, the planner used the call and research stopped before any retrieval, leaving no sources. A test caught it. Retrieval steps make no model calls, so the model budget now limits only the synthesis (fixed in its own commit, `c1591c9`).
  - Two AI-written tests used the wrong API (`set_level` instead of `update_level`; `passages` as a property instead of a method) and were corrected.
- **Design changes from Stage 1 introduced here:**
  - Only three of the eight Stage 1 command classes exist so far. All three search library passages and differ in purpose (evidence, theory, history); the purpose is recorded per source, and the synthesis prompt groups sources by it.
  - `ResearchPlanner.createInitialPlan` asks the model for a plan in a fixed line format (`history: <keywords>`). If the model is missing, fails, or replies in another form, a fixed plan is used and the reader is told. The question as asked is always searched last, to top up.
  - `revisePlan` exists only for the tool-failure branch of SD01 (`revise_after_failure`): a failed command is retried once, immediately, and if it fails again the missing material is reported. Revision from a `ResearchAssessment` comes in the next slice; until then the loop runs the initial plan.
  - `ResearchStoppingPolicy.shouldStop(session, assessment, budget)` is `should_stop(session, budget, plan, context)` for now: it stops on budget, on a full source list, or when the plan is done. It also returns the reason, so the reader is told why research stopped and which steps were not run. Model calls are not part of the loop's budget (see above).
  - `ResearchSession` also records each step, model calls, tokens and warnings, so the result can show how the research was done.
  - No `ConcreteSituation`, `DialecticalMaterialistResearchMethod` or `MaterialistAnalysis` yet. The synthesis is one model call that writes fixed sections (findings, historical context, theoretical connections, open questions), with open questions split out. As with F04, sources are returned with a warning when the model fails, rather than only an error.
  - `ResearchResult.getRecommendedReadings()` returns the texts behind the cited sources.
- **Human contribution:** Reviewed the code and approved it ("i reviewed the code, its good").
- **Outcome:** Eight code commits and this documentation commit, pushed to `main`.

### 2026-11-21 — Multi-step research agent, second slice: assessment and plan revision (F03)

- **Task:** Add SD01's `updateSituation → assess → shouldStop → revisePlan` loop: a `ConcreteSituation` built from the evidence, a dialectical-materialist assessment of it, and plan revision driven by that assessment.
- **Input/Instruction:** "let's do the next slice of praxis".
- **AI contribution:** Took slice 2 of the F03 split made in the previous session. Added `ConcreteSituation` with typed findings (`MaterialRelation` with `RelationType`, `Contradiction`, `HistoricalDevelopment`, `ConflictingEvidence`), `ConcreteSituationBuilder`, `ResearchAssessment` with `FollowUp`, `DialecticalMaterialistResearchMethod.assess()` and its prompt, `InvestigateRelationCommand` and `InvestigateContradictionCommand`, `ResearchPlanner.revise_plan()`, and two new stop reasons in `ResearchStoppingPolicy`. Wired them into `PoliticalResearchAgent.research()`, fed the established findings into the synthesis prompt, and showed assessments and the concrete situation in `praxis research`. 331 automated tests. One live run against `gpt-5-mini` with the question used in slice 1 ("Why did the 1848 revolution in Germany fail?", 97 s, 21,250 tokens, against 44 s and 8,916 tokens before): one assessment found 4 contradictions, 8 relations, 4 historical developments and 2 conflicts between sources, and added 3 follow-up searches. Research then stopped at the 20-source limit. Two findings were checked against the text and are in it: the king's conditional refusal of the crown and "draw the sword" (¶259 of *Revolution and Counter-Revolution*), and the Assembly's "open declaration of war", the recall of deputies and the workers "ready to take up arms" (¶272).
- **Problems met:**
  - A reply of only `verdict: sufficient` was treated as unreadable, because "unreadable" was tested as "no findings". A CLI test caught it. `parse_assessment` now returns None only when no line is in the reply format.
  - The live run showed conflicts as `vs | Passage depicts …`: the model wrote `conflict: [1] vs [10] | …`, and removing the citation marks left a field of just "vs". Fixed in its own commit (`459e60e`), with a regression test confirmed to fail before the fix.
  - The live analysis dates the Dresden and Baden risings to "May 1848". They were in May 1849; the passage gives only "the 4th of May". The model filled the year from memory. The citation checks cannot catch a wrong detail inside a correctly cited sentence.
  - The model cited `[310]` in an open question, confusing source [18]'s paragraph number (¶310) with a source number. The existing citation check flagged it as unsupported. At the user's request ("fix the citation prompt"), the answer, synthesis and assessment prompts now state that the ¶ number is a paragraph locator, not a citation number (`CITATION_NUMBER_RULE`); not yet re-checked in a live run.
  - One AI-written test called `book.passages[0]` (it is a method), the same mistake as in slice 1. Another assumed a search would add new sources when the passages had already been retrieved. Both were corrected.
  - One commit (`8c1b9db`) was first made with a failing test because the shell pipeline `pytest | tail` hid pytest's exit status. It was caught before pushing and the commit amended.
- **Design changes from Stage 1 introduced here:**
  - SD01 assesses after every retrieval step. Here the assessment runs once per round, when the queued plan is used up, because each assessment is a model call. One model call is always kept for the synthesis, so the default budget (4 calls) allows the plan, up to two assessments and the synthesis. Assessments do not count as research steps against `max_iterations`.
  - `DialecticalMaterialistResearchMethod.assess()` is one model call that does the work Stage 1 splits across `identifyMissingRelations`, `identifyContradictions`, `identifyHistoricalQuestions`, `identifyConflictingEvidence` and `evaluateDevelopment`. The model replies in a fixed line format (`contradiction: <side> | <side> | <relationship> [n]`, `search: history | <keywords>`, `verdict: sufficient`). `MaterialRelationAnalyzer`, `HistoricalDevelopmentAnalyzer`, `ContradictionAnalyzer` and `EvidenceEvaluator` are not separate classes. `ResearchAssessment.missing_relations` and `historical_questions` are derived from its follow-up searches.
  - `ConcreteSituation` holds typed findings, each with the source numbers it rests on, instead of Stage 1's free attributes (`materialConditions`, `actors`, `institutions`, `productiveForces`, …). `RelationType` (class, production, institutional, ideological) covers the relation kinds. `Contradiction` keeps two sides and their relationship; Stage 1's `historicalOrigin`, `currentForm`, `development`, `significance` and `confidence` are not modelled. There is no separate `Evidence` class: a corpus source number serves as the evidence.
  - `ConcreteSituationBuilder` only adds a finding if it cites a retrieved passage (two for a conflict). References to sources that were not retrieved are removed, and the reader is told how many findings were left out (UC03: "If insufficient evidence exists for a claim, the claim is … excluded").
  - `ResearchPlan` remembers commands already run, so `revisePlan` never repeats a search. `revise_plan` returns the commands it added.
  - `ResearchStoppingPolicy.shouldStop(session, assessment, budget)` is `should_stop(session, budget, plan, context, assessment)`. New reasons: the assessment judged the research sufficient (`sufficientCoverage`), or revision added no new search (`noUsefulNextSteps`). Budget limits still take priority.
  - Two of the five remaining Stage 1 commands now exist: `InvestigateRelationCommand` and `InvestigateContradictionCommand`. Like the first three, they search library passages and record their purpose. `CompareSourcesCommand`, `TestExplanationCommand` and `SynthesizeResearchCommand` are not built.
  - No `MaterialistAnalysis` class yet. The synthesis receives the situation's findings and open questions and adds a "Contradictions" section.
  - Each step now takes 3 passages (was 4), the source list holds 20 (was 12), and the initial plan has at most 4 steps (was 5), so follow-up searches have room after the first round. Default budget raised to 10 steps, 14 tool calls and 240 s.
- **Human contribution:** _Code review pending._
- **Outcome:** Seven code commits and this documentation commit.
