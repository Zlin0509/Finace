import os
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional

import anthropic
import openai


class LLMProvider(str, Enum):
    CODEX_RESPONSES = "codex_responses"
    CLAUDE_MESSAGES = "claude_messages"
    OPENAI_CHAT = "openai_chat"


PROVIDER_LABELS = {
    LLMProvider.CODEX_RESPONSES.value: "Codex / OpenAI Responses 兼容",
    LLMProvider.CLAUDE_MESSAGES.value: "CC / Anthropic Messages 兼容",
    LLMProvider.OPENAI_CHAT.value: "OpenAI Chat Completions 兼容",
}


@dataclass
class LLMConfig:
    provider: str = LLMProvider.CODEX_RESPONSES.value
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    timeout_seconds: float = 120.0
    max_tokens: int = 900
    temperature: float = 0.3

    @classmethod
    def from_env(cls) -> "LLMConfig":
        provider = os.getenv("FUND_LLM_PROVIDER", LLMProvider.CODEX_RESPONSES.value)

        if provider == LLMProvider.CLAUDE_MESSAGES.value:
            api_key = os.getenv(
                "CC_API_KEY",
                os.getenv("ANTHROPIC_AUTH_TOKEN", os.getenv("ANTHROPIC_API_KEY", "")),
            )
            base_url = os.getenv("CC_BASE_URL", os.getenv("ANTHROPIC_BASE_URL", ""))
            model = os.getenv("CC_MODEL", os.getenv("ANTHROPIC_MODEL", ""))
        elif provider == LLMProvider.CODEX_RESPONSES.value:
            api_key = os.getenv("CODEX_API_KEY", os.getenv("OPENAI_API_KEY", ""))
            base_url = os.getenv("CODEX_BASE_URL", os.getenv("OPENAI_BASE_URL", ""))
            model = os.getenv("CODEX_MODEL", os.getenv("OPENAI_MODEL", ""))
        else:
            api_key = os.getenv("OPENAI_API_KEY", "")
            base_url = os.getenv("OPENAI_BASE_URL", "")
            model = os.getenv("OPENAI_MODEL", "")

        return cls(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout_seconds=float(os.getenv("FUND_LLM_TIMEOUT", "120")),
            max_tokens=int(os.getenv("FUND_LLM_MAX_TOKENS", "900")),
        )

    @classmethod
    def from_dict(cls, values: Dict[str, Any]) -> "LLMConfig":
        provider = values.get("provider") or values.get("api_type")
        if provider == "Anthropic":
            provider = LLMProvider.CLAUDE_MESSAGES.value
        elif provider in {"OpenAI", "OpenAI (兼容格式)"}:
            provider = LLMProvider.OPENAI_CHAT.value

        return cls(
            provider=provider or LLMProvider.CODEX_RESPONSES.value,
            api_key=str(values.get("api_key", "")),
            base_url=str(values.get("base_url", "")),
            model=str(values.get("model", "")),
            timeout_seconds=float(values.get("timeout_seconds", 120.0)),
            max_tokens=int(values.get("max_tokens", 900)),
            temperature=float(values.get("temperature", 0.3)),
        )

    def to_dict(self, include_api_key: bool = True) -> Dict[str, Any]:
        values = asdict(self)
        if not include_api_key:
            values["api_key"] = ""
        return values


class LLMGateway:
    """Protocol adapter for Codex/Responses and Claude Code-compatible APIs."""

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        openai_client_factory: Optional[Callable[..., Any]] = None,
        anthropic_client_factory: Optional[Callable[..., Any]] = None,
    ):
        self.config = config or LLMConfig.from_env()
        self._openai_client_factory = openai_client_factory or openai.OpenAI
        self._anthropic_client_factory = anthropic_client_factory or anthropic.Anthropic

    def update_config(self, values: Dict[str, Any]) -> None:
        merged = self.config.to_dict()
        merged.update(values)
        self.config = LLMConfig.from_dict(merged)

    def validate(self) -> None:
        if self.config.provider not in PROVIDER_LABELS:
            raise ValueError(f"不支持的 LLM 协议: {self.config.provider}")
        if not self.config.api_key.strip():
            raise ValueError("API Key 不能为空")
        if not self.config.model.strip():
            raise ValueError("Model ID 不能为空")
        if self.config.timeout_seconds <= 0:
            raise ValueError("请求超时必须大于 0 秒")

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
    ) -> str:
        self.validate()
        if not prompt.strip():
            raise ValueError("Prompt 不能为空")

        provider = self.config.provider
        if provider == LLMProvider.CODEX_RESPONSES.value:
            return self._call_responses(prompt, system_prompt, max_tokens)
        if provider == LLMProvider.CLAUDE_MESSAGES.value:
            return self._call_anthropic(prompt, system_prompt, max_tokens)
        return self._call_chat_completions(prompt, system_prompt, max_tokens)

    def test_connection(self) -> str:
        return self.generate("只回复 OK", "这是一次 API 连通性测试。", max_tokens=16)

    def list_models(self):
        if not self.config.api_key.strip():
            raise ValueError("API Key 不能为空")

        if self.config.provider == LLMProvider.CLAUDE_MESSAGES.value:
            kwargs: Dict[str, Any] = {
                "api_key": self.config.api_key,
                "timeout": self.config.timeout_seconds,
            }
            if self.config.base_url.strip():
                kwargs["base_url"] = self.config.base_url.strip()
            response = self._anthropic_client_factory(**kwargs).models.list()
        else:
            response = self._openai_client().models.list()

        model_ids = sorted(
            {
                str(model.id)
                for model in getattr(response, "data", [])
                if getattr(model, "id", None)
            }
        )
        if not model_ids:
            raise RuntimeError("接口未返回可用模型")
        return model_ids

    def _openai_client(self):
        kwargs: Dict[str, Any] = {
            "api_key": self.config.api_key,
            "timeout": self.config.timeout_seconds,
        }
        if self.config.base_url.strip():
            kwargs["base_url"] = self.config.base_url.strip()
        return self._openai_client_factory(**kwargs)

    def _call_responses(
        self, prompt: str, system_prompt: str, max_tokens: Optional[int]
    ) -> str:
        kwargs: Dict[str, Any] = {
            "model": self.config.model,
            "input": prompt,
            "max_output_tokens": max_tokens or self.config.max_tokens,
        }
        if system_prompt:
            kwargs["instructions"] = system_prompt

        response = self._openai_client().responses.create(**kwargs)
        output_text = getattr(response, "output_text", None)
        if output_text:
            return str(output_text)

        texts = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", None)
                if text:
                    texts.append(str(text))
        if not texts:
            raise RuntimeError("Responses API 未返回文本内容")
        return "\n".join(texts)

    def _call_chat_completions(
        self, prompt: str, system_prompt: str, max_tokens: Optional[int]
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self._openai_client().chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=max_tokens or self.config.max_tokens,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("Chat Completions API 未返回文本内容")
        return str(content)

    def _call_anthropic(
        self, prompt: str, system_prompt: str, max_tokens: Optional[int]
    ) -> str:
        kwargs: Dict[str, Any] = {
            "api_key": self.config.api_key,
            "timeout": self.config.timeout_seconds,
        }
        if self.config.base_url.strip():
            kwargs["base_url"] = self.config.base_url.strip()

        request: Dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": self.config.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            request["system"] = system_prompt

        response = self._anthropic_client_factory(**kwargs).messages.create(**request)
        texts = [
            str(block.text)
            for block in response.content
            if getattr(block, "type", "") == "text" and getattr(block, "text", None)
        ]
        if not texts:
            raise RuntimeError("Anthropic Messages API 未返回文本内容")
        return "\n".join(texts)
