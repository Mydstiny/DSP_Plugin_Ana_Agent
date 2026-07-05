"""OpenAI-compatible provider — works with OpenAI, DeepSeek, Ollama, custom."""

from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from .base import BaseProvider, Message, ToolDef, ProviderResponse

logger = logging.getLogger(__name__)


class OpenAICompatProvider(BaseProvider):
    """Provider using OpenAI-compatible chat completions API.

    Works with any endpoint that implements the /v1/chat/completions format:
    OpenAI, DeepSeek, Ollama, vLLM, custom proxies, etc.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDef] | None = None,
    ) -> ProviderResponse:
        # Build OpenAI-format messages
        openai_messages: list[dict] = []
        for msg in messages:
            role = msg.get("role", "user")

            entry: dict = {"role": role}

            if role == "tool":
                entry["tool_call_id"] = msg.get("tool_call_id", "")
                # Tool content should be a string for OpenAI
                content = msg.get("content", "")
                entry["content"] = (
                    json.dumps(content) if not isinstance(content, str) else content
                )
                entry["name"] = msg.get("name", "")

            elif role == "assistant" and msg.get("tool_calls"):
                entry["content"] = msg.get("content") or ""
                entry["tool_calls"] = msg["tool_calls"]
            else:
                content = msg.get("content", "")
                if isinstance(content, list):
                    text = " ".join(
                        b.get("text", "") for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                else:
                    text = str(content or "")
                entry["content"] = text

            openai_messages.append(entry)

        # API call
        kwargs: dict = {
            "model": self._model,
            "messages": openai_messages,
            "max_tokens": 4096,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        logger.debug(
            "OpenAI-compat call: model=%s, messages=%d, tools=%d, url=%s",
            self._model,
            len(openai_messages),
            len(tools) if tools else 0,
            str(self._client.base_url),
        )

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        # Parse → unified format
        tool_calls: list[dict] | None = None
        if message.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]

        finish = choice.finish_reason or "stop"

        return ProviderResponse(
            content=message.content or None,
            tool_calls=tool_calls,
            finish_reason=finish,
        )
