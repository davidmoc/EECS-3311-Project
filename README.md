# EECS-3311-Project — Praxis

An AI-agent platform for researching current events, history and political
theory through a Marxist analytical framework. The Stage 1 design is in
[`Stage 1 - Proposal/`](Stage%201%20-%20Proposal/).

> **Status:** Stage 2 implementation in progress. Working now through the
> CLI: the reading library (F05), the reader model (F13) and the workspace
> (F15). The research agent, news dashboard and GUI are not built yet.

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
# Reading library (F05): five public-domain texts ship in data/library
python -m praxis library seed                # load them (no network needed)
python -m praxis library search "class struggle"
python -m praxis library browse --topic imperialism
python -m praxis library read 59983f05 --start 1 --count 5   # id prefix from search
python -m praxis library read 59983f05 --find "hitherto existing"
python -m praxis library download 59983f05 --to downloads
python -m praxis library import 1346 -t history   # any Project Gutenberg book

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
| `praxis/app.py` | Composition root shared by CLI and GUI |
| `praxis/cli/` | Typer command-line interface |
| `praxis/config.py` | Local settings and API-key handling |
| `praxis/documents/` | Documents, passages, citations, annotations |
| `praxis/library/` | `LibraryService`, `DocumentProvider`, Gutenberg adapter |
| `praxis/llm/` | `LLMClient` interface and the OpenAI adapter |
| `praxis/persistence/` | SQLite database and repositories |
| `praxis/reader_model/` | Reader profile, its service, event bus and updater |
| `praxis/tools/` | Agent tools, tool manager and tool factory |
| `praxis/workspace/` | Saved items, workspace and its service |
| `data/library/` | Bundled public-domain texts and their catalogue |
| `tests/` | Automated tests |
| `docs/collaboration-log.md` | AI–human collaboration record |
