"""Base provider interface — OpenAI-compatible IR for LLM abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TypedDict


class Message(TypedDict, total=False):
    """Unified message representation (OpenAI-compatible format)."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | list[dict] | None
    tool_calls: list[dict] | None  # assistant message with tool calls
    tool_call_id: str | None  # tool message
    name: str | None  # tool message — function name


class ToolDef(TypedDict):
    """Tool definition in OpenAI function-calling format."""

    type: str  # "function"
    function: dict  # {"name", "description", "parameters"}


@dataclass
class ProviderResponse:
    """Normalized response from any LLM provider."""

    content: str | None = None
    tool_calls: list[dict] | None = None
    finish_reason: str = "stop"


class BaseProvider(ABC):
    """Abstract base for LLM providers.

    All implementations accept and return the unified IR (Message, ToolDef,
    ProviderResponse), so the Agent layer never knows which provider is active.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDef] | None = None,
    ) -> ProviderResponse:
        """Send a chat completion request and return a normalized response."""
        ...
