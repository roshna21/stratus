"""The boundary between Stratus and whichever model is doing the reasoning.

Everything above this line — the repair loop, the prompts, the validation —
is the same regardless of which model runs. Only the code below it knows
whether it is talking to Anthropic, Google, or a model on your own laptop.

That separation is worth having for its own sake: a project welded to one
vendor's SDK cannot switch when that vendor's pricing, limits, or terms
change. It also makes it possible to run the same request through several
models and compare what comes back, which is how you find out whether the
expensive one is actually earning its cost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


@dataclass
class TokenUsage:
    """What has been spent so far, in tokens.

    Accumulated across every call in a request, including repairs, so the
    true cost of a generation is visible rather than just the cost of its
    final successful attempt.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    calls: int = 0

    def add(self, other: TokenUsage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cached_tokens += other.cached_tokens
        self.calls += other.calls


@dataclass
class ProviderResponse:
    """One reply from a model, normalised."""

    parsed: BaseModel | None
    usage: TokenUsage = field(default_factory=TokenUsage)
    stop_reason: str | None = None
    """Why generation ended. Mostly useful when `parsed` is None: hitting an
    output limit and being refused look identical otherwise."""


@runtime_checkable
class ModelProvider(Protocol):
    """Anything that can turn a conversation into a structured object."""

    name: str
    """Human-readable, for logs and for telling the user who answered."""

    model: str

    def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        schema: type[BaseModel],
    ) -> ProviderResponse:
        """Answer the conversation, shaped to fit `schema`.

        `messages` uses the Anthropic convention — a list of
        {"role": "user"|"assistant", "content": str} — because it was first
        and it is the clearest. Providers that expect something else translate
        internally rather than pushing that detail upward.
        """
        ...

    def price(self, usage: TokenUsage) -> float:
        """What that usage costs in US dollars. Zero for free tiers."""
        ...


def messages_to_text(messages: list[dict[str, Any]]) -> str:
    """Flatten a conversation into one string.

    A fallback for providers with no multi-turn structured-output support.
    Lossy, so it is only used where there is no alternative.
    """
    parts = []
    for message in messages:
        speaker = "User" if message["role"] == "user" else "You previously wrote"
        parts.append(f"{speaker}:\n{message['content']}")
    return "\n\n".join(parts)
