"""Model providers, and how one gets chosen.

Stratus works with several. Which one runs is a configuration decision, not
something baked into the code that uses it.
"""

from __future__ import annotations

import os

from stratus.agent.providers.base import (
    ModelProvider,
    ProviderResponse,
    TokenUsage,
    messages_to_text,
)

__all__ = [
    "ModelProvider",
    "ProviderResponse",
    "TokenUsage",
    "messages_to_text",
    "get_provider",
    "available_providers",
]


def available_providers() -> dict[str, bool]:
    """Which providers this machine is currently set up for."""
    return {
        "gemini": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
    }


def get_provider(name: str | None = None) -> ModelProvider:
    """Build a provider by name, or pick whichever is configured.

    Preference order when nothing is named: Gemini first, because it is free
    and its key is the one most likely to be present. An explicit STRATUS_MODEL
    or an argument always wins — choosing a provider by accident is exactly
    the sort of thing that produces a surprise bill.
    """
    chosen = (name or os.getenv("STRATUS_MODEL_PROVIDER") or "").strip().lower()

    if not chosen:
        ready = available_providers()
        if ready["gemini"]:
            chosen = "gemini"
        elif ready["anthropic"]:
            chosen = "anthropic"
        else:
            raise RuntimeError(
                "No model provider is configured.\n\n"
                "The free option takes about two minutes:\n"
                "  1. Get a key at https://aistudio.google.com/apikey\n"
                "     (no payment card required)\n"
                "  2. Add it to .env:  GEMINI_API_KEY=your-key-here\n\n"
                "Or set ANTHROPIC_API_KEY to use Claude, which is paid."
            )

    if chosen == "gemini":
        from stratus.agent.providers.gemini import GeminiProvider

        return GeminiProvider()

    if chosen == "anthropic":
        from stratus.agent.providers.anthropic import AnthropicProvider

        return AnthropicProvider()

    raise ValueError(
        f"Unknown model provider {chosen!r}. Known providers: gemini, anthropic."
    )
