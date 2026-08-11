"""Turning a plain-English request into Terraform configuration.

This is the only part of Stratus that calls a language model. Everything
else — reading the account, running Terraform, deciding what is destructive,
summarising a plan — is ordinary code, because those jobs have exactly one
correct answer and code produces it instantly and for free.

Writing infrastructure configuration from an ambiguous sentence is not that
kind of job, so it is the one that gets a model.

Which model is a configuration choice. Nothing in this file knows or cares.
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, Field

from stratus.agent.prompts import SYSTEM_PROMPT, build_repair_message, build_user_message
from stratus.agent.providers import ModelProvider, TokenUsage, get_provider
from stratus.models import Snapshot

DEFAULT_REPAIR_ATTEMPTS = 2
"""How many times to hand a validation error back and ask for a fix.

Two is deliberate. The first repair fixes most genuine slips. If a second
still fails, the model is usually looping rather than converging, and further
attempts only spend time and money reproducing the same error.
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


class GenerationFailed(RuntimeError):
    """The model could not produce configuration Terraform would accept."""


class TerraformGenerator:
    """Writes Terraform configuration, and fixes it when Terraform objects."""

    def __init__(
        self,
        provider: ModelProvider | None = None,
        repair_attempts: int = DEFAULT_REPAIR_ATTEMPTS,
    ) -> None:
        self.provider = provider or get_provider()
        self.repair_attempts = repair_attempts
        self.usage = TokenUsage()

        self.repairs_used = 0
        """Repairs needed on the most recent generation.

        Worth recording rather than discarding: it is the clearest single
        measure of how well a given model handles this task, and it makes
        comparing providers a matter of reading a number instead of an
        impression.
        """

    @property
    def cost(self) -> float:
        """What has been spent so far, in US dollars. Zero on a free tier."""
        return self.provider.price(self.usage)

    def generate(
        self,
        request: str,
        existing: Snapshot,
        validate: Callable[[dict[str, str]], Any] | None = None,
    ) -> GeneratedConfig:
        """Produce configuration for a request.

        `validate` takes {filename: contents} and should raise an exception
        whose message explains the problem. Terraform's own `validate` is the
        intended one; keeping it as a parameter means the loop can be tested
        without Terraform, and means a policy check can slot in at exactly
        this point later.
        """
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": build_user_message(request, existing)}
        ]

        self.repairs_used = 0
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

                self.repairs_used += 1
                # Keep the rejected attempt in the conversation. The model
                # needs to see what it wrote in order to correct it, and
                # dropping it makes the same mistake likely again.
                messages.append({"role": "assistant", "content": _describe(config)})
                messages.append({"role": "user", "content": build_repair_message(last_error)})

        raise GenerationFailed(
            f"{self.provider.name} could not produce configuration Terraform "
            f"would accept, after {self.repair_attempts + 1} attempts.\n\n"
            f"Last error:\n{last_error}"
        )

    def _ask(self, messages: list[dict[str, Any]]) -> GeneratedConfig:
        response = self.provider.complete(SYSTEM_PROMPT, messages, GeneratedConfig)
        self.usage.add(response.usage)

        if response.parsed is None:
            raise GenerationFailed(
                f"{self.provider.name} did not return usable configuration "
                f"(stop reason: {response.stop_reason})."
            )
        if not isinstance(response.parsed, GeneratedConfig):
            raise GenerationFailed(
                f"{self.provider.name} returned {type(response.parsed).__name__}, "
                "not a configuration."
            )
        return response.parsed


def _describe(config: GeneratedConfig) -> str:
    """Render a previous attempt back into the conversation."""
    return "\n\n".join(f"--- {f.filename} ---\n{f.contents}" for f in config.files)
