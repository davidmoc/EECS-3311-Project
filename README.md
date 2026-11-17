# EECS-3311-Project — Praxis

An AI-agent platform for researching current events, history and political
theory through a Marxist analytical framework. The Stage 1 design is in
[`Stage 1 - Proposal/`](Stage%201%20-%20Proposal/).

> **Status:** Stage 2 implementation in progress. The foundation layers
> (configuration, document model, LLM adapter, storage, agent tools) are in
> place and tested. The GUI and CLI are not built yet; launch commands will be
> added here when they exist.

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

## Run the tests

```bash
python -m pytest
```

The tests use a fake LLM client and an in-memory database, so they need no
API key and no network access.

## Layout

| Path | Contents |
|---|---|
| `praxis/config.py` | Local settings and API-key handling |
| `praxis/documents/` | Documents, passages, citations, annotations |
| `praxis/llm/` | `LLMClient` interface and the OpenAI adapter |
| `praxis/persistence/` | SQLite database and repositories |
| `praxis/tools/` | Agent tools, tool manager and tool factory |
| `tests/` | Automated tests |
| `docs/collaboration-log.md` | AI–human collaboration record |
