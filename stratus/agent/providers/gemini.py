"""Google Gemini, via the AI Studio free tier.

Chosen as the default because it needs no payment card and its free tier is
generous enough to build against all day. Quality on this particular job —
writing Terraform and explaining it plainly — is close enough to the paid
alternatives that the difference rarely shows.

The free tier is rate-limited per minute and per day. When those limits bite
the error says so clearly, which is handled below rather than left to surface
as an unexplained failure mid-build.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel

from stratus.agent.providers.base import ProviderResponse, TokenUsage

DEFAULT_MODEL = "gemini-flash-latest"
"""An alias that tracks whatever the current Flash model is.

Pinning a dated version — `gemini-2.5-flash`, say — looks more reproducible
and is worse in practice: Google retires older models for new accounts, and
the request then fails with a 404 that reads like the key is broken. This
project is meant to still run when someone clones it in six months, and an
alias is what makes that true.

Flash rather than Pro: faster, and its free-tier allowance is far larger. For
a few dozen lines of Terraform the prompt is the bottleneck, not the model.

Override with GEMINI_MODEL to compare against something else.
"""


class RateLimited(RuntimeError):
    """The free tier's request allowance is exhausted."""


class GeminiProvider:
    """Talks to Gemini and returns a validated object."""

    name = "Google Gemini"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model or os.getenv("GEMINI_MODEL") or DEFAULT_MODEL

        if client is not None:
            self._client = client
            return

        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError(
                "No Gemini API key found.\n\n"
                "Get one free at https://aistudio.google.com/apikey — it takes "
                "about two minutes and needs no payment card.\n"
                "Then add it to your .env file:\n\n"
                "    GEMINI_API_KEY=your-key-here"
            )

        from google import genai

        self._client = genai.Client(api_key=key)

    def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        schema: type[BaseModel],
    ) -> ProviderResponse:
        from google.genai import types

        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=[_to_gemini(m) for m in messages],
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    # Gemini accepts a Pydantic class directly and returns an
                    # instance of it, so there is no hand-written JSON schema
                    # to keep in step with the model definition.
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
        except Exception as exc:  # noqa: BLE001 - re-raised with better context
            raise self._explain(exc) from exc

        return ProviderResponse(
            parsed=_parsed(response, schema),
            usage=_usage(response),
            stop_reason=_stop_reason(response),
        )

    def price(self, usage: TokenUsage) -> float:
        """Zero on the free tier.

        Deliberately not an estimate of what it *would* cost on a paid tier:
        showing a number implies money is moving, and none is.
        """
        return 0.0

    def available_models(self) -> list[str]:
        """Model names this key may actually use.

        Which models a key can reach depends on when the account was created,
        so this can only be answered by asking.
        """
        names = []
        for model in self._client.models.list():
            if "generateContent" in (getattr(model, "supported_actions", None) or []):
                names.append(model.name.removeprefix("models/"))
        return names

    def _explain(self, exc: Exception) -> Exception:
        """Turn Gemini's less helpful errors into actionable ones."""
        text = str(exc)

        if "429" in text or "RESOURCE_EXHAUSTED" in text:
            return RateLimited(
                f"{self.name} free-tier limit reached.\n\n"
                "Allowances reset per minute and per day. Wait a minute and "
                "retry, or switch provider for now:\n"
                "    STRATUS_MODEL_PROVIDER=anthropic"
            )

        if "404" in text and "NOT_FOUND" in text:
            # Google retires models for new accounts, and the resulting 404
            # reads like a broken key. Say what is actually usable.
            try:
                usable = ", ".join(self.available_models()[:8])
            except Exception:  # noqa: BLE001 - best effort inside an error path
                usable = "(could not list them)"
            return RuntimeError(
                f"Model {self.model!r} is not available to this API key.\n\n"
                "Google retires models for newly created accounts, so a name "
                "from a tutorial may no longer work.\n\n"
                f"Available to you: {usable}\n\n"
                "Set GEMINI_MODEL in .env to pick one."
            )

        return exc


def _to_gemini(message: dict[str, Any]) -> dict[str, Any]:
    """Translate one message into Gemini's shape.

    Gemini calls the assistant "model"; the rest of Stratus uses "assistant".
    The mapping lives here so nothing above this file has to know.
    """
    role = "model" if message["role"] == "assistant" else "user"
    return {"role": role, "parts": [{"text": message["content"]}]}


def _parsed(response: Any, schema: type[BaseModel]) -> BaseModel | None:
    """Pull the structured object out of a response.

    `.parsed` is populated when the reply matched the schema. When the model
    stops early — hitting an output limit mid-JSON, most often — it is None
    and `.text` holds a truncated fragment. Falling back to parsing that
    fragment would produce a half-built configuration, which is worse than
    no configuration at all, so it is not attempted.
    """
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, schema):
        return parsed
    return None


def _usage(response: Any) -> TokenUsage:
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return TokenUsage(calls=1)
    return TokenUsage(
        input_tokens=getattr(meta, "prompt_token_count", 0) or 0,
        output_tokens=getattr(meta, "candidates_token_count", 0) or 0,
        cached_tokens=getattr(meta, "cached_content_token_count", 0) or 0,
        calls=1,
    )


def _stop_reason(response: Any) -> str | None:
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return None
    reason = getattr(candidates[0], "finish_reason", None)
    return str(reason) if reason is not None else None
