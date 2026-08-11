"""Tests for the generation and repair loop.

A stub stands in for the Anthropic client, so these run offline and free.
What is being tested here is the loop — how many times it asks, what it feeds
back, when it gives up — not the model's writing ability, which no unit test
could check anyway.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from stratus.agent.generator import (
    GeneratedConfig,
    GeneratedFile,
    GenerationFailed,
    TerraformGenerator,
    Usage,
)
from stratus.models import Snapshot


def _config(contents: str = "resource {}", summary: str = "A thing.") -> GeneratedConfig:
    return GeneratedConfig(
        files=[GeneratedFile(filename="main.tf", contents=contents)],
        summary=summary,
        assumptions=[],
    )


class StubClient:
    """Returns a scripted sequence of responses and records what it was sent."""

    def __init__(self, responses: list[GeneratedConfig]):
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("asked more times than the test scripted")
        return SimpleNamespace(
            parsed_output=self._responses.pop(0),
            stop_reason="end_turn",
            usage=SimpleNamespace(
                input_tokens=1000, output_tokens=500, cache_read_input_tokens=0
            ),
        )


EMPTY = Snapshot(subscription_id="test")


class TestHappyPath:
    def test_returns_configuration(self):
        gen = TerraformGenerator(client=StubClient([_config()]))
        result = gen.generate("a website", EMPTY)
        assert result.summary == "A thing."
        assert result.files[0].filename == "main.tf"

    def test_asks_once_when_nothing_needs_fixing(self):
        client = StubClient([_config()])
        TerraformGenerator(client=client).generate("a website", EMPTY, validate=lambda f: None)
        assert len(client.calls) == 1

    def test_skips_validation_when_none_is_given(self):
        gen = TerraformGenerator(client=StubClient([_config()]))
        assert gen.generate("a website", EMPTY) is not None

    def test_exposes_files_as_a_mapping(self):
        assert _config("body").as_dict() == {"main.tf": "body"}


class TestRepairLoop:
    def test_repairs_after_one_rejection(self):
        client = StubClient([_config("broken"), _config("fixed")])
        attempts = []

        def validate(files):
            attempts.append(files["main.tf"])
            if files["main.tf"] == "broken":
                raise RuntimeError("Error: Argument definition required on line 7")

        result = TerraformGenerator(client=client).generate(
            "a website", EMPTY, validate=validate
        )

        assert result.files[0].contents == "fixed"
        assert attempts == ["broken", "fixed"]
        assert len(client.calls) == 2

    def test_shows_the_model_its_own_broken_attempt(self):
        # Without the rejected attempt in the conversation the model is
        # correcting something it cannot see, and tends to reproduce the
        # same mistake.
        client = StubClient([_config("broken"), _config("fixed")])

        def validate(files):
            if files["main.tf"] == "broken":
                raise RuntimeError("boom")

        TerraformGenerator(client=client).generate("x", EMPTY, validate=validate)

        second_call_messages = client.calls[1]["messages"]
        conversation = str(second_call_messages)
        assert "broken" in conversation

    def test_passes_the_error_through_verbatim(self):
        # Terraform names the file, line and problem. Paraphrasing loses
        # exactly the detail that makes a fix possible.
        client = StubClient([_config("broken"), _config("fixed")])
        error = "Error: Unsupported argument on main.tf line 12"

        def validate(files):
            if files["main.tf"] == "broken":
                raise RuntimeError(error)

        TerraformGenerator(client=client).generate("x", EMPTY, validate=validate)
        assert error in str(client.calls[1]["messages"])

    def test_gives_up_rather_than_looping_forever(self):
        client = StubClient([_config("bad")] * 3)

        def always_fails(files):
            raise RuntimeError("still broken")

        gen = TerraformGenerator(client=client, repair_attempts=2)
        with pytest.raises(GenerationFailed, match="still broken"):
            gen.generate("x", EMPTY, validate=always_fails)

        # One initial attempt plus two repairs, and then it stops.
        assert len(client.calls) == 3

    def test_respects_a_lower_repair_budget(self):
        client = StubClient([_config("bad")] * 2)
        gen = TerraformGenerator(client=client, repair_attempts=0)
        with pytest.raises(GenerationFailed):
            gen.generate("x", EMPTY, validate=lambda f: (_ for _ in ()).throw(RuntimeError("no")))
        assert len(client.calls) == 1


class TestPromptConstruction:
    def test_caches_the_system_prompt(self):
        # The system prompt is identical between requests, so caching it cuts
        # its cost by roughly ninety percent. Anything request-specific must
        # stay out of it or the cache is invalidated every time.
        client = StubClient([_config()])
        TerraformGenerator(client=client).generate("x", EMPTY)
        system = client.calls[0]["system"]
        assert system[0]["cache_control"] == {"type": "ephemeral"}

    def test_request_specific_content_goes_in_the_user_turn(self):
        client = StubClient([_config()])
        TerraformGenerator(client=client).generate("build me a blog", EMPTY)
        assert "blog" not in str(client.calls[0]["system"])
        assert "blog" in str(client.calls[0]["messages"])


class TestUsage:
    def test_accumulates_across_repairs(self):
        client = StubClient([_config("broken"), _config("fixed")])

        def validate(files):
            if files["main.tf"] == "broken":
                raise RuntimeError("boom")

        gen = TerraformGenerator(client=client)
        gen.generate("x", EMPTY, validate=validate)

        assert gen.usage.calls == 2
        assert gen.usage.input_tokens == 2000
        assert gen.usage.output_tokens == 1000

    def test_estimates_cost(self):
        usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000, calls=1)
        # $5 per million in, $25 per million out.
        assert usage.estimated_cost_usd == pytest.approx(30.0)

    def test_cached_input_is_cheaper(self):
        plain = Usage(input_tokens=1_000_000)
        cached = Usage(cached_tokens=1_000_000)
        assert cached.estimated_cost_usd < plain.estimated_cost_usd


class TestFailureModes:
    def test_raises_when_the_model_returns_nothing_usable(self):
        client = StubClient([])
        client._parse = lambda **kw: SimpleNamespace(
            parsed_output=None, stop_reason="max_tokens",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1, cache_read_input_tokens=0),
        )
        client.messages = SimpleNamespace(parse=client._parse)

        with pytest.raises(GenerationFailed, match="max_tokens"):
            TerraformGenerator(client=client).generate("x", EMPTY)
