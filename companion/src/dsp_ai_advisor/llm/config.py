"""LLM configuration loader — reads config.yaml, resolves env vars, creates providers."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider."""

    provider_type: str  # "anthropic" | "openai_compat"
    api_key: str
    model: str
    base_url: str | None = None  # required for openai_compat


@dataclass
class LLMSettings:
    """Top-level LLM configuration from config.yaml."""

    default: str
    providers: dict[str, ProviderConfig] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str | Path) -> LLMSettings:
        """Load configuration from a YAML file.

        Environment variable references (${VAR_NAME}) in api_key fields
        are resolved against os.environ.
        """
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

        llm = raw.get("llm", {})
        default = llm.get("default", "claude")

        providers: dict[str, ProviderConfig] = {}
        for name, cfg in llm.get("providers", {}).items():
            api_key = _resolve_env(cfg.get("api_key", ""))
            providers[name] = ProviderConfig(
                provider_type=cfg["provider_type"],
                api_key=api_key,
                model=cfg["model"],
                base_url=cfg.get("base_url"),
            )

        return cls(default=default, providers=providers)

    def create_provider(self, name: str | None = None) -> BaseProvider:
        """Factory: create a provider instance by name.

        If name is None, uses self.default.
        """
        from .anthropic_provider import AnthropicProvider
        from .openai_compat_provider import OpenAICompatProvider

        name = name or self.default
        if name not in self.providers:
            available = ", ".join(self.providers.keys())
            raise ValueError(
                f"Provider '{name}' not found. Available: {available}"
            )

        cfg = self.providers[name]
        if cfg.provider_type == "anthropic":
            return AnthropicProvider(api_key=cfg.api_key, model=cfg.model)
        elif cfg.provider_type == "openai_compat":
            return OpenAICompatProvider(
                api_key=cfg.api_key,
                model=cfg.model,
                base_url=cfg.base_url or "https://api.openai.com/v1",
            )
        else:
            raise ValueError(f"Unknown provider_type: {cfg.provider_type}")


# Import here to avoid circular dependency — BaseProvider is used in the type hint
from .base import BaseProvider  # noqa: E402


def _resolve_env(value: str) -> str:
    """Replace ${VAR_NAME} patterns with environment variable values."""
    pattern = re.compile(r"\$\{(\w+)\}")

    def _replacer(match: re.Match) -> str:
        var = match.group(1)
        return os.environ.get(var, f"${{{var}}}")

    return pattern.sub(_replacer, value)
