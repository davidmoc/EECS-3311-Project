"""Local configuration.

Secrets live in a git-ignored ``.env`` file (see ``.env.example``). Nothing in
this module contains or logs a real credential.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

API_KEY_PLACEHOLDER = "YOUR_LOCAL_API_KEY_HERE"
DEFAULT_MODEL = "gpt-5-mini"
DEFAULT_DATABASE_PATH = Path("data/praxis.db")


_OFF = ("off", "0", "false", "no")


class ConfigError(Exception):
    """Raised when required local configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    openai_model: str = DEFAULT_MODEL
    openai_base_url: str | None = None
    database_path: Path = DEFAULT_DATABASE_PATH
    # Look beyond the library (web search, Wikipedia) for texts on what
    # the reader researches, and add them to it. Off unless configured, so
    # code that builds Settings directly (tests) never touches the network;
    # load_settings turns it on unless PRAXIS_WEB_DISCOVERY is "off".
    web_discovery: bool = False

    def require_api_key(self) -> str:
        """Return the API key, or explain how to configure one.

        Only features that call the LLM need a key, so the check is made on
        demand rather than at startup.
        """
        if not self.openai_api_key:
            raise ConfigError(
                "No OpenAI API key configured. Copy .env.example to .env and "
                "set OPENAI_API_KEY."
            )
        return self.openai_api_key


def load_settings(
    env: Mapping[str, str] | None = None,
    env_file: Path | str = ".env",
) -> Settings:
    """Build Settings from ``env_file`` overlaid with process environment.

    Passing ``env`` explicitly bypasses both sources, which keeps tests
    independent of the developer's real configuration.
    """
    if env is None:
        values: dict[str, str | None] = dict(dotenv_values(env_file))
        values.update(os.environ)
    else:
        values = dict(env)

    def get(name: str) -> str | None:
        value = (values.get(name) or "").strip()
        return value or None

    api_key = get("OPENAI_API_KEY")
    if api_key == API_KEY_PLACEHOLDER:
        api_key = None

    return Settings(
        openai_api_key=api_key,
        openai_model=get("OPENAI_MODEL") or DEFAULT_MODEL,
        openai_base_url=get("OPENAI_BASE_URL"),
        database_path=Path(get("PRAXIS_DATABASE_PATH") or DEFAULT_DATABASE_PATH),
        web_discovery=(get("PRAXIS_WEB_DISCOVERY") or "on").lower() not in _OFF,
    )
