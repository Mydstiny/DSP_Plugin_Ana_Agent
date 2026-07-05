"""Anthropic provider — maps Anthropic API to unified IR."""

from __future__ import annotations

import json
import logging

import anthropic

from .base import BaseProvider, Message, ToolDef, ProviderResponse

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseProvider):
    """Provider using the Anthropic Messages API."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDef] | None = None,
    ) -> ProviderResponse:
        # Convert unified messages → Anthropic format
        system_prompt = ""
        anthropic_messages: list[dict] = []

        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                system_prompt += msg.get("content", "")
                continue

            if role == "tool":
                # Tool result message → Anthropic tool_result block
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id", ""),
                        "content": json.dumps(msg.get("content", "")),
                    }],
                })
                continue

            if role == "assistant" and msg.get("tool_calls"):
                # Assistant message with tool calls → Anthropic tool_use blocks
                tool_blocks = []
                for tc in msg["tool_calls"]:
                    func = tc.get("function", {})
                    tool_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": func.get("name", ""),
                        "input": json.loads(func.get("arguments", "{}")),
                    })
                anthropic_messages.append({
                    "role": "assistant",
                    "content": tool_blocks,
                })
                continue

            # Regular text message (user or assistant)
            content = msg.get("content", "")
            if isinstance(content, list):
                # Already a list of content blocks → keep only text blocks
                text = " ".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            else:
                text = str(content or "")
            anthropic_messages.append({
                "role": role,
                "content": text,
            })

        # Convert unified tools → Anthropic tool format
        anthropic_tools: list[dict] | None = None
        if tools:
            anthropic_tools = [
                {
                    "name": t["function"]["name"],
                    "description": t["function"]["description"],
                    "input_schema": t["function"]["parameters"],
                }
                for t in tools
            ]

        # API call
        kwargs: dict = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": anthropic_messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        logger.debug(
            "Anthropic call: model=%s, messages=%d, tools=%d",
            self._model,
            len(anthropic_messages),
            len(anthropic_tools) if anthropic_tools else 0,
        )

        response = await self._client.messages.create(**kwargs)

        # Parse response → unified format
        content_text = ""
        tool_calls: list[dict] = []

        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.input),
                    },
                })

        finish_reason = response.stop_reason or "stop"
        if finish_reason == "end_turn":
            finish_reason = "stop"
        elif finish_reason == "tool_use":
            finish_reason = "tool_calls"

        return ProviderResponse(
            content=content_text or None,
            tool_calls=tool_calls or None,
            finish_reason=finish_reason,
        )
