"""Turning a plain-English request into Terraform configuration.

This is the only place in Stratus that calls a language model. Everything
else — reading the account, running Terraform, deciding what is destructive,
summarising a plan — is ordinary code, because those jobs have exactly one
correct answer and code produces it instantly and for free.

Writing infrastructure configuration from an ambiguous sentence is not that
kind of job, so it is the one that gets a model.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from stratus.agent.prompts import SYSTEM_PROMPT, build_repair_message, build_user_message
from stratus.models import Snapshot

MODEL = "claude-opus-5"

MAX_TOKENS = 16000
"""Generous. Terraform configuration for a multi-resource request runs long,
and a truncated configuration fails in confusing ways much later."""

DEFAULT_REPAIR_ATTEMPTS = 2
"""How many times to hand a validation error back and ask for a fix.

Two is deliberate. The first repair fixes most genuine slips. If a second
still fails, the model is usually stuck in a loop rather than converging, and
further attempts just spend money to produce the same error.
"""


class GeneratedFile(BaseModel):
    filename: str = Field(description="File name, ending in .tf")
    contents: str = Field(description="Complete Terraform configuration")


class GeneratedConfig(BaseModel):
    """What the model produced, before Terraform has seen it."""

    files: list[GeneratedFile] = Field(
        description="Every file needed, complete. Never a fragment or a diff."
    )
    summary: str = Field(
        description="Two or three sentences for someone who has never used a "
        "cloud. No jargon, no product names, no Terraform vocabulary."
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Decisions taken that the person did not specify, in plain "
        "language.",
    )

    def as_dict(self) -> dict[str, str]:
        return {f.filename: f.contents for f in self.files}


class Usage(BaseModel):
    """What a request cost, so spend is visible rather than discovered later."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    calls: int = 0

    def add(self, usage: Any) -> None:
        self.calls += 1
        self.input_tokens += getattr(usage, "input_tokens", 0)
        self.output_tokens += getattr(usage, "output_tokens", 0)
        self.cached_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0

    @property
    def estimated_cost_usd(self) -> float:
        """Rough cost at Claude Opus 5 list prices ($5 / $25 per million).

        Cached input is billed at about a tenth of the normal rate, which is
        why the system prompt is held byte-identical between requests.
        """
        return (
            self.input_tokens * 5 / 1_000_000
            + self.cached_tokens * 0.5 / 1_000_000
            + self.output_tokens * 25 / 1_000_000
        )


class GenerationFailed(RuntimeError):
    """The model could not produce configuration Terraform would accept."""


class TerraformGenerator:
    """Writes Terraform configuration, and fixes it when Terraform objects."""

    def __init__(
        self,
        client: Any | None = None,
        model: str = MODEL,
        repair_attempts: int = DEFAULT_REPAIR_ATTEMPTS,
    ) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client = client
        self.model = model
        self.repair_attempts = repair_attempts
        self.usage = Usage()

    def generate(
        self,
        request: str,
        existing: Snapshot,
        validate: Any | None = None,
    ) -> GeneratedConfig:
        """Produce configuration for a request.

        `validate` is an optional callable taking {filename: contents}. It
        should raise an exception whose message explains the problem if the
        configuration is unacceptable. Terraform's own `validate` is the
        intended one, but keeping it as a parameter means this can be tested
        without Terraform, and means a policy check can be slotted in later
        at exactly the same point.
        """
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": build_user_message(request, existing)}
        ]

        last_error: str | None = None

        # One initial attempt, then up to repair_attempts corrections.
        for attempt in range(self.repair_attempts + 1):
            config = self._ask(messages)

            if validate is None:
                return config

            try:
                validate(config.as_dict())
                return config
            except Exception as exc:  # noqa: BLE001 - message is fed back to the model
                last_error = str(exc)
                if attempt == self.repair_attempts:
                    break
                # Keep the rejected attempt in the conversation. The model
                # needs to see what it wrote in order to correct it, and
                # dropping it makes the same mistake likely again.
                messages.append(
                    {"role": "assistant", "content": _describe(config)}
                )
                messages.append(
                    {"role": "user", "content": build_repair_message(last_error)}
                )

        raise GenerationFailed(
            f"Terraform rejected the configuration after "
            f"{self.repair_attempts + 1} attempts.\n\nLast error:\n{last_error}"
        )

    def _ask(self, messages: list[dict[str, Any]]) -> GeneratedConfig:
        response = self._client.messages.parse(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    # The system prompt never varies between requests, so it
                    # can be cached and served far more cheaply. Anything
                    # request-specific deliberately lives in the user turn to
                    # keep this prefix identical.
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=messages,
            output_format=GeneratedConfig,
        )
        self.usage.add(response.usage)

        if response.parsed_output is None:
            raise GenerationFailed(
                "The model did not return usable configuration "
                f"(stop reason: {response.stop_reason})."
            )
        return response.parsed_output


def _describe(config: GeneratedConfig) -> str:
    """Render a previous attempt back into the conversation."""
    parts = [f"--- {f.filename} ---\n{f.contents}" for f in config.files]
    return "\n\n".join(parts)
