from types import SimpleNamespace

import openai
import pytest

from praxis.config import ConfigError, Settings
from praxis.llm import LLMError, OpenAILLMAdapter, Prompt


class FakeOpenAIClient:
    """Stands in for ``openai.OpenAI``; records the request it receives."""

    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return self._result


def completion(content, usage=(12, 30), model="served-model"):
    return SimpleNamespace(
        model=model,
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=usage[0], completion_tokens=usage[1])
        if usage
        else None,
    )


def adapter_with(client):
    return OpenAILLMAdapter(api_key="unused", model="configured-model", client=client)


def test_response_is_translated_to_internal_type():
    client = FakeOpenAIClient(completion("  An answer.  "))

    response = adapter_with(client).generate(Prompt(user="Question?"))

    assert response.text == "An answer."
    assert response.model == "served-model"
    assert (response.prompt_tokens, response.completion_tokens) == (12, 30)
    assert response.total_tokens == 42


def test_request_carries_model_and_both_roles():
    client = FakeOpenAIClient(completion("ok"))

    adapter_with(client).generate(Prompt(user="Question?", system="Be brief."))

    assert client.calls == [
        {
            "model": "configured-model",
            "messages": [
                {"role": "system", "content": "Be brief."},
                {"role": "user", "content": "Question?"},
            ],
        }
    ]


def test_system_message_is_omitted_when_empty():
    client = FakeOpenAIClient(completion("ok"))

    adapter_with(client).generate(Prompt(user="Question?"))

    assert [m["role"] for m in client.calls[0]["messages"]] == ["user"]


def test_missing_usage_counts_as_zero_tokens():
    client = FakeOpenAIClient(completion("ok", usage=None))

    assert adapter_with(client).generate(Prompt(user="q")).total_tokens == 0


def test_provider_errors_become_llm_errors():
    client = FakeOpenAIClient(error=openai.OpenAIError("rate limited"))

    with pytest.raises(LLMError, match="rate limited"):
        adapter_with(client).generate(Prompt(user="q"))


@pytest.mark.parametrize("content", [None, "", "   "])
def test_empty_content_is_an_error(content):
    client = FakeOpenAIClient(completion(content))

    with pytest.raises(LLMError, match="empty"):
        adapter_with(client).generate(Prompt(user="q"))


def test_no_choices_is_an_error():
    client = FakeOpenAIClient(SimpleNamespace(choices=[], usage=None, model="m"))

    with pytest.raises(LLMError):
        adapter_with(client).generate(Prompt(user="q"))


def test_blank_prompt_is_rejected_before_any_request():
    with pytest.raises(ValueError):
        Prompt(user="  ")


def test_from_settings_requires_a_key():
    with pytest.raises(ConfigError):
        OpenAILLMAdapter.from_settings(Settings(openai_api_key=None))
