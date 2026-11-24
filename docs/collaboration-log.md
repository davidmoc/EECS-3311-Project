# AI–Human Collaboration Log

Running record for the Stage 2 report (sections 5 and 6). Entries are added as
work happens. "Human contribution" records only what was actually decided or
reviewed; where review has not happened yet, it says so.

## AI tools used

| Tool | LLM model | Purpose | Token / money cost |
|---|---|---|---|
| Claude Code (CLI) | Claude Fable 5.2 (`claude-fable-5-2`) on 2026-11-16; Claude Opus 5.5 (`claude-opus-5-5`) from 2026-11-18 to 2026-11-21 | Design review, code generation, tests | _to be filled from `/cost` at the end of each session_ |

### Cost per session

Development cost comes from `/cost` in Claude Code at the end of each session.
Application cost (the app's own OpenAI calls) comes from the Usage page on
platform.openai.com.

| Date | Claude Code tokens | Claude Code cost | OpenAI app cost | Work done |
|---|---|---|---|---|
| 2026-11-16 | 47k | $6.27 | $0 | Design review, stack and scope decisions, foundation layers |
| 2026-11-18 | 88k output | $7.76 | $0 | Library, reader model, workspace, CLI; trace-found fixes (Nov 19) |
| 2026-11-19 | 57k output | $4.65 | _from OpenAI usage page_ | Source-first question answering (F04); trace-found fixes (Nov 21) |
| 2026-11-21 | 60k output | $4.64 | _from OpenAI usage page_ | Multi-step research agent, first slice (F03) |
| 2026-11-21 | 73k output | $4.70 | _from OpenAI usage page_ | Multi-step research agent, second slice (F03); citation prompt fix; review records |
| 2026-11-21 | 63k output | $6.62 | _from OpenAI usage page_ | Multi-step research agent, third slice (F03): stored and continued research; focus-first fix; research call trace |
| 2026-11-22 | 56k output | $5.14 | _from OpenAI usage page_ | AI-annotated reading, first slice (F06); unseen-paragraph and list-display fixes |

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
- **Human contribution:** Reviewed the code.
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
- **Human contribution:** Reviewed the code.
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
- **Human contribution:** Reviewed the code.
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
- **Human contribution:** Reviewed the code.
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
- **Human contribution:** Asked for the paragraph-number citation fix; reviewed the code.
- **Outcome:** Seven code commits and this documentation commit.

### 2026-11-21 — Multi-step research agent, third slice: stored and continued research (F03)

- **Task:** Make research sessions persistent and let the reader continue one (UC03 postcondition "a persistent research session… The user may… continue the research"; UC15 "If a research session was incomplete, it can be restored as an incomplete session").
- **Input/Instruction:** "let's do the next slice of praxis".
- **AI contribution:** Took slice 3 of the F03 split. Added rounds to `ResearchSession` (`resume()`, a budget per round, the round on each `StepRecord`, the reader's focus per round), kept the `ResearchPlan` on the `ResearchResult` (steps run and steps still queued), `ResearchRepository` with `SQLResearchRepository` (a `research_sessions` table), `PoliticalResearchAgent.continue_research()`, `get_research()`, `find_research()` and `list_research()`, `ResearchPlanner.plan_follow_up()`, the `praxis sessions list|show|continue` commands, and `research --save`, which saves to the workspace and links back to the session. 358 automated tests. One live run against `gpt-5-mini` on a scratch database: "Why did the 1848 revolution in Germany fail?" (86 s, 21,222 tokens, 20 sources, 17 cited, no warnings), then `sessions continue --focus "the role of the peasantry"` (58 s, 15,404 more tokens). Round 2 added sources [21]–[30] after the unchanged [1]–[20] and repeated none of round 1's searches. No citation in either analysis pointed past the last source, so the paragraph-number confusion seen in slice 2 did not recur; one run is not proof it is fixed. Two claims in the round-2 analysis were checked against the text and are in it: Metternich turning the serfs against the Galician nobility in 1846 (¶115 of *Revolution and Counter-Revolution*), and the peasant as "not revolutionary, but conservative" (¶54 of the Manifesto).
- **Problems met:**
  - `continue_research` first read the earlier plan with `if previous.plan`. `ResearchPlan` defines `__len__` (the number of queued commands), so in Python a plan with nothing queued counts as false, and the record of searches already run was discarded. A test written to check that a continuation repeats no search caught it before commit; the check is now `is not None`.
  - A restored result never equalled the original because `ResearchPlan` had no `__eq__`; one was added (same objective, queue, and searches run).
  - Storage could not be exported from `praxis.persistence`'s `__init__`: `praxis.tools` imports `praxis.persistence`, and storage imports the research commands, which import `praxis.tools`. It is imported as `praxis.persistence.research`; the import-order test now covers it.
  - In the live continuation, the 10-source limit for a round was reached after four of the five steps, so the round ended before its assessment and before the top-up search of the focus as typed. At the user's request, the focus as typed is now searched first, before the model's plan for it. The limit still ends rounds before an assessment (it did so in round 1 too); not changed.
- **Design changes from Stage 1 introduced here:**
  - Stage 1 names `ResearchRepository` and `continueResearch(sessionId, request)` but gives neither a sequence diagram. `continue_research(session_id, focus, budget)` reloads the stored result, resumes its session as a new round, searches the focus as typed and then the model's plan for it (one model call), queues any steps a limit left unrun, and runs the SD01 loop again. With no focus, it refuses unless there are unrun steps or open questions.
  - The whole `ResearchResult` is stored as JSON, including the passage text of every source, so stored research can be shown and continued even if a text leaves the library (the same reasoning as `SavedItem`'s snapshot). A few columns beside the JSON serve the session list.
  - Research is stored automatically when it finishes; a failure to store becomes a warning, not an error. A run interrupted mid-way is not stored.
  - Each round has its own budget, and may add up to 10 sources beyond those already gathered. The analysis is rewritten over all sources, with the reader's focuses added to the research question. Warnings are cleared when a round starts, because they describe the result that round replaces.
  - "Incomplete" (`ResearchResult.is_incomplete`) means no analysis was written, or a limit stopped the research while planned steps remained.
  - Listing, showing and continuing sessions go through the agent facade; `ResearchController` is still played by the CLI commands.
- **Human contribution:** Asked for the next slice; chose to search the focus first. Reviewed the code.
- **Outcome:** Six code commits and this documentation commit.

### 2026-11-22 — AI-annotated reading, first slice (F06)

- **Task:** Implement F06 (UC06, SD04): annotate a passage of a text with AI commentary kept apart from the author's words, store it with the passage, and show it when the text is read again.
- **Input/Instruction:** "let's do the next slice of praxis".
- **AI contribution:** F03 was finished, so took F06 as the next full-depth feature. Gave `Annotation` its document, locator, sources, uncertainties, reader-profile flag and creation time. Added `AnnotationType.parse`, `label` and `searches_library`, and `Document.paragraph(n)`. Added `PromptBuilder.build_annotation_prompt` with a task per annotation type, `parse_annotation`, the `praxis/reading` package with `AnnotationService` (`generate_annotation`, `get_annotations`, `annotations_for`, `find_annotation`, `remove_annotation`), and `SQLAnnotationRepository` (an `annotations` table). In the CLI: `praxis annotate`, `praxis annotations list|remove`, and ✎ markers plus `--annotations` in `library read`. 417 automated tests. Three live runs against `gpt-5-mini` on a scratch database, all on ¶259 of *Revolution and Counter-Revolution* (the king's answer to the Frankfurt deputation): historical context (18 s, 3,379 tokens), fact check (34 s, 4,425 tokens), and historical context again after the fixes below (20 s, 3,810 tokens). Each search found the same three passages of the same book (¶272, ¶254, ¶187). Claims checked against the text: the fact check's "28 March … 290 votes against 248 who abstained" is in ¶254. The rerun's Dresden rising of 4 May, the Landwehr refusals and the recalled deputies are in ¶272 [1], and the Assembly's appeal to "the bayonets of the troops" is in ¶187 [3]. The fact check separated the authors' interpretive remark from the factual claims, and listed the 3 April date and the king's wording as not verifiable from the passages given.
- **Problems met:**
  - `annotate` parsed `--type` before opening the session, so an unknown type raised a `ValueError` traceback instead of printing an error. A CLI test caught it before commit.
  - The first live historical-context annotation cited paragraphs as "(see ¶254)" and "(see ¶3)" instead of `[n]`. ¶254 was one of its sources, but ¶3 (the heading "Germany in 1848") was never given to the model, and no check noticed. Fixed in its own commit (`65a8da8`): the prompt allows ¶ references only to the paragraphs shown, and the annotation warns about any other ¶ it names. The rerun cited only `[1]`–`[3]`; one run is not proof the prompt change holds.
  - In the fact check, a "- " list was shown run together as one paragraph, because the CLI wrapped whole paragraphs. Fixed in its own commit (`1c078ff`).
  - The rerun says the authors wrote the text "in August 1852" without marking it as general background; the articles appeared in 1851–52. As in F03, the citation checks cannot catch a wrong detail in an uncited sentence.
  - Two AI-written tests had vacuous assertions (`… or True`; asserting a constant). Another passed trivially, because the three-paragraph test text put every source inside the surrounding window. All three were rewritten before commit.
- **Design changes from Stage 1 introduced here:**
  - `AnnotationService.generateAnnotation(passage, type, profile)` is `generate_annotation(document, passage, type, profile)`. The document supplies the surrounding paragraphs and the title, author and date that F06's input lists. The controller resolves a paragraph number to a `Passage` with `Document.paragraph(n)`.
  - SD04's "additional context required" is decided by the annotation type. Historical context, fact check and connection search the library (`passage_search`, with the paragraph's own text as the query) for up to three passages outside the surrounding window. Terminology, argument and framing use the text alone. There is no web search, so a fact check is against the library and general knowledge only, and says so.
  - UC06's ambiguity flow is a fixed rule: a paragraph under 40 words gets two paragraphs on each side instead of one.
  - The model marks what it cannot verify with `uncertain:` lines, which become `Annotation.uncertainties`. SD04's "insufficient evidence" branch is a reply with only such lines. It returns an `AnnotationResult` with no annotation and the limitations, and nothing is stored.
  - Unlike `ask`, `annotate` without an API key, or when the model fails, is an error: an annotation has nothing to show without the model's commentary. Stored annotations can still be read without a key.
  - Annotations are stored by passage id. Passage ids derive from the document id and paragraph number, so an annotation finds its paragraph again. Sources are stored with their quoted text, as `SavedItem` and research results are. A failure to store becomes a warning. Annotations can be removed, which Stage 1 does not have.
  - `ReadingController` is played by the CLI commands, and `ReaderView` by `library read` (markers by default, full annotations with `--annotations`). SD04 shows reading progress being recorded on opening; that already happens in `library read` (F13), and `annotate` does not record progress.
  - Not built yet: UC06 step 9's links to recommended material (only links to the cited passages), saving an annotation to the workspace, and the GUI.
- **Human contribution:** Asked for the next slice. Reviewed the code.
- **Outcome:** Seven code commits and this documentation commit.

### 2026-11-22 — Source and framing comparison, first slice (F10)

- **Task:** Implement F10 (UC10, SD06): compare how two or more chosen sources treat a subject, keeping factual disagreements apart from differences in framing, and showing the underlying passages.
- **Input/Instruction:** "do the next 5 slices of praxis".
- **AI contribution:** Planned the five slices: F10 in two slices, F01 in two, then F02. F03 and F04 are finished and F06 is mostly done, so F10 and F01 are the full-depth features left with no code. Added a `document_id` filter to `search_passages`, `SourceRetrievalTool` (`source_retrieval`, registered through `ToolFactory`), the `praxis/comparison` package (`SourceSelection`, `SourceProfile`, `Comparability`, `ComparisonPoint` with `PointKind`, `SourceComparison`, `parse_comparison`, `check_points`, `CompareSourcesCommand`), `PromptBuilder.build_comparison_prompt` with `COMPARISON_RULES`, `PoliticalResearchAgent.compare_sources`, and `praxis compare`. 467 automated tests. Live runs against `gpt-5-mini` on a scratch database, all comparing *The Eighteenth Brumaire* with *Revolution and Counter-Revolution* on "the peasantry". The first left the *Brumaire* out (see below) and made no model call. The second (45 s, 7,203 tokens) judged the sources comparable and gave 3 points of shared ground, 1 difference, 2 "factual disagreements" and 2 observations; 3 further points were dropped for not citing passages from both sources. Phrases the comparison quoted were checked against the cited paragraphs and are there: "bag with potatoes" and "do not constitute a class" (¶228 of the *Brumaire*), "enslavement and pauperism" (¶235), "great class" (¶66 of *Revolution and Counter-Revolution*) and "real gainers" (¶132). The third run, after the prompt fix below (34 s, 6,295 tokens), noted in its comparability line that the books treat different countries, and listed 4 differences, 2 points of shared ground, 3 observations and no factual disagreements.
- **Problems met:**
  - The first live run left out *The Eighteenth Brumaire*. Daniel De Leon's translation calls the peasants "allotment farmers" and uses "peasant" three times. Porter stemming does not reduce "peasantry" and "peasant" to the same word, so the search found nothing. The warning shown was accurate. Fixed in its own commit: as in F04, the model suggests search keywords, and each source is searched for the subject and those keywords. A regression test was confirmed to fail before the fix.
  - In the second run, both "factual disagreements" were not about facts. One set the French peasants' condition against the Austrian peasants' gains, and the other was the interpretive question of whether the peasants "constitute a class". The rule now says that claims about different countries, periods or groups do not disagree. The rerun listed none. One run is not proof the rule holds.
  - One AI-written test assumed that searching the Manifesto for "the state" would return both of its paragraphs; only one mentions the state. It now names the paragraphs. The CLI tests first used *State and Revolution*, which is not in the bundled library.
  - `CompareSourcesCommand` was first written with a placeholder helper that ran a library search and threw the result away. It was replaced before commit: `SourceSelection` now carries the title for messages.
- **Design changes from Stage 1 introduced here:**
  - SD06's `compareSources(sourceIds)` is `compare_sources(selections, subject)`. A selection is a document and optionally its paragraphs (`3f2a91c0:12-14`). The library holds whole books, so a subject is needed to choose passages unless every source names its paragraphs. Two to four sources.
  - `CompareSourcesCommand` is a `ResearchCommand`. It runs one `source_retrieval` tool call per source (SD06's retrieval loop) against a `ResearchContext`, so it can later run inside research. A source with nothing on the subject is left out with a warning (UC10 precondition). With fewer than two sources left, the model is not asked.
  - `SourceProfile` is built only from the document's metadata (author, kind, outlet for news, date, URL, licence). There is no `WebProvider`, so SD06's optional profile search is not built. The prompt forbids stating or guessing ownership or funding the profile does not give (UC10: "no unsupported inference is made").
  - `SourceComparison.compare()` is not a method; the comparison is one model call in a fixed line format (`comparability:`, `similarity:`, `difference: <aspect> |`, `disagreement:`, `observation:`, `uncertain:`), parsed by `parse_comparison`. SD06's "low comparability" branch is `comparability: not comparable`. It becomes the first warning, and the passages are still shown.
  - Points are checked against the passages (`check_points`). A similarity, difference or disagreement must cite passages from at least two sources; an observation must cite at least one. Points that fail are dropped and counted in a warning. Disagreements (facts) and observations (interpretation of a source's standpoint) are shown under their own headings (UC10: "the disagreement is distinguished from differences in framing"; F10: bias judgements "identified as analysis").
  - `ResearchView`/`ResearchController` are played by `praxis compare`. Comparisons are not stored yet, and cannot yet be started from a research session or an event.
- **Human contribution:** Asked for the next five slices. Reviewed the code.
- **Outcome:** Seven code commits and this documentation commit.

### 2026-11-22 — Source and framing comparison, second slice: stored comparisons and comparison from research (F10)

- **Task:** Keep comparisons so they can be reopened, save them to the workspace, and start a comparison from a research session (F10: "requests a comparison from an event or research view").
- **Input/Instruction:** Second of the five slices requested.
- **AI contribution:** Moved the JSON encoding of numbered sources into `praxis/persistence/sources.py`, shared by research and comparison storage. Added `ComparisonRepository` with `SQLComparisonRepository` (a `comparisons` table), and in the agent `compare_research_sources`, `get_comparison`, `find_comparison` and `list_comparisons`. Added `WorkspaceService.save_comparison` with a `comparison` item kind, and the commands `compare --save`, `comparisons list|show` and `sessions compare`; `workspace open` links a saved comparison back to it. The keyword model call is now skipped when every source names its paragraphs. 484 automated tests. Live run against `gpt-5-mini` on the scratch database: `research "How did the bourgeoisie behave in the revolutions of 1848?"` (141 s, 34,275 tokens, 20 sources: 16 from *The Eighteenth Brumaire*, 3 from *Revolution and Counter-Revolution*, 1 from the Manifesto), then `sessions compare` on it with `--save` (30 s, 6,992 tokens). The comparison judged the three texts comparable while noting they treat different countries and levels. It gave 3 points of shared ground, 4 differences, 3 observations and no factual disagreements, and was stored and saved. Terms it attributed to the passages were checked and are there: "aristocracy of finance", "fractions" and "small traders" (¶53 of the *Brumaire*), "petty traders" (¶321 of *Revolution and Counter-Revolution*) and "world-market" (¶21 of the Manifesto).
- **Problems met:**
  - The live run compared only 6 of the 16 *Brumaire* passages without saying so: `CompareSourcesCommand` cut named paragraphs at 6 silently. Fixed in its own commit (`c43fe96`): the reader is now told how many were named and which were compared. Regression test confirmed to fail before the fix.
  - The live comparison's differences contained empty "()": the model wrote citations inside brackets ("([10])"), and stripping the citation marks left the brackets. Fixed in its own commit (`dc3850a`), with a regression test confirmed to fail before the fix.
  - A first check that the paragraph-cap test fails without the fix was invalid: `git stash` also removed the new test. It was redone stashing only the source file.
- **Design changes from Stage 1 introduced here:**
  - Comparisons are stored whole as JSON with the passage text, like research results, and only when two or more sources had passages. A failure to store becomes a warning.
  - Comparing from a research view is `compare_research_sources(session_id)`: the research question is the subject, and the research's own passages are compared (up to four texts, those that supplied most passages, at most six passages each). It needs a research session that drew on two texts or more. Comparing from an event waits for F01/F02.
- **Human contribution:** Reviewed the code.
- **Outcome:** Six code commits and this documentation commit.

### 2026-11-22 — News dashboard, first slice: fetching and keeping news (F01)

- **Task:** The retrieval half of F01 (UC01 steps 1 and the "source unavailable" flows, SD03's `NewsService` → `NewsProvider.getRecentNews()`): fetch current news from several configured sources, keep it, and list it.
- **Input/Instruction:** Third of the five slices requested.
- **AI contribution:** Checked which public RSS feeds were reachable, and chose six for a spread of outlets: BBC News, Al Jazeera, The Guardian, Deutsche Welle, CBC News and Peoples Dispatch (`data/news/feeds.json`). Added the `praxis/news` package: `NewsProvider`, `RSSNewsAdapter` (RSS 2.0, RSS 1.0/RDF and Atom, parsed with the standard library), `parse_feed`, `read_feeds`, and `NewsService` with `refresh()` and `get_recent_news(days)`. `DocumentRepository` gained `list_kind` and `count(kind)`. `LibraryService` now leaves news out of `browse`, `search`, `topics` and `is_empty`. Commands: `praxis news refresh|list|feeds`. 507 automated tests, none of which touch the network. Live run on the scratch database: `news refresh` fetched 145 articles from all six feeds in under 2 s (33, 25, 45, 10, 20 and 12), and `news list --days 1` showed 74 from 22 November.
- **Problems met:**
  - Making `is_empty` ignore news first loaded every document, which an existing test forbids. It now compares two counts.
  - Feeds give a date and time, but `Document.publication_date` is a date, so headlines from the same day are listed alphabetically, not by time. Not changed.
  - Al Jazeera's items carry the category "Show Types", which is kept as a topic. Not changed.
- **Design changes from Stage 1 introduced here:**
  - `NewsProvider.getRecentNews()` is `get_recent_news()` on each provider, and `RSSNewsAdapter` adapts one feed. Each feed is a provider, so one unavailable feed is reported and the rest are still used (UC01).
  - SD03 fetches news inside `getDashboardEvents()`. Here fetching is `NewsService.refresh()`, and the stored articles are what is shown. The dashboard can therefore fall back to earlier news when no source is reachable (SD03's "cached/partial events").
  - Articles are stored as `NewsArticle` documents in the document table, keyed by their link. Questions, research and comparisons can therefore draw on news through the same passage search, which UC03's News Provider actor needs. Only the feed's syndicated summary (at most 1,500 characters) is kept, and the licence marks it as not reproducible, so quotations stay within the excerpt limit.
  - `NewsController`/`NewsView` are played by the `news` commands. No clustering, summaries or event cards yet; those are the next slice.
- **Human contribution:** Reviewed the code.
- **Outcome:** Three code commits and this documentation commit.

### 2026-11-22 — News dashboard, second slice: events, summaries and the dashboard (F01)

- **Task:** The rest of SD03's dashboard flow: `cluster(articles)`, `summarize(event)` with its fallback, and event cards (UC01 steps 2–5).
- **Input/Instruction:** Fourth of the five slices requested.
- **AI contribution:** Added `Event` with `Grouping` (single report, grouped, grouping uncertain) and `SummaryStatus` (summarised, headlines only), `EventClusterer` (TF-IDF cosine similarity of headline and opening words, single-link, at most two days apart; no model call), `PromptBuilder.build_event_summary_prompt` with `EVENT_SUMMARY_RULES`, `NewsSummaryService` and `read_summary`, `SQLEventRepository` (a `news_events` table), `NewsService.get_dashboard_events`, `get_event` and `find_event`, and `praxis news dashboard`. The clustering thresholds were chosen by running the clusterer on the 104 stored reports from 21–22 November and reading the groups. 538 automated tests. Live run against the real feeds and `gpt-5-mini` (2 min 4 s, 8 model calls, 16,119 tokens): 77 events from 104 reports. The 8 shown were each reported by 2–4 outlets: the COP31 collapse, the Indonesian factory fire, the arrest of "El Chapo Isidro", the drone strike on a Russian ship in Benghazi, settler attacks in the West Bank, reactions to Trump calling Putin a friend, a swim across the Strait of Hormuz, and the Democrats' House majority. Four were marked "grouping uncertain". For the West Bank event, the model also said the reports were only partly about one incident. Details in the summaries were checked against the stored feed text, and each is in a report the summary cites for it: "36" unaccounted for (CBC, Guardian), "Merkury", "Guasave", "Jay Clayton", "9.3" miles, "Chuck Hubbard" and "44" seats (Guardian), "longest" summit (BBC, Al Jazeera, CBC). The fire summary reported the different accounts of how many were missing side by side and cited each. Rerun with `--offline`: 0.3 s, no model call, every card reused.
- **Problems met:**
  - With only two reports, words both shared got an inverse document frequency of log(3/3) = 0, so two reports of the same event could never be grouped. A unit test caught this before commit; the weight is now log(…) + 1. The thresholds were re-chosen on the live data after the change.
  - The live dashboard printed report lines without their indent (`textwrap.shorten` collapses whitespace, including leading spaces), and one note ended "..". Both were fixed in their own commit (`db397ca`), with regression tests confirmed to fail before the fix.
  - One AI-written test expected a stored summary after a run that only refreshed the feeds and built no dashboard. The test was wrong and was corrected.
  - One summary cited "[2,3; 1,4]". The citation pattern does not read that form, so those numbers were not checked; the same summary's other citations were. Not changed.
  - Summaries are generated one after another, so a cold dashboard of 8 events takes about two minutes. Not changed; stored cards make reruns immediate.
- **Design changes from Stage 1 introduced here:**
  - `EventClusterer.cluster()` is deterministic (no model), so grouping is cheap, repeatable and testable. How confident a grouping is comes from the weakest similarity that joined a report. The model's "same event: no|partly" can mark a group uncertain, but never splits it.
  - `NewsSummaryService.summarize()` is one model call per event of two or more reports. A single report is not summarised: the card shows the outlet's own summary, labelled as such, and says no other outlet in the feeds reported it (F01: "Events with insufficient information … should not be presented as confidently established"). SD03's "summary fails" branch also covers a summary that cites no report or a report that does not exist: the card then shows headlines only.
  - Events are stored, keyed by the set of their reports, so an unchanged event reuses its summary and can be opened by id (F02). Only the `--limit` most widely reported events (default 8) are summarised, which bounds model calls.
  - `NewsView`/`NewsController` are played by `news dashboard`. Opening an event (F02) is the next slice.
- **Human contribution:** Reviewed the code.
- **Outcome:** Five code commits and this documentation commit.

### 2026-11-22 — Expandable event exploration (F02)

- **Task:** F02 (UC02, SD03's `openEvent`/`getEvent` and `researchEvent`): open a dashboard event in a detailed view with its sources, context and links to further research. Also F10's "comparison from an event view" and saving events (F15).
- **Input/Instruction:** Fifth of the five slices requested.
- **AI contribution:** Added `EventExplorer` and `ExpandedEvent` (`praxis/news/exploration.py`), `related_reports` in the clusterer, `PromptBuilder.build_event_exploration_prompt` with `EVENT_EXPLORATION_RULES`, and `NewsService.get_expanded_event`. In the agent: `research_event` (a research session whose first sources are the event's reports; `research` gained a `reports` argument and an "event" source purpose) and `compare_event_reports`. Also `WorkspaceService.save_event`, and the `praxis news event <id> [--research|--compare] [--save]` command. 566 automated tests. Live runs against `gpt-5-mini` on the scratch database:
  - The Benghazi ship event (48 s, 6,059 tokens): 4 reports, 3 library passages, 4 other possibly related reports, and an account in all four sections. Checked against the text: the Guardian report contains "Associated Press", "sea drones", "western Libya" and the counts of four drones intercepted and two hits. The quoted "terrible reality of the Russian Empire" is in ¶171 of *Revolution and Counter-Revolution*, and "deluge the whole continent" in ¶182. The library background is a stretch: Engels on 19th-century Russian expansion, applied to the ship. The model presented it as interpretation, as the prompt requires.
  - `--compare --save` on the Indonesian factory fire (20 s, 3,346 tokens): four outlets compared, with 3 points of shared ground, 4 differences and 3 observations, stored and saved. Its attributions were checked: "36" missing and "Banten" (CBC), "devastating" and "much larger tragedy" (DW), "feared dead" (BBC), and the drone footage and AFP credit (the Guardian item's author is Agence France-Presse).
  - `--research` on the same event (1 min 59 s, 32,347 tokens): it started from the 4 reports, added 14 library and news sources, ran 2 assessments, and stopped at the step limit. The analysis cites the reports together with *The Condition of the Working-Class in England*.
- **Problems met:**
  - Related reports were first looked up through the passage index. It skips text under 8 words and does not index headlines, so a test's related report was never found. They now use the clusterer's headline similarity, with a lower threshold (0.15) than grouping.
  - In the first live expanded view, the account's "- " items ran together. `_print_ai_text`, which `ask` and `research` also use, wrapped whole paragraphs. A "Sources" heading also appeared under the library heading. Fixed in their own commit (`cde192d`), with a regression test confirmed to fail before the fix. The "related reports" in that run included loosely similar items (Finnish airspace, drone strikes in Sudan), so the heading now says they *may* be related.
  - Guardian feed summaries end with a "Continue reading..." paragraph, which was compared as text. It is now dropped (`0899b53`). Removing citations from comparison points could leave "searches , details"; fixed (`de80e3c`). Both have regression tests confirmed to fail before the fix.
  - The event research's planner wrote very long keyword lists. Its follow-up searches were in Indonesian with quotation marks, which the library cannot match, so several steps found nothing. This is F03 planner behaviour brought out by the event's question. Not changed.
  - Now that news is in the passage index, research can pull in unrelated news: one source in the event research was a measles report. It was not cited. Not changed.
- **Design changes from Stage 1 introduced here:**
  - SD03's expanded view (`openEvent` → `getEvent` → display) gains `NewsService.get_expanded_event`. It adds related reports (UC02 step 2, "additional reporting": here from stored news, not a new fetch), library background (step 5), and one model call for the account (steps 3 and 5, and the disagreement flow). The account is checked like the other AI text: citations of missing sources are warned about, and an account citing no report is flagged as unsupported.
  - Whether an event is still developing is decided from dates (latest report today or yesterday), not by the model.
  - SD03's `research(event)` is `research_event(event)`: the research question is built from the headline, and the event's reports are the first sources, so the research is about the event actually reported rather than whatever a search finds.
  - `--research` and `--compare` replace the expanded view rather than following it, so one command makes at most one kind of model work.
- **Human contribution:** Reviewed the code.
- **Outcome:** Seven code commits and this documentation commit.

### 2026-11-22 — Intelligent reading recommendations (F07)

- **Task:** Implement F07 (UC07, SD05's `recommendReadings`): recommend library texts for a topic or for the reader's interests, ranked, each with why.
- **Input/Instruction:** "do the next 5 slices of praxis".
- **AI contribution:** Planned the five slices from the features with no code yet: F07, F08 in two slices (building a learning path, then keeping it with progress), F09, then F11. Added `RECOMMENDATION_RULES` and `PromptBuilder.build_recommendation_prompt`, and the module `praxis/reading/recommendations.py`: `Recommendation`, `ExternalSuggestion`, `ReadingStatus`, `RecommendationResult`, `parse_recommendations` and `RecommendationService` (`recommend_readings(topic, profile)`, `recommend_next(profile)`). In the CLI: `praxis recommend [TOPIC]`. 600 automated tests. Two live runs against `gpt-5-mini` on a scratch database whose reader had read 37% of *Revolution and Counter-Revolution*:
  - `recommend "the state"` (37 s, 4,413 tokens): the *Brumaire*, *Revolution and Counter-Revolution* and the Manifesto, with two works outside the library (*On the Jewish Question*, *The State and Revolution*). Phrases its reasons quoted were checked and are in the cited paragraphs: "by far the most important" (¶102 of *Revolution and Counter-Revolution*), "in the hands of the State" (¶139 of the Manifesto), "framing of a republican constitution" and "state of siege" (¶55 of the *Brumaire*), and the State's "supervision" of education (¶59).
  - `recommend` with no topic (40 s, 3,509 tokens) used the three strongest interests (1848, bourgeoisie, germany) and ranked the partly read *Revolution and Counter-Revolution* first. Its paragraph references were checked: "German workers" and "recognition" (¶216 of the Manifesto), 1848 (¶19) and Bismarck (¶22) in *The Condition of the Working-Class*, and Vienna (¶193 of *Revolution and Counter-Revolution*).
- **Problems met:**
  - Without a model, `recommend imperialism` ranked *Revolution and Counter-Revolution* above Lenin's letter: the index stems "imperialism" so that it matches "Imperial" (the Imperial Diet and army). Texts the catalogue tags with the topic now come first. Fixed in its own commit (`8862a95`), with a regression test confirmed to fail before the fix.
  - In the first live run every reason repeated "you have not opened it", which the command already prints. The prompt now says not to restate progress (own commit). In the second run one reason still mentioned the 37% as the reason to continue, which is a fair use.
  - A word match is not always about the topic: "the state" matched the *Brumaire*'s "state of siege". The model's reason quoted it as if it were about the State. Not changed; the same keyword search serves F04 and F03.
- **Design changes from Stage 1 introduced here:**
  - SD05's `LibraryService.search(topic)` is the `passage_search` tool: texts are found by their passages, which also gives the reader paragraphs to start from. `RecommendationService` takes the `ToolManager`, not `LibraryService`. News articles are not recommended.
  - SD05's "evaluate relevance/difficulty" is one model call. The model replies in a fixed line format (`recommend: [n] | <difficulty> | <why>`, `external: <title> | <author> | <why>`); up to 8 candidates are shown and up to 5 recommended. Numbers the model invents are ignored with a warning. Without a model, or if it fails or replies in another form, texts are ranked by matching passages and the reader is told.
  - UC07 step 4 ("previously completed … readings are deprioritized") is done in code after the model's ranking: finished texts go last. The reader's progress in each text comes from the reading history.
  - UC07's "external source recommendations" are the model's `external:` lines, shown under their own heading as not checked. There is no web search to verify them.
  - F07's "should not imply that a recommendation is personalized when insufficient user information exists": the reader profile is sent only when `reader_context` allows it, and a sparse profile or personalization turned off produces a warning that the ranking rests on the topic alone. `recommend_next` (no topic) needs personalization on and at least one interest.
  - `ReadingController`/`ReaderView` are played by `praxis recommend`. Saving or opening a recommended text uses the existing `workspace save-text` and `library read` commands, which the output names. Recommendations are not stored.
- **Human contribution:** Asked for the next five slices. Reviewed the code.
- **Outcome:** Five code commits and this documentation commit.

### 2026-11-22 — Prerequisite-guided learning, first slice: building a learning path (F08)

- **Task:** F08 (UC08, SD05's `buildLearningPath`): identify what a topic or text assumes, leave out what the reader knows, and give an ordered path with readings.
- **Input/Instruction:** Second of the five slices requested.
- **AI contribution:** Added `PREREQUISITE_RULES` and `PromptBuilder.build_prerequisite_prompt`, and `praxis/reading/prerequisites.py`: `Prerequisite`, `LearningStep`, `StepStatus`, `LearningPath`, `parse_prerequisites` and `PrerequisiteService` (`identify_prerequisites`, `build_learning_path`). In the CLI: `praxis path build [TOPIC] [--text ID]`. 626 automated tests. Two live runs against `gpt-5-mini` on the scratch database, both for *The Eighteenth Brumaire* (`--text`):
  - Before the fixes below (39 s, 3,800 tokens): five steps, all marked "needed". The first three were the text's own catalogue topics (historical materialism, class struggle, the state), and two event steps offered the same paragraph.
  - After them, with "class struggle" recorded as known (26 s, 3,082 tokens): five steps on the background the pamphlet assumes: the 1799 coup, the February Revolution and Second Republic, the French factions of 1848–52, Louis Bonaparte's presidency and the 1851 coup, and Bonapartism. "On the 24th of February, 1848, Louis Philippe was driven out of Paris" (¶127 of *Revolution and Counter-Revolution*) was offered for the February Revolution, which fits. The library has nothing on the 1851 coup, so that step showed the model's orientation and was reported as a gap. The orientation's dates (elected 1848, coup on 2 December 1851) are correct general history.
- **Problems met:**
  - Steps were marked "needed" for a reader with no recorded knowledge: the check used `ReaderProfile.is_sparse`, which also counts interests and reading progress. Steps are now required only when knowledge areas exist. Fixed in its own commit (`1c3fd6a`), with a regression test confirmed to fail before the fix.
  - Given the target text's catalogue topics, the model listed what the text teaches as what it assumes. The text is now named by title, year and author only (`95190e4`). Regression test confirmed to fail before the fix.
  - The same paragraph was offered for two steps; a passage is now offered by one step only (`bbaff34`). Regression test confirmed to fail before the fix.
  - Readings are found by keyword search, and the library holds five books, so several are weak: ¶9 of *Revolution and Counter-Revolution* (a preface naming the *Brumaire*) for the 1799 coup, ¶93 (German parties) for the French factions, and two unrelated paragraphs for Bonapartism. Not changed. The path shows the excerpt beside each reading, so the reader can judge it.
  - Two AI-written CLI tests assumed "negation" and "Hegelian dialectic" appear in no bundled text; "Hegelian" and "dialectic" do. The test uses the Physiocrats, which no bundled text mentions.
- **Design changes from Stage 1 introduced here:**
  - `PrerequisiteService.identifyPrerequisites(topic)` is one model call in a fixed block format (`prerequisite: <name> | <kind> | <essential|helpful>`, then `search:`, `why:`, `orientation:` lines). The reader's known topics are sent with it, so the model reuses their names, and the service filters on those names. Without a model, or on a reply in another form, no path is built (an error, as for annotations).
  - UC08's filtering: knowledge the reader stated at introductory level or above removes a step, and is listed as left out. Knowledge only inferred from reading keeps the step, as a suggestion with a note (UC08: "If the system lacks confidence in a knowledge assessment, it presents the prerequisite as a suggestion rather than a requirement"). With no recorded knowledge, or personalization off, every step is a suggestion and the reader is told.
  - SD05's `search(prerequisite topics)` is a `passage_search` per step, for the name and the model's keywords. Up to two passages, from different texts first, never from the target text, the news, or an earlier step.
  - SD05's "user already knows prerequisites" branch is `LearningPath.no_path_required`: the command says no path is needed and points to the target text, or to `recommend` for a topic.
  - `LearningPath` has an id, a creation time and a status per step, ready to be stored; storing paths and recording progress (UC08 steps 7–8) is the next slice. Until then the command points to `profile know` for steps the reader already understands.
- **Human contribution:** Reviewed the code.
- **Outcome:** Five code commits and this documentation commit.

### 2026-11-22 — Prerequisite-guided learning, second slice: stored paths and progress (F08)

- **Task:** UC08 steps 7–8 and its postcondition ("progress can be retained"): keep learning paths, let the reader mark steps done, already known or skipped, and update the reader model.
- **Input/Instruction:** Third of the five slices requested.
- **AI contribution:** Moved the JSON encoding of citations into `praxis/persistence/citations.py`, shared by annotation, source and path storage. Added a `learning_paths` table, `LearningPathRepository` with `SQLLearningPathRepository` and `LearningPathSummary`, `LearningPath.settled_count` and `next_step`, and in `PrerequisiteService` `get_path`, `list_paths`, `find_path` and `set_step_status`. In the CLI: `path list`, `path show` and `path mark <id> <step> done|known|skip|todo`. `path build` now prints the path's id and next step. 648 automated tests. Live runs against `gpt-5-mini` on the scratch database:
  - `path build "surplus value"` (35 s, 2,678 tokens): commodity, the labour theory of value, labour-power and wages, capital, and circulation, in that order. Marking step 1 known and step 3 done added "commodity" and "labour-power and wages" to the reader model as stated knowledge at introductory level. Skipping step 5 left the model alone. `path list` showed 3/5 steps, and `path show` marked each settled step.
  - `path build "the falling rate of profit"` (33 s, 2,598 tokens): six steps. None matched a topic the reader had marked, so nothing was left out.
- **Problems met:**
  - The two live paths named the same step "Labour theory of value" and "The labour theory of value"; matching on the exact name would not have recognised it as known. Known topics are now matched without a leading article (`89e4565`). Regression test confirmed to fail before the fix.
  - Most readings for the economic steps are weak, because the library has no economic text such as *Capital*: ¶274 of *Revolution and Counter-Revolution* (on insurrection) was offered for the labour theory of value, and ¶144 of the Manifesto (free education) for circulation. ¶84 of the Manifesto (the minimum wage) and ¶80 ("To be a capitalist…") fit. Not changed; importing more texts is the remedy.
- **Design changes from Stage 1 introduced here:**
  - Stage 1 gives `LearningPath` no storage. Paths are stored whole as JSON, with the text of each reading, as research and comparisons are. A path with no steps (nothing to learn) is not stored. A failure to store becomes a warning, and the command then falls back to the `profile know` hint.
  - UC08 step 7 ("marks or demonstrates completion") is marking only: done, already known, skipped, or back to do. There is no test of understanding.
  - UC08 step 8 goes through the Observer pair as SD07 shows: the `path mark` controller publishes `PrerequisiteMarkedKnown` for done and known steps, and `ReaderModelUpdater` records the topic as stated knowledge at introductory level (never lowering a higher level). `PrerequisiteService` does not touch the reader model itself. Skipping publishes nothing, since skipping is not knowing.
  - When every step is dealt with, the command points on to the target text, or to `recommend` for a topic.
- **Human contribution:** Reviewed the code.
- **Outcome:** Four code commits and this documentation commit.

### 2026-11-22 — Historical context exploration (F09)

- **Task:** Implement F09 (UC09): a source-grounded account of how a situation developed (origins, stages, turning points, continuities), keeping chronology apart from disputed interpretation, naming gaps, and suggesting texts to read further. Also its "contextual links" from a news event.
- **Input/Instruction:** Fourth of the five slices requested.
- **AI contribution:** Added `HISTORY_PLAN_RULES`, `HISTORY_RULES` and their prompt builders, and `praxis/research/history.py`: `HistoryItemKind`, `HistoryItem`, `ContextStatus`, `HistoricalContext`, `SuggestedReading`, `parse_history_plan`, `parse_history`, `check_items` and `suggested_readings`. In the agent: `explore_history(topic, allow_broad, reports)` and `explore_event_history(event)`. `ResearchContext` gained `library_only`. In the CLI: `praxis history TOPIC [--broad]` and `news event ID --history`. 677 automated tests. Live runs against `gpt-5-mini` on scratch databases:
  - `history "the defeat of the 1848 revolution in Vienna"` before the prompt fixes below (69 s, 9,799 tokens), then after them (77 s, 11,716 tokens). The second run's chronology ran from 13 March to the storming of Vienna in one ordered sequence. Its dated claims were checked: the 14th of May, the 15th and the 26th of May and the Academic Legion (¶195 of *Revolution and Counter-Revolution*); the 19th of August review and the massacre of "unarmed and unresisting workpeople" on the 23rd (¶197); "legal and constitutional" and "British free-traders" (¶211). It wrote "15–16 May" where ¶195 gives only the 15th. The first run's "Wrangel's approach to Berlin" is not in the cited ¶228, which does not name Wrangel: correct history from the model's memory, attached to a passage that does not state it.
  - `news event 56eefcd0 --history` on the COP31 climate summit (82 s, 7,448 tokens; after the news fix below, 61 s, 5,839 tokens). The library has nothing on climate diplomacy. The chronology came from the reports, the origins from Engels on coal and steam-power (¶29 of *The Condition of the Working-Class*), and the gaps said that the passages do not link 19th-century industry to the summit.
- **Problems met:**
  - In the first Vienna run, every stage was listed before every turning point, so the chronology was out of order, and several events appeared twice, once as each kind. The rules now ask for one chronological sequence with each event once (`add8d3b`). The prompt test passes; the second live run was in order with no repeats.
  - The planner wrote long phrase lists as keywords, and the first two searches matched the *Brumaire* and the Manifesto rather than Vienna. Searches are now limited to a short label and six keywords (`21bf954`). In the rerun, 9 of 13 sources were from *Revolution and Counter-Revolution* (6 of 13 before).
  - The first event run pulled unrelated news (a ruling on Myanmar, Australian fuel imports) into the history and suggested a news live blog as further reading. History searches now leave news out (`ResearchContext.library_only`). Fixed in its own commit (`01649df`), with a regression test confirmed to fail before the fix.
  - An AI-written test expected two sources from a search whose words appear in only one test passage, and step lines said "+1 sources"; both corrected before commit.
- **Design changes from Stage 1 introduced here:**
  - Stage 1 realises F09 inside SD01 (the planner schedules `TraceHistoricalDevelopmentCommand`, and `HistoricalDevelopmentAnalyzer` reconstructs origins, stages and turning points). Here it is its own request on the agent facade, `explore_history`, which reuses `TraceHistoricalDevelopmentCommand` and `ResearchContext` but not the full research loop: one planning call, one search per planned period plus the topic as typed, then one organising call. There is no `HistoricalDevelopmentAnalyzer` class: the model's reply in a fixed line format (`origin:`, `stage: <when> |`, `turning point: <when> |`, `continuity:`, `interpretation:`, `gap:`) is parsed by `parse_history`. Stage 1's `traceOrigins()`, `identifyStages()` and `identifyTurningPoints()` correspond to the origin, stage and turning point kinds.
  - UC09's "distinguishes factual chronology from contested interpretation": stages and turning points must be facts the passages state; interpretations are a separate kind, shown under their own heading as interpretation, not established fact. "If evidence is incomplete, gaps are identified": `gap:` lines. "Ask the user to narrow the scope": the planning call can answer `scope: too broad` with narrower topics, and nothing is searched unless the reader passes `--broad`.
  - UC09 step 4 ("evidence supporting those developments is retained"): each item keeps the source numbers it cites; items citing no retrieved passage are dropped and counted in a warning, as in F03. If nothing cited remains, no account is shown, only the passages.
  - UC09 lists a Web Search Provider; there is none, so history comes from the library only. News reports appear only as an event's starting sources, and are not suggested as readings.
  - Historical context is not stored and cannot be saved to the workspace yet. Opening it from an annotation or a research result (F09's other "contextual links") is not built; annotations already have a historical-context type (F06).
- **Human contribution:** Reviewed the code.
- **Outcome:** Six code commits and this documentation commit. The previous entry's commit count is corrected here from five to four.

### 2026-11-22 — Marxist theoretical analysis (F11)

- **Task:** Implement F11 (UC11): analyse an issue with Marxist concepts, retrieving theoretical texts and connecting them to the evidence, with interpretations linked to their passages, tentative where the evidence is thin, other readings noted, and suggested theoretical readings. Also UC11's "reached as part of a broader research session".
- **Input/Instruction:** Fifth of the five slices requested.
- **AI contribution:** Added `CONCEPT_RULES`, `ANALYSIS_RULES` and their prompt builders, and `praxis/research/analysis.py`: `Concept`, `AnalysisItemKind`, `AnalysisItem`, `AnalysisStatus`, `MaterialistAnalysis`, `parse_concepts`, `parse_analysis` and `check_analysis`. In the agent: `analyze(issue, framework)` and `analyze_research(session_id, framework)`. In the CLI: `praxis analyze ISSUE [--framework ...]` and `praxis sessions analyze ID [--framework ...]`. 700 automated tests. Live runs against `gpt-5-mini` on the scratch database:
  - `analyze "the condition of English factory workers in the 1840s"` (69 s, 12,256 tokens): 6 evidence passages, all from *The Condition of the Working-Class*, and 7 theory passages; concepts class, labour, capital and the state. Checked against the text: the factory operatives as "the nucleus of the labour movement", with Manchester "the central point of Chartism" (¶377); the Factory Act (¶234); the New Poor Law declaring proletarians "superfluous" (¶428); child mortality among factory operatives (¶250); and "the concentration of capital and land in a few hands" (¶165 of the Manifesto). One application was labelled "reserve army of labour" and cited ¶62 of the Manifesto, which says that wage-labour "rests exclusively on competition between the laborers" but has no reserve army. The model gave a concept from *Capital* a passage that only partly supports it. Two applications were dropped for not citing both theory and evidence.
  - `sessions analyze 27004bab --framework "the state as an instrument of class rule"` on the stored two-round 1848 research session (69 s, 23,406 tokens): no evidence search; 8 theory passages added after the session's 30 sources. Its use of the *Brumaire* was checked: the executive power's "tremendous bureaucratic and military organization" (¶224), and the bureaucracy as "the instrument of the ruling class" (¶225). Four claims were marked supported and two tentative, and five alternative readings were given (the international defeats, the monarchs' command of the army, local class composition, tactical mistakes at Frankfurt).
- **Problems met:**
  - Citation marks at the end of a line left stray punctuation ("socialism),", "independence,,"); brackets that held only citations were printed as "(,)"; a removed mid-sentence citation left a double space. `strip_citations` (shared with F09) now removes these. Two fixes in their own commits (`a3f9ed2`, `4d9ec25`), each with a regression test confirmed to fail before the fix.
  - The model headed alternatives and limits "label | text", which the format gives only to the other kinds, so the bar was printed. Labels are now split for every kind (`7303355`). Regression test confirmed to fail before the fix. In the second run the model copied the template's "where concept does not fit" as the label of each limit; not changed.
- **Design changes from Stage 1 introduced here:**
  - Stage 1 realises F11 inside SD01, through `DialecticalMaterialistResearchMethod` and its analyzers, ending in `MaterialistAnalysis`, with theory from `TheorySearchTool`. Here `MaterialistAnalysis` is the result of its own agent request. `analyze` makes three model calls (search keywords, concepts, analysis); `analyze_research` makes two, reusing the session's sources as evidence and its established findings (`established_lines`) as context. Theory is retrieved with the existing `RetrieveTheoryCommand` (the `passage_search` tool), not a separate `TheorySearchTool`, and from the library only, not news.
  - UC11 step 2 ("identifies material conditions, class and production relations, institutions …") is the `condition:` kind with its aspect; step 4 ("connects the theoretical material to the evidence") is `application:`, which must cite at least one theory passage and one evidence passage or it is dropped (`check_analysis`); step 5 ("interpretive claims retain links") is the citation check on every item.
  - UC11's alternatives: "a tentative interpretation" is the claim label: a claim is "supported" only when the model says so, anything else counts as tentative, and an analysis with no supported claim carries a warning. "Multiple plausible interpretations … may be noted" is `alternative:`. "Does not force every issue into a predetermined category" is `limit:`, and the concept prompt names only concepts the evidence gives reason to apply.
  - With no evidence, nothing is analysed. With evidence but no theoretical passage for the chosen concepts, no analysis is written and the evidence is shown. Without a model, the evidence is returned. If the model names no usable concept, theory is searched for the framework, or the issue, as typed.
  - Analyses are not stored and cannot yet be saved to the workspace. Theoretical connections suggested within reading views (F06) are not built.
- **Human contribution:** Reviewed the code.
- **Outcome:** Six code commits and this documentation commit.

### 2026-11-22 — More library texts

- **Task:** Widen the reading library, after the F08 and F11 live runs showed weak readings for economic topics because no bundled text dealt with political economy.
- **Input/Instruction:** "import more texts".
- **AI contribution:** gutenberg.org returned 503 and the gutendex catalogue API timed out, so the mirror's `GUTINDEX.ALL` was searched for socialist authors. Project Gutenberg has no English *Capital*, *Imperialism, the Highest Stage of Capitalism*, *The State and Revolution* or *Value, Price and Profit*. Chose nine English texts it does have and bundled them in `data/library/` with catalogue entries (topics and dates): Marx, *A Contribution to the Critique of Political Economy* (46423); Engels, *Socialism: Utopian and Scientific* (39257), *The Origin of the Family, Private Property and the State* (33111), *Landmarks of Scientific Socialism* (Anti-Dühring, 31933) and *Feuerbach* (27814); Luxemburg, *The Accumulation of Capital* (41405); Trotsky, *Dictatorship vs. Democracy* (38982); Labriola, *Essays on the Materialistic Conception of History* (32644); and Kropotkin, *The Conquest of Bread* (23428), an anarchist text for contrast (F12). `library seed` now imports 14 texts, and the local database was seeded. Searches for "surplus value", "exchange value money circulation" and "imperialism capitalist accumulation" now return passages from Luxemburg and the *Critique*. 706 automated tests.
- **Problems met:**
  - Four of the new books open or close with transcribers' notes (formatting conventions, lists of corrected misprints), some boxed in `+---|` lines. These would have been indexed and could be cited as the author's words, as the volunteer credits once could. They are now dropped from the first and last five paragraphs (`78dffc8`, `53de0dc`), with regression tests confirmed to fail before each fix. Short decorative lines that remain (for example "* * * * *") are under the eight-word indexing threshold.
  - Three tests depended on the library's contents: the seed count, topic counts, and the Physiocrats being absent (the *Critique* discusses them). The learning-path tests now use phrenology, which no bundled text mentions.
  - The test suite takes about 28 s instead of 12 s, because many CLI tests seed the full library.
  - Luxemburg's *Accumulation of Capital* is the 1951 Schwarzschild translation; it is included because Project Gutenberg distributes it as public domain in the US, as with the other texts.
- **Human contribution:** Asked for more texts. Texts were chosen by the AI.
- **Outcome:** Three code commits and this documentation commit.

### 2026-11-22 — Comparison of leftist perspectives (F12)

- **Task:** Implement F12 (UC12, Stage 1's `IdeologicalContextService`): present the meaningful disagreements between Marxism and other leftist traditions on a topic, each from its own texts where the library has them, with readings, and without inventing disagreements.
- **Input/Instruction:** "do the next 5 slices of praxis".
- **AI contribution:** Planned five slices from what was still missing: F12, F14 (personalized assistance), and the GUI in three slices (the Stage 2 instructions require one, and none existed). Added `TRADITION_RULES`, `TRADITION_COMPARISON_RULES` and their prompt builders, and `praxis/reading/traditions.py`: `Tradition`, `Perspective`, `Statement` (position, conditions, assessment), `Disagreement`, `TraditionsStatus`, `TraditionsComparison`, `parse_traditions`, `parse_tradition_comparison`, `check_comparison`, `authored_by` and `IdeologicalContextService` (`compare_traditions`, `find_relevant_traditions`, `recommend_representative_texts`). In the CLI: `praxis traditions TOPIC` and `praxis sessions traditions ID`. 737 automated tests. Two live runs of `traditions "the abolition of the state after the revolution"` against `gpt-5-mini` on a scratch database:
  - Before the fixes below (77 s, 8,871 tokens): Marxism, Leninism (Lenin, Trotsky), Luxemburgism and Anarchism, 12 passages.
  - After them (68 s, 8,042 tokens): Marxism (Marx, Engels, Lenin), Luxemburgism and Anarchism. Two disagreements, Marxism against each, each citing passages of both sides. Checked against the texts: the Soviets as "a new type of state … a particular form of the dictatorship of the proletariat" (¶43 of Lenin's *Letter to American Workingmen*), cited for the Marxist position; and "in one country State Socialism, in another Federation" (¶354 of *The Conquest of Bread*), cited for the anarchist one.
- **Problems met:**
  - Disagreements were headed "Leninism vs Anarchism | …", which the format does not give them, and the bar was printed. The sides are now kept apart and printed as a label (`c2028eb`). Regression test confirmed to fail before the fix.
  - In the first run the model listed Leninism as a tradition apart from Marxism, so the platform's "Marxist assessment" criticised Leninism, against its Marxist-Leninist standpoint. It also took ¶72 of *The Accumulation of Capital*, an editor's biographical introduction ("gave Rosa Luxemburg a welcome opportunity…"), as Luxemburg's own words. The prompts now keep Lenin within Marxism and say that an editor's introduction or a quoted writer is not the tradition's own words (`361bd17`). Prompt test confirmed to fail before the fix. In the second run Leninism was no longer separate, but ¶72 was still retrieved and cited for Luxemburg's position along with another paragraph. Not changed further: the code cannot tell an introduction from the author's text, and the library has no text of Luxemburg's on the state.
  - The first CLI test named Fabianism as a tradition the library has no material on. It has some: Kropotkin and Engels both mention the Fabians, so the passages were correctly found and the test was wrong. It now uses an invented tradition.
  - Keyword search is weak for some traditions: Kropotkin's ¶655 (German military societies) was retrieved for anarchism on the state. Not changed.
- **Design changes from Stage 1 introduced here:**
  - Stage 1 gives F12 two names ("Comparison of Leftist Perspectives" in the feature specification, "Ideological Context and Related Traditions" in UC12 and the traceability table). The implementation does both: a structured comparison of positions (the feature specification) that also gives each tradition's historical conditions and the Marxist assessment of it, kept apart from its own position (UC12).
  - `IdeologicalContextService` keeps Stage 1's three methods. `findRelevantTraditions()` is one model call given the topic and the library's authors and titles; the model names each tradition's representatives from that list, so "its own words" means passages from those authors' texts (matched on surname by `authored_by`). `explainHistoricalContext()` is the comparison call, whose `conditions:` lines carry the historical context. `recommendRepresentativeTexts()` lists each tradition's own texts, the cited ones first. `LibraryService.search()` is replaced by the `passage_search` and `source_retrieval` tools, as in F07 and F10.
  - UC12's alternatives: a tradition the model names but for which nothing is found is left out and named as left out; if only Marxism has material, nothing is compared. A tradition with no text of its own may still be described from others' passages, and the reader is told. When the model judges that no tradition differs materially, the command says so and points to `analyze`. A disagreement must cite passages of two traditions or it is dropped; if none survives, the reader is told rather than shown one.
  - Without a model nothing can be compared, since the traditions come from the model; the command reports an error. Comparisons are not stored and cannot yet be saved to the workspace. Opening one from a news event is not built.
- **Human contribution:** Asked for the next five slices. Reviewed the code.
- **Outcome:** Five code commits and this documentation commit.

### 2026-11-22 — Personalized and adaptive assistance (F14)

- **Task:** Complete F14 (UC14, SD07, Stage 1's `PersonalizationService`). Personalization already existed as one profile-wide setting (`reader_context`, explanation depth, the personalization switch). UC14 also asks for the reader's familiarity with the *current* topic, for knowledge gaps to be considered, and for the reader to override the level of detail.
- **Input/Instruction:** Second of the five slices requested.
- **AI contribution:** Added `praxis/reader_model/personalization.py`: `RequestPreferences` (depth and personalization for one request, applied to a copy of the profile), `Familiarity`, `topic_words` and `PersonalizationService` (`profile_for`, `determine_explanation_depth`, `familiarity`, `personalize_prompt`). `reader_context` in the prompts now delegates to it and takes the request's topic, and every prompt builder with a topic passes it (question, research plan and synthesis, comparison, recommendation, history, analysis, traditions). The agent's `answer_question`, `research`, `continue_research`, `explore_history`, `analyze` and `analyze_research` take `RequestPreferences`. In the CLI: `--detail brief|standard|detailed` on `ask`, `research`, `sessions continue` and `annotate`, and `--general` on those and on `history`, `analyze`, `sessions analyze`, `traditions`, `sessions traditions` and `recommend`. 751 automated tests. Live runs against `gpt-5-mini` on the scratch database, with "surplus value" stated at advanced level and "dialectics" at introductory:
  - `ask "Where does surplus value come from?" --general` (19 s, 6,294 tokens): labelled "AI-generated", not adapted; it defined constant and variable capital.
  - The same with `--detail brief` (5,168 tokens): labelled "adapted to your reader profile", and shorter, but three paragraphs where the depth guidance asks for two or three sentences. The model follows the depth guidance loosely. The first `--detail brief` run printed no explanation; its output was not captured, so the cause is not known.
- **Problems met:**
  - The first version of `topic_words` made "analysis" into "analysi" by dropping a final s. Found by an AI-written test before commit; words ending in -is and -us are now kept.
- **Design changes from Stage 1 introduced here:**
  - `PersonalizationService.personalizePrompt()` is `personalize_prompt(profile, topic)`. It returns the text the prompt builders append, rather than rewriting a prompt. `determineExplanationDepth()` is `determine_explanation_depth(profile)`. `filterKnownPrerequisites()` stays in `PrerequisiteService` (F08), which already leaves out stated knowledge.
  - UC14 step 2 ("likely familiarity with the current topic"): knowledge areas sharing a word with the request's topic are listed first, under "On this topic". Step 4 ("knowledge gaps are considered"): when no area matches, the model is told not to assume the reader knows the topic and to define its basic terms. Matching is on words, so "the state" also matches "state capitalism". Annotations (F06) get no topic, since a paragraph has none to match, and keep the whole profile.
  - UC14's "The user can override the level of detail": `RequestPreferences` change a copy of the profile for one request and are never stored; `profile depth` and `profile personalize` remain the lasting settings. A request cannot turn personalization back on when the reader has turned it off. `--detail` is offered only where prompts use the explanation depth (questions, research synthesis, annotations).
- **Human contribution:** Reviewed the code.
- **Outcome:** Four code commits and this documentation commit.

### 2026-11-22 — Graphical interface, first slice: window, library, reader and profile

- **Task:** Start the GUI the Stage 2 instructions require ("a graphical user interface through which users can access the application's major functionality"). Until now everything ran through the CLI. This slice: the window and the background running of model requests, the library and reader (F05, F06) and the profile (F13, F14).
- **Input/Instruction:** Third of the five slices requested.
- **AI contribution:** Added `Database(shared_with_worker=True)` and PySide6 to `requirements.txt` (it was already installed in the virtual environment). Added the package `praxis/gui/`: `tasks.py` (`TaskRunner`, `ThreadTaskRunner` on one worker thread, `InlineTaskRunner` for tests), `main_window.py` (`MainWindow`: a page list and the pages, with the runner's status in the status bar), `home.py` (`HomeController`, `HomeView`), `library.py` (`LibraryController`, `ReadingController`, `LibraryView`), `profile.py` (`ProfileController`, `ProfileView`), `render.py` (results as Markdown for the text panes, the GUI's counterpart of the CLI's printing functions) and `launch.py` (`build_window`, `run`). `Application` gained `llm`. `praxis gui` and `python -m praxis.gui` open the window. 766 automated tests; the GUI tests run Qt offscreen with a scripted model. The real launcher was started offscreen against the scratch database and closed after half a second (exit code 0), and each page was rendered to an image and looked at.
- **Problems met:**
  - The first test of inferred knowledge opened one page of a text and expected knowledge to be inferred. Knowledge is inferred only when a text is finished (F13's updater). The test now opens the last page of Lenin's letter.
  - An AI-written test asserted `"¶3" in prompt or "3" in prompt`, which would pass on almost any prompt. It now checks for "Passage to annotate (¶3)".
- **Design changes from Stage 1 introduced here:**
  - MVC as Stage 1 describes it: each page is a View (`LibraryView`, `ProfileView`) that only collects input and shows results, and its Controller (`LibraryController`, `ReadingController`, `ProfileController`) calls the same services the CLI uses, through the same `Application`. Stage 1's `ReaderView` is the right half of the library page, not a page of its own, so choosing a text and reading it happen side by side. The CLI commands play the controller role for the CLI, as before.
  - Not in Stage 1: model calls take up to a minute, so they run on a worker thread (`ThreadTaskRunner`), with the result handed back to the GUI thread by a Qt signal. SQLite connections may not be used from two threads at once, so only one request runs at a time, and every widget that reads the database is disabled while one runs. Pages refresh when shown, except while a request runs.
  - Reading a page in the GUI records progress through the `LearningEventBus`, as `library read` does. Resetting the whole profile is left to the CLI (`profile reset`), which asks for confirmation.
- **Human contribution:** Reviewed the code.
- **Outcome:** Four code commits and this documentation commit.

### 2026-11-22 — Graphical interface, second slice: research, past research and learning paths

- **Task:** Bring the agent's requests into the GUI.
- **Input/Instruction:** Fourth of the five slices requested. The session hit its usage limit partway through; the slice was finished after it reset ("Continue the task you were working on").
- **AI contribution:** Added `praxis/gui/results.py` (each feature's result as Markdown, following the CLI's labels), `research.py` (`ResearchController`, `ResearchView`: ask F04, research F03, history F09, analysis F11, traditions F12, readings F07, learning paths F08, with per-request detail and "general" options from F14), `sessions.py` (`SessionsController`, `SessionsView`: reopen stored research, continue it with a focus, and run analysis, text comparison or traditions on it), `paths.py` (`PathsController`, `PathsView`: stored learning paths and marking steps) and `widgets.py` (shared `lock_while_busy` and `result_browser`). Passage links in results open the text at that paragraph on the library page. 784 automated tests. One live run of the research page's "Ask a question" against `gpt-5-mini`, on a real worker thread, offscreen (23 s): the passages came first and the explanation was labelled AI-generated and adapted to the reader profile. The phrase it quoted, "orders it to raise itself above the danger of self government", is in the cited ¶121 of the *Brumaire*. The page was rendered to an image and looked at.
- **Problems met:**
  - An AI-written GUI test switched the model off by setting a private attribute. It was replaced by a test of a real follow-up: comparing a session's texts when the model's reply is unreadable.
  - Passage-link handling was first written twice (research and past research pages), and the past research page's buttons were re-enabled after a request even with no session chosen. Both were corrected before commit: the links moved to `widgets.result_browser`, and the buttons now follow the selection.
  - Italics marked with underscores in the Gutenberg texts (`_Socialist_`) are shown with their underscores, because passage text is escaped so that it is never read as formatting. Not changed.
- **Design changes from Stage 1 introduced here:**
  - Stage 1's `ResearchView`/`ResearchController` handle research only. Here the research page is where the reader makes every request to the agent and the reading services, chosen from a list, because each takes the same input (a topic or question) and shows the same kind of result (passages, then labelled AI output).
  - Marking a learning-path step in the GUI publishes `PrerequisiteMarkedKnown`, as `path mark` does, so the GUI and CLI update the reader model the same way (Observer).
- **Human contribution:** Reviewed the code.
- **Outcome:** Three code commits, this documentation commit and one earlier interim log commit.

### 2026-11-22 — Graphical interface, third slice: news, compare and workspace

- **Task:** Complete the GUI: the news dashboard and event view (F01, F02), comparing chosen texts (F10), and the workspace (F15), with saving from the other pages.
- **Input/Instruction:** Fifth of the five slices requested.
- **AI contribution:** Added `praxis/gui/news.py` (`NewsController`, `NewsView`: fetch or show the dashboard, open an event, then research it, compare its outlets, trace its history or save it), `compare.py` (`CompareController`, `CompareView`: tick two to four texts, name the subject, reopen earlier comparisons), `workspace.py` (`WorkspaceController`, `WorkspaceView`, `Resume`: list, filter, search, notes, removal, and "Continue" back to the page an item came from), renderers for event cards, expanded events and comparisons in `results.py`, and `widgets.item_list`. Save buttons were added to the library page (text, paragraph) and the research page (answers and research results). The GUI test fixture now gives the application no news feeds unless a test passes some, so no test reaches the real feeds. 793 automated tests. The README now says all fifteen features work through both interfaces, and lists the options that remain CLI-only. Live run of the news page against the real feeds and `gpt-5-mini` on the scratch database, on a worker thread, offscreen: fetching and the dashboard took 165 s (12 of 79 events, 32 reports, each with an AI summary). Opening the first event (COP31) took 47 s; its account's claim that "the EU, the UK and some allies in the developing world" rejected the text is in the cited Guardian report. Both views were rendered to images and looked at.
- **Problems met:**
  - In the live run the multi-line event cards ran together in the list. Lists whose entries span lines are now shaded alternately and spaced (`widgets.item_list`), in its own commit.
  - The event's library background was two passages matched by keyword only: Luxemburg on diplomats vetoing Turkey's affairs (¶1632 of *The Accumulation of Capital*) and Trotsky on Soviet Russia's lack of coal and oil. This is F02's existing retrieval, not something the GUI added. Not changed.
  - AI-written tests assumed opening an event makes one model call (it makes two: search terms, then the account) and that a saved event's title is the headline (it is "Event: …"). Both were corrected against the code before commit.
- **Design changes from Stage 1 introduced here:**
  - Stage 1's `NewsView`/`NewsController` and `WorkspaceView`/`WorkspaceController` are pages of the main window. SD03's event actions (research, compare, history) are buttons on the opened event, as `news event --research/--compare/--history` are in the CLI.
  - F15 had no sequence diagram in Stage 1. In the GUI, `WorkspaceController.resume` decides where a saved item continues (text and paragraph, research session, comparison or event), and the window shows that page. A saved text resumes after the furthest paragraph read; one no longer in the library shows the saved copy and says so (F15's error case), with "Continue" disabled.
  - Saving is offered where the CLI offers `--save`, except comparisons, which are already stored and listed on the compare page.
- **Human contribution:** Reviewed the code.
- **Outcome:** Four code commits and this documentation commit.

### 2026-11-22 — README rewrite

- **Task:** Make the README fully up to date with the app and easy to use.
- **Input/Instruction:** The user asked for the README to be brought up to date with the app's functionality and made easy to use.
- **AI contribution:** Checked every CLI command and option against `--help` and the GUI pages against `praxis/gui/launch.py`, then restructured the README: a four-step quick start, a feature table mapping F01–F15 to their GUI page and CLI command, the GUI pages in sidebar order, a CLI reference grouped by task with copy-pasteable examples, the per-feature explanations in collapsible sections, and a troubleshooting table. Added the commands the old README left out (`library topics`, `news feeds`, `profile forget/personalize/background/reset`, `workspace save-text/note/search/remove`, `sessions analyze/traditions`) and the CLI-only list now includes Gutenberg import and `.txt` download.
- **Problems met:** The old README said `pip install -e .` gives a `praxis` command; it fails, because setuptools finds several top-level folders and `pyproject.toml` does not name the package. The README now uses `python -m praxis` throughout; `pyproject.toml` was not changed.
- **Human contribution:** Requested the change.
- **Outcome:** One documentation commit.

### 2026-11-22 — GUI theme

- **Task:** Make the GUI look better with a ready-made theme library.
- **Input/Instruction:** The user asked for a ready-made Qt theme library, styled in keeping with Marxist aesthetics.
- **AI contribution:** Added `qt-material` (to `requirements.txt`) and a custom light theme, `praxis/gui/praxis_theme.xml`: constructivist red (`#b71c1c`) on cream paper (`#f3ecdc`) with near-black text. `praxis/gui/theme.py` applies it at launch (`launch.run`). The pages were rendered offscreen to images and looked at. 793 automated tests pass.
- **Problems met:** qt-material draws a selected row's text in the theme's dark text colour, which is hard to read on the red selection. Overriding it with `color` or a widget-level `selection-color` had no effect; testing qt-material's rules one at a time showed its `QListView::item:selected:focus` rule wins, and Qt takes a selected item's text colour from `selection-color` on the item rule. `theme.py` adds that rule, giving cream text on red.
- **Human contribution:** Chose the library approach and the aesthetic.
- **Outcome:** One code commit with this log entry.

### 2026-11-23 — GUI overhaul: home page and reader

- **Task:** Overhaul the GUI's user experience, starting with the home and library pages.
- **Input/Instruction:** The user specified the home page (news cards fetched on start-up, readings to return to, the current learning path with progress and Continue) and the library (only the list until a text is chosen; then a reader that fills the page, shows the text as one continuous scroll, and replaces the controls below it with an "Ask about" menu on each paragraph number that shows a request in progress and then the annotation inline in another colour). The rest was left to the AI's judgement.
- **AI contribution:** Added `praxis/gui/reader.py` (`ReaderPane`, `ReaderText`): the whole text as Qt rich text, paragraph numbers as links, stored and new annotations in a tinted box with their own ink under their paragraph, a note while one is being written and the error if it fails, a centred 760-pixel serif column, and progress taken from the paragraph at the bottom of the screen once scrolling pauses. Rewrote `praxis/gui/library.py` around a list view and a reader view; `ReadingController.open_text` replaces the ten-paragraph `open_page`, and `record_progress` publishes `DocumentRead`. Rewrote `praxis/gui/home.py` (`HomeController.news`, `readings`, `current_path`) with three sections of cards, and added `widgets.Card`. `launch.run` fetches the news when the window opens; the dashboard is handed to the News page (`NewsView.show_dashboard`). Removed `render.paragraphs` and `render.annotation_markdown`, no longer used. Updated the README's page descriptions. 801 automated tests (new: `tests/test_gui_home.py` and the library tests). Home, the library list, the reader with a finished and a pending annotation, and the menu were rendered offscreen with the theme and looked at.
- **Problems met:**
  - In the first render the reader's text was red and in Roboto: qt-material styles text browsers with the theme colour and font. The reader now sets its own stylesheet (black Georgia on paper) and colours paragraphs explicitly.
  - An hourglass emoji in the "being written" note drew as a broken glyph; it is plain text now.
  - Tests compared `toPlainText()` with the no-break spaces after each paragraph number, which Qt turns into ordinary spaces there (the document's blocks keep them, which is what the reader relies on). Tests corrected.
  - Two AI-written home tests called a page's methods without navigating to Home, so the page never refreshed; they now navigate as a user would.
- **Design changes from Stage 1 introduced here:**
  - Stage 1's `ReaderView` paged through a text; the reader now scrolls the whole text and records the furthest paragraph seen, so a saved text resumes from where scrolling stopped rather than after a page.
  - SD04's annotation request starts from the paragraph in the reader (its "Ask about" menu) instead of a separate form below it. Saving a paragraph (F15) moved into the same menu.
  - The home page draws on F01, F13's reading history and F08 together; it calls the same services as the News and Learning paths pages and adds no new ones.
- **Human contribution:** Requested the change and specified the home and library designs.
- **Outcome:** Two code commits and this documentation commit.

### 2026-11-23 — Finding texts beyond the library

- **Task:** Stop research and learning paths being limited to the texts already in the library.
- **Input/Instruction:** The user reported that a learning path for Libya had good steps but pointed only to foundational Marxist texts, and asked that researching a question or building a learning path find genuinely relevant articles, books and other texts on the web, add them to the library and use them. The design was left to the AI.
- **AI contribution:** Added `praxis/discovery/`: `SourceFinder` (Strategy) with `WebSearchSourceFinder` (a model with web search, asked for substantive, freely readable texts across perspectives, including Marxist and left outlets) and `WikipediaSourceFinder` (Wikipedia's API; CC BY-SA, so shown in full); `WebPageReader`, which keeps an HTML page's article prose and refuses paywalled, script-built and PDF pages; and `SourceDiscoveryService`, which runs the finders in parallel, skips pages already stored, downloads the rest in parallel and saves them as `Article`s tagged with the topic. Web pages are licensed as not reproducible, so they are quoted in excerpts with a link, like news. Added `WebSearchClient` and `OpenAIWebSearchAdapter` (Responses API `web_search` tool) beside `LLMClient`. `PoliticalResearchAgent` (research and its continuation, ask, history, analyze) and `PrerequisiteService` discover texts first; a learning-path step reads first from the texts found for it. Each result says what was added. Added `praxis library discover` and the `PRAXIS_WEB_DISCOVERY` setting. 824 automated tests (new: `tests/test_discovery.py`, `tests/test_discovery_features.py`), all offline. Tried live: a learning path for "Libya" cited Wikipedia on Ottoman Tripolitania and Italian colonisation, Tricontinental on NATO's 2011 war and MERIP on settler colonialism; `ask` on who backs the RSF in Sudan answered from Peoples Dispatch, The Guardian and Wikipedia in 50 seconds.
- **Problems met:**
  - The first live learning path took over four minutes, most of it the web search at the model's default reasoning effort. At low effort it took about 30 seconds with similar results; the adapter now asks for low effort and retries without it for models that reject the setting.
  - A Wikipedia page found by both finders was stored from the scraped HTML (with "[2][3]" reference marks) because the web finder ran first. Wikipedia now runs first, so its clean API copy is kept.
  - The first page-furniture filter matched class names anywhere in a word, so a wrapper such as `has-sidebar` would have hidden a whole article; only names that start with a furniture word count now.
  - An AI-written test fixture repeated its paragraphs to look long, which the reader correctly de-duplicates below its minimum length; the fixture now uses distinct paragraphs.
- **Design changes from Stage 1 introduced here:**
  - Stage 1 had texts enter the library only through `LibraryService.importDocument` from a `DocumentProvider`. `SourceDiscoveryService` is a second way in, used by the agent and `PrerequisiteService` before they search; the tools and the citation rules are unchanged, so every reading is still a stored passage.
  - UC08's gap case ("If no appropriate reading exists…") now applies only when nothing is found on the web either.
- **Human contribution:** Reported the problem and set the goal.
- **Outcome:** Two code commits and this documentation commit.

### 2026-11-23 — Structured result panes

- **Task:** Make the results the model produces (research, news, learning paths and the rest) easier to follow and use.
- **Input/Instruction:** The user said every page that shows a structured response from the LLM felt janky because it was all raw text, and asked for them to be developed to be easier to follow and use. The design was left to the AI.
- **AI contribution:** Rewrote `praxis/gui/render.py` as rich-text building blocks (cards, AI boxes, badges, sections, a "Jump to" bar, a progress bar, citation links) and `praxis/gui/results.py` on top of them, replacing the Markdown renderers. Passages and news reports are white serif cards with an Open link; model output is a tinted box labelled AI-generated, in the reader's annotation colours; `[n]` citations in model text link to passage n, and `widgets.result_browser` scrolls to it, opens web links in the browser and hands other links to the page. History's chronology is a date table; analysis claims carry Supported/Tentative badges; comparisons mark each finding with its sources' letters. Research, history, analysis, traditions and comparisons show findings before passages; a plain question (F04) keeps its passages first. The News page's event list is now a `CardList` of clickable cards with a shortened summary and grouping warnings. On the Learning paths page each step has Mark done / I already know this / Skip / Undo links, replacing the step spin box and status menu; settled steps fold to one line and the path shows a progress bar and its next step. A path built on the Research page links to its page. Moved `markdown_html` from `reader.py` to `render.py`. Updated the README. 827 automated tests (new: undoing a step, the Research→Learning paths link, a citation scrolling to its passage). The pages were rendered offscreen from a copy of the real database and looked at before and after.
- **Problems met:**
  - The first render of the news cards had overlapping text: cards in a scrolling list kept the default "Maximum" height policy, which squeezes word-wrapped labels. Cards in a `CardList` now grow to fit.
  - The progress bar's empty part did not draw, because Qt gives an empty table cell no height; each cell now holds a tiny space.
  - Tests that matched the old wording (and drove the removed spin box) were updated; the citation-scroll test has to show the window, as an unshown pane cannot scroll.
- **Design changes from Stage 1 introduced here:**
  - UC08 step 7 (recording progress) now happens from the step itself rather than a separate form; the service call and the `PrerequisiteMarkedKnown` event are unchanged.
  - Multi-source results now lead with the AI findings, each linking down to its passages, rather than listing every passage first; F04 answers still lead with their passages.
- **Human contribution:** Reported the problem and set the goal.
- **Outcome:** One code commit and this log entry.
