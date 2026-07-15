from types import SimpleNamespace

import pytest

from src.integrations.llm_gateway import LLMConfig, LLMGateway, LLMProvider


class FakeResponses:
    def __init__(self, recorder):
        self.recorder = recorder

    def create(self, **kwargs):
        self.recorder.update(kwargs)
        return SimpleNamespace(output_text="responses-ok")


class FakeChatCompletions:
    def create(self, **kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="chat-ok"))]
        )


class FakeOpenAIClient:
    def __init__(self, recorder):
        self.responses = FakeResponses(recorder)
        self.chat = SimpleNamespace(completions=FakeChatCompletions())


def test_codex_responses_adapter_supports_custom_base_url():
    request = {}
    client_args = {}

    def factory(**kwargs):
        client_args.update(kwargs)
        return FakeOpenAIClient(request)

    gateway = LLMGateway(
        LLMConfig(
            provider=LLMProvider.CODEX_RESPONSES.value,
            api_key="secret",
            base_url="https://gateway.example/v1",
            model="third-party-codex",
        ),
        openai_client_factory=factory,
    )

    assert gateway.generate("hello", "system") == "responses-ok"
    assert client_args["base_url"] == "https://gateway.example/v1"
    assert request["model"] == "third-party-codex"
    assert request["input"] == "hello"
    assert request["instructions"] == "system"


def test_claude_messages_adapter_supports_custom_base_url():
    client_args = {}
    request = {}

    class Messages:
        def create(self, **kwargs):
            request.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="claude-ok")])

    def factory(**kwargs):
        client_args.update(kwargs)
        return SimpleNamespace(messages=Messages())

    gateway = LLMGateway(
        LLMConfig(
            provider=LLMProvider.CLAUDE_MESSAGES.value,
            api_key="secret",
            base_url="https://cc.example",
            model="third-party-claude",
        ),
        anthropic_client_factory=factory,
    )

    assert gateway.generate("hello", "system") == "claude-ok"
    assert client_args["base_url"] == "https://cc.example"
    assert request["system"] == "system"
    assert request["messages"][0]["content"] == "hello"


def test_gateway_requires_key_and_model():
    gateway = LLMGateway(LLMConfig())

    with pytest.raises(ValueError, match="API Key"):
        gateway.generate("hello")

    gateway.update_config({"api_key": "secret"})
    with pytest.raises(ValueError, match="Model ID"):
        gateway.generate("hello")


def test_chat_provider_reads_openai_environment(monkeypatch):
    monkeypatch.setenv("FUND_LLM_PROVIDER", LLMProvider.OPENAI_CHAT.value)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://chat.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "chat-model")
    monkeypatch.setenv("CODEX_API_KEY", "codex-key")

    config = LLMConfig.from_env()

    assert config.api_key == "openai-key"
    assert config.base_url == "https://chat.example/v1"
    assert config.model == "chat-model"


def test_gateway_lists_models_without_requiring_model_id():
    class Models:
        def list(self):
            return SimpleNamespace(
                data=[SimpleNamespace(id="gpt-5.6-sol"), SimpleNamespace(id="gpt-5.4")]
            )

    def factory(**_kwargs):
        return SimpleNamespace(models=Models())

    gateway = LLMGateway(
        LLMConfig(
            provider=LLMProvider.CODEX_RESPONSES.value,
            api_key="secret",
            base_url="https://gateway.example/v1",
            model="",
        ),
        openai_client_factory=factory,
    )

    assert gateway.list_models() == ["gpt-5.4", "gpt-5.6-sol"]
