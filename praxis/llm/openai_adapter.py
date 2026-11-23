"""Adapter from the OpenAI chat-completions API to ``LLMClient``."""

from __future__ import annotations

from typing import Any

import openai

from praxis.config import Settings
from praxis.llm.client import LLMClient, LLMError, LLMResponse, Prompt, WebSearchClient


class OpenAILLMAdapter(LLMClient):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        """``client`` lets tests substitute the SDK client; normally omitted."""
        self._model = model
        self._client = client or openai.OpenAI(api_key=api_key, base_url=base_url)

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenAILLMAdapter:
        return cls(
            api_key=settings.require_api_key(),
            model=settings.openai_model,
            base_url=settings.openai_base_url,
        )

    def generate(self, prompt: Prompt) -> LLMResponse:
        messages = []
        if prompt.system:
            messages.append({"role": "system", "content": prompt.system})
        messages.append({"role": "user", "content": prompt.user})

        try:
            completion = self._client.chat.completions.create(
                model=self._model, messages=messages
            )
        except openai.OpenAIError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc

        choices = getattr(completion, "choices", None) or []
        text = (choices[0].message.content or "").strip() if choices else ""
        if not text:
            raise LLMError("The model returned an empty response.")

        usage = getattr(completion, "usage", None)
        return LLMResponse(
            text=text,
            model=getattr(completion, "model", None) or self._model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )


class OpenAIWebSearchAdapter(WebSearchClient):
    """Adapter from the OpenAI Responses API's web search tool to
    ``WebSearchClient``."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._model = model
        self._client = client or openai.OpenAI(api_key=api_key, base_url=base_url)

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenAIWebSearchAdapter:
        return cls(
            api_key=settings.require_api_key(),
            model=settings.openai_model,
            base_url=settings.openai_base_url,
        )

    def search(self, prompt: Prompt) -> LLMResponse:
        request = dict(
            model=self._model,
            tools=[{"type": "web_search"}],
            instructions=prompt.system or None,
            input=prompt.user,
        )
        try:
            try:
                # Low effort: finding links needs little reasoning, and at the
                # default effort a search took minutes instead of ~30 seconds.
                response = self._client.responses.create(**request, reasoning={"effort": "low"})
            except openai.BadRequestError:
                # Models without reasoning reject the setting.
                response = self._client.responses.create(**request)
        except openai.OpenAIError as exc:
            raise LLMError(f"Web search failed: {exc}") from exc

        text = (getattr(response, "output_text", None) or "").strip()
        if not text:
            raise LLMError("The web search returned an empty response.")
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=text,
            model=getattr(response, "model", None) or self._model,
            prompt_tokens=getattr(usage, "input_tokens", 0) or 0,
            completion_tokens=getattr(usage, "output_tokens", 0) or 0,
        )
