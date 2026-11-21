"""The agent subsystem.

Python note: importing any module inside a package (``praxis.agent.corpus``)
first runs this file. The facade in ``agent.py`` depends on
``praxis.research``, which in turn uses ``corpus``, ``prompts`` and
``response`` from here, so loading the facade eagerly would create an
import cycle. Instead, the facade's names are loaded on first use through
a module-level ``__getattr__``, which Python calls for names a module does
not define (PEP 562). ``from praxis.agent import PoliticalResearchAgent``
works as usual.
"""

from praxis.agent.corpus import ResearchCorpus, Source
from praxis.agent.prompts import PromptBuilder, reader_context
from praxis.agent.response import AgentResponse, ResponseStatus

_FACADE_NAMES = {"AgentError", "PoliticalResearchAgent", "check_citations"}

__all__ = [
    "AgentError",
    "AgentResponse",
    "PoliticalResearchAgent",
    "PromptBuilder",
    "ResearchCorpus",
    "ResponseStatus",
    "Source",
    "check_citations",
    "reader_context",
]


def __getattr__(name: str):
    if name in _FACADE_NAMES:
        from praxis.agent import agent

        return getattr(agent, name)
    raise AttributeError(f"module 'praxis.agent' has no attribute '{name}'")
