"""Claude, via the Anthropic API.

Kept alongside the free providers so the two can be compared on identical
requests. Needs a paid balance; Stratus does not default to it.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel

from stratus.agent.providers.base import ProviderResponse, TokenUsage

DEFAULT_MODEL = "claude-opus-5"

INPUT_PER_MTOK = 5.0
OUTPUT_PER_MTOK = 25.0
CACHED_INPUT_PER_MTOK = 0.5
"""Cached input is billed at roughly a tenth of the normal rate, which is why
the system prompt is held byte-identical between requests."""


class AnthropicProvider:
    name = "Anthropic Claude"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        client: Any | None = None,
    ) -> None:
        self.model = model

        if client is not None:
            self._client = client
            return

        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "No Anthropic API key found. Set ANTHROPIC_API_KEY in .env, "
                "or use the Gemini provider, which is free."
            )

        import anthropic

        self._client = anthropic.Anthropic(api_key=key)

    def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        schema: type[BaseModel],
    ) -> ProviderResponse:
        response = self._client.messages.parse(
            model=self.model,
            max_tokens=16000,
            system=[
                {
                    "type": "text",
                    "text": system,
                    # Identical between requests, so it can be served from
                    # cache at a fraction of the price.
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=messages,
            output_format=schema,
        )

        usage = getattr(response, "usage", None)
        return ProviderResponse(
            parsed=getattr(response, "parsed_output", None),
            usage=TokenUsage(
                input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
                output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
                cached_tokens=(getattr(usage, "cache_read_input_tokens", 0) or 0)
                if usage
                else 0,
                calls=1,
            ),
            stop_reason=getattr(response, "stop_reason", None),
        )

    def price(self, usage: TokenUsage) -> float:
        return (
            usage.input_tokens * INPUT_PER_MTOK
            + usage.cached_tokens * CACHED_INPUT_PER_MTOK
            + usage.output_tokens * OUTPUT_PER_MTOK
        ) / 1_000_000
