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
- **Human contribution:** Asked for the next five slices. The code has not been reviewed yet.
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
- **Human contribution:** None on this slice yet; the code has not been reviewed.
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
- **Human contribution:** None on this slice yet; the code has not been reviewed.
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
- **Human contribution:** None on this slice yet; the code has not been reviewed.
- **Outcome:** Five code commits and this documentation commit.
