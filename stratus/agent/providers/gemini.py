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

DEFAULT_MODEL = "gemini-2.5-flash"
"""Flash rather than Pro: faster, and its free-tier allowance is far larger.
For generating a few dozen lines of Terraform the extra capability of Pro is
not the bottleneck — the prompt is.
"""


class RateLimited(RuntimeError):
    """The free tier's request allowance is exhausted."""


class GeminiProvider:
    """Talks to Gemini and returns a validated object."""

    name = "Google Gemini"

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

        response = self._client.models.generate_content(
            model=self.model,
            contents=[_to_gemini(m) for m in messages],
            config=types.GenerateContentConfig(
                system_instruction=system,
                # Gemini accepts a Pydantic class directly and returns an
                # instance of it, so there is no hand-written JSON schema to
                # keep in step with the model definition.
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )

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
