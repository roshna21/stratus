"""Tests for the generation and repair loop.

A stub provider stands in for a real model, so these run offline and free.
What is being tested is the loop — how many times it asks, what it feeds
back, when it gives up — not the model's writing ability, which no unit test
could judge anyway.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from stratus.agent.generator import (
    GeneratedConfig,
    GeneratedFile,
    GenerationFailed,
    TerraformGenerator,
)
from stratus.agent.providers import ModelProvider, ProviderResponse, TokenUsage
from stratus.models import Snapshot


def _config(contents: str = "resource {}", summary: str = "A thing.") -> GeneratedConfig:
    return GeneratedConfig(
        files=[GeneratedFile(filename="main.tf", contents=contents)],
        summary=summary,
        assumptions=[],
    )


class StubProvider:
    """Returns a scripted sequence of replies and records what it was sent."""

    name = "Stub"
    model = "stub-1"

    def __init__(self, replies: list[GeneratedConfig | ProviderResponse]):
        self._replies = list(replies)
        self.calls: list[dict] = []

    def complete(self, system, messages, schema) -> ProviderResponse:
        self.calls.append({"system": system, "messages": list(messages), "schema": schema})
        if not self._replies:
            raise AssertionError("asked more times than the test scripted")

        reply = self._replies.pop(0)
        if isinstance(reply, ProviderResponse):
            return reply
        return ProviderResponse(
            parsed=reply,
            usage=TokenUsage(input_tokens=1000, output_tokens=500, calls=1),
            stop_reason="end_turn",
        )

    def price(self, usage: TokenUsage) -> float:
        return 0.0


EMPTY = Snapshot(subscription_id="test")


def _always_fails(_files):
    raise RuntimeError("still broken")


class TestProviderBoundary:
    def test_the_stub_satisfies_the_interface(self):
        # Guards the boundary itself: if ModelProvider grows a method, this
        # fails rather than every provider silently drifting out of step.
        assert isinstance(StubProvider([]), ModelProvider)

    def test_the_generator_never_names_a_vendor(self):
        # The whole point of the boundary. If this file ever has to import an
        # SDK to test the loop, the abstraction has leaked.
        import stratus.agent.generator as module

        source = module.__doc__ or ""
        assert "anthropic" not in source.lower()
        assert "gemini" not in source.lower()


class TestHappyPath:
    def test_returns_configuration(self):
        gen = TerraformGenerator(provider=StubProvider([_config()]))
        result = gen.generate("a website", EMPTY)
        assert result.summary == "A thing."
        assert result.files[0].filename == "main.tf"

    def test_asks_once_when_nothing_needs_fixing(self):
        provider = StubProvider([_config()])
        TerraformGenerator(provider=provider).generate(
            "a website", EMPTY, validate=lambda f: None
        )
        assert len(provider.calls) == 1

    def test_skips_validation_when_none_is_given(self):
        gen = TerraformGenerator(provider=StubProvider([_config()]))
        assert gen.generate("a website", EMPTY) is not None

    def test_exposes_files_as_a_mapping(self):
        assert _config("body").as_dict() == {"main.tf": "body"}

    def test_reports_no_repairs_when_none_were_needed(self):
        gen = TerraformGenerator(provider=StubProvider([_config()]))
        gen.generate("x", EMPTY, validate=lambda f: None)
        assert gen.repairs_used == 0


class TestRepairLoop:
    def test_repairs_after_one_rejection(self):
        provider = StubProvider([_config("broken"), _config("fixed")])
        seen = []

        def validate(files):
            seen.append(files["main.tf"])
            if files["main.tf"] == "broken":
                raise RuntimeError("Error: Argument definition required on line 7")

        result = TerraformGenerator(provider=provider).generate(
            "a website", EMPTY, validate=validate
        )

        assert result.files[0].contents == "fixed"
        assert seen == ["broken", "fixed"]
        assert len(provider.calls) == 2

    def test_counts_the_repairs_it_needed(self):
        # The clearest single measure of how well a model handles this task,
        # and what makes comparing providers a number rather than a feeling.
        provider = StubProvider([_config("broken"), _config("fixed")])

        def validate(files):
            if files["main.tf"] == "broken":
                raise RuntimeError("boom")

        gen = TerraformGenerator(provider=provider)
        gen.generate("x", EMPTY, validate=validate)
        assert gen.repairs_used == 1

    def test_shows_the_model_its_own_broken_attempt(self):
        # Without the rejected attempt in the conversation the model is
        # correcting something it cannot see, and tends to reproduce the
        # same mistake.
        provider = StubProvider([_config("broken"), _config("fixed")])

        def validate(files):
            if files["main.tf"] == "broken":
                raise RuntimeError("boom")

        TerraformGenerator(provider=provider).generate("x", EMPTY, validate=validate)
        assert "broken" in str(provider.calls[1]["messages"])

    def test_passes_the_error_through_verbatim(self):
        # Terraform names the file, line and problem. Paraphrasing loses
        # exactly the detail that makes a fix possible.
        provider = StubProvider([_config("broken"), _config("fixed")])
        error = "Error: Unsupported argument on main.tf line 12"

        def validate(files):
            if files["main.tf"] == "broken":
                raise RuntimeError(error)

        TerraformGenerator(provider=provider).generate("x", EMPTY, validate=validate)
        assert error in str(provider.calls[1]["messages"])

    def test_gives_up_rather_than_looping_forever(self):
        provider = StubProvider([_config("bad")] * 3)
        gen = TerraformGenerator(provider=provider, repair_attempts=2)

        with pytest.raises(GenerationFailed, match="still broken"):
            gen.generate("x", EMPTY, validate=_always_fails)

        # One initial attempt plus two repairs, then it stops.
        assert len(provider.calls) == 3

    def test_respects_a_lower_repair_budget(self):
        provider = StubProvider([_config("bad")] * 2)
        gen = TerraformGenerator(provider=provider, repair_attempts=0)

        with pytest.raises(GenerationFailed):
            gen.generate("x", EMPTY, validate=_always_fails)
        assert len(provider.calls) == 1

    def test_the_failure_names_the_provider(self):
        # When a model cannot do the job, the user needs to know which one so
        # they can try another rather than assume Stratus is broken.
        gen = TerraformGenerator(provider=StubProvider([_config()] * 3))
        with pytest.raises(GenerationFailed, match="Stub"):
            gen.generate("x", EMPTY, validate=_always_fails)


class TestPromptConstruction:
    def test_request_specific_content_goes_in_the_user_turn(self):
        # Keeping the system prompt byte-identical between requests is what
        # allows a provider to cache it.
        provider = StubProvider([_config()])
        TerraformGenerator(provider=provider).generate("build me a blog", EMPTY)
        assert "blog" not in provider.calls[0]["system"]
        assert "blog" in str(provider.calls[0]["messages"])

    def test_the_schema_is_passed_to_the_provider(self):
        provider = StubProvider([_config()])
        TerraformGenerator(provider=provider).generate("x", EMPTY)
        assert provider.calls[0]["schema"] is GeneratedConfig


class TestUsageAndCost:
    def test_accumulates_across_repairs(self):
        provider = StubProvider([_config("broken"), _config("fixed")])

        def validate(files):
            if files["main.tf"] == "broken":
                raise RuntimeError("boom")

        gen = TerraformGenerator(provider=provider)
        gen.generate("x", EMPTY, validate=validate)

        assert gen.usage.calls == 2
        assert gen.usage.input_tokens == 2000
        assert gen.usage.output_tokens == 1000

    def test_cost_comes_from_the_provider(self):
        # A free tier reports zero rather than what it would have cost
        # elsewhere. Showing a number implies money moved.
        gen = TerraformGenerator(provider=StubProvider([_config()]))
        gen.generate("x", EMPTY)
        assert gen.cost == 0.0

    def test_token_usage_adds_up(self):
        total = TokenUsage()
        total.add(TokenUsage(input_tokens=10, output_tokens=5, calls=1))
        total.add(TokenUsage(input_tokens=20, cached_tokens=3, calls=1))
        assert (total.input_tokens, total.output_tokens, total.cached_tokens, total.calls) == (
            30,
            5,
            3,
            2,
        )


class TestFailureModes:
    def test_raises_when_the_model_returns_nothing_usable(self):
        provider = StubProvider(
            [ProviderResponse(parsed=None, usage=TokenUsage(calls=1), stop_reason="MAX_TOKENS")]
        )
        with pytest.raises(GenerationFailed, match="MAX_TOKENS"):
            TerraformGenerator(provider=provider).generate("x", EMPTY)

    def test_rejects_an_object_of_the_wrong_shape(self):
        class SomethingElse(BaseModel):
            value: int

        provider = StubProvider(
            [ProviderResponse(parsed=SomethingElse(value=1), usage=TokenUsage(calls=1))]
        )
        with pytest.raises(GenerationFailed, match="not a configuration"):
            TerraformGenerator(provider=provider).generate("x", EMPTY)
