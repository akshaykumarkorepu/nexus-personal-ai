"""Model provider adapters."""

from __future__ import annotations

from ..config import Settings
from .anthropic_provider import AnthropicProvider
from .base import Provider, ProviderError
from .demo import DemoProvider
from .ollama_provider import OllamaProvider

__all__ = [
    "AnthropicProvider",
    "DemoProvider",
    "OllamaProvider",
    "Provider",
    "ProviderError",
    "build_provider",
]


def build_provider(settings: Settings) -> Provider | None:
    """Return the configured provider, or None when nothing is configured."""
    match settings.resolved_provider:
        case "anthropic":
            return AnthropicProvider(settings)
        case "ollama":
            return OllamaProvider(settings)
        case "demo":
            return DemoProvider()
        case _:
            return None
