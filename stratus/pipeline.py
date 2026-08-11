"""The whole flow, from a sentence to running infrastructure.

Everything else in Stratus is a part. This is the order the parts go in:

    read what exists  ->  write configuration  ->  check it parses
     ->  work out what would change  ->  explain it  ->  ask
     ->  build it  ->  report what happened

The order matters more than any single step. Reading first is what stops
duplicates. Checking before planning keeps a broken configuration from
reaching Azure. Explaining before asking is what makes the answer consent
rather than a guess. Applying only the saved plan is what makes the thing
that runs the same as the thing that was approved.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from stratus.agent import GeneratedConfig, TerraformGenerator
from stratus.agent.prompts import DEFAULT_REGION
from stratus.azure import LiveAzureReader
from stratus.azure.state import StateStorage
from stratus.cost import Estimate, describe as describe_cost, estimate as estimate_cost
from stratus.explain import confirmation_is_valid, explain
from stratus.models import Plan, Snapshot
from stratus.policy import Review, describe_warnings, explain_block, review
from stratus.recovery import PartialBuild, assess, explain_partial, parse_choice
from stratus.terraform import TerraformError, TerraformRunner

WORKSPACE_ROOT = Path.home() / ".stratus" / "workspaces"
"""Where each set of infrastructure keeps its files.

Outside the project directory on purpose: these are the user's
infrastructure, not part of Stratus's source, and they must survive the
project being reinstalled or moved.
"""


@dataclass
class Outcome:
    """What happened, for the caller to report however it likes."""

    request: str
    config: GeneratedConfig | None = None
    plan: Plan | None = None
    approved: bool = False
    applied: bool = False
    cancelled_reason: str | None = None
    repairs_used: int = 0
    cost_usd: float = 0.0
    existing_before: Snapshot | None = None
    notes: list[str] = field(default_factory=list)

    partial: PartialBuild | None = None
    """Set when the build died partway and left resources behind."""

    recovery: str | None = None
    """What was done about that: 'finished', 'undone', 'finish failed', or
    'left as is'."""

    error: Exception | None = None
    """The failure itself, kept so the caller can show what the cloud said
    rather than only our interpretation of it."""

    review: Review | None = None
    """The safety review of the approved plan. Blocked plans never reach
    here — they are corrected before the user sees anything — so this holds
    warnings only."""

    cost: Estimate | None = None
    """What the plan would add to the monthly bill."""


class Stratus:
    """One workspace: one set of infrastructure, one state file."""

    def __init__(
        self,
        subscription_id: str,
        workspace: str = "default",
        provider=None,
        workspace_root: Path | None = None,
        region: str | None = None,
        *,
        reader=None,
        runner=None,
        generator=None,
        backend=None,
    ) -> None:
        """Build a workspace, or accept ready-made parts.

        The four keyword-only arguments exist for tests. Without them a test
        has to reach in and assign attributes after construction, which breaks
        silently every time a new one is added — and a test that breaks when
        you add a field is a test that stops protecting the thing it was
        written for.
        """
        self.subscription_id = subscription_id
        self.workspace = workspace
        self.region = region or os.getenv("STRATUS_REGION") or DEFAULT_REGION

        root = workspace_root or WORKSPACE_ROOT
        self.runner = runner or TerraformRunner(root / workspace)
        self.reader = reader or LiveAzureReader(subscription_id)
        self.generator = generator or TerraformGenerator(provider=provider)

        # One state file per workspace. Sharing one would make unrelated
        # requests block each other on the lock, and would let a mistake in
        # one damage another.
        self.backend = backend or StateStorage(subscription_id).config_for(
            f"{workspace}.tfstate"
        )

        # Filled in by _validate, which plans and reviews as part of deciding
        # whether a configuration is acceptable.
        self._last_plan: Plan | None = None
        self._last_review: Review | None = None

    def build(
        self,
        request: str,
        confirm: Callable[[str], str],
        on_progress: Callable[[str], None] = lambda _: None,
    ) -> Outcome:
        """Take a request all the way to running infrastructure.

        `confirm` is handed the approval text and returns whatever the user
        typed. It is a parameter rather than a built-in prompt so the same
        pipeline serves a terminal, a web UI, or a test — and so there is
        exactly one place where approval happens.
        """
        outcome = Outcome(request=request)

        on_progress("Looking at what you already have...")
        existing = self.reader.read()
        outcome.existing_before = existing

        on_progress("Working out what to build...")
        config = self.generator.generate(
            request, existing, validate=self._validate, region=self.region
        )
        outcome.config = config
        outcome.repairs_used = self.generator.repairs_used
        outcome.cost_usd = self.generator.cost

        # The plan and the safety review already happened inside _validate,
        # as part of deciding whether the configuration was acceptable at all.
        # Planning again here would be a second slow round trip to Azure for
        # an answer already held.
        plan = self._last_plan
        assert plan is not None
        outcome.plan = plan
        outcome.review = self._last_review

        if plan.is_empty:
            # Reading the account first is what makes this possible: the
            # request is already satisfied, so nothing is built and nothing
            # is duplicated.
            outcome.cancelled_reason = "nothing to do"
            return outcome

        # Warnings ride along with the approval question rather than being
        # printed earlier. They are things the user should weigh before
        # answering, and anything shown before the plan gets skimmed past.
        question = explain(plan)

        # Cost first, then warnings, then the plan. Money is the thing a
        # person on a free tier most needs to see, and the further down the
        # screen it sits the more likely it is skimmed.
        outcome.cost = estimate_cost(plan, region=self.region)
        cost_text = describe_cost(outcome.cost)
        warnings = describe_warnings(self._last_review) if self._last_review else ""

        for block in (warnings, cost_text):
            if block:
                question = f"{block}\n\n{question}"

        answer = confirm(question)
        if not confirmation_is_valid(plan, answer):
            outcome.cancelled_reason = "not approved"
            return outcome

        outcome.approved = True
        on_progress("Building it...")
        # Progress is streamed rather than collected. Terraform prints a line
        # every ten seconds while a resource is being created, and those lines
        # are the only way to tell slow progress from a stuck retry loop.
        try:
            self.runner.apply(on_line=_progress_filter(on_progress))
        except TerraformError as exc:
            # A build that dies partway leaves real resources behind. Raising
            # here would hand the user an error and abandon them holding
            # infrastructure they did not ask to keep, so instead work out
            # what survived and offer a way out.
            outcome.partial = assess(
                plan, self.runner.state_resources(), reason=str(exc)
            )
            outcome.error = exc

            if outcome.partial.is_clean_failure:
                outcome.cancelled_reason = "failed, nothing left behind"
                return outcome

            self._recover(outcome, confirm, on_progress)
            return outcome

        outcome.applied = True
        return outcome

    def _recover(
        self,
        outcome: Outcome,
        confirm: Callable[[str], str],
        on_progress: Callable[[str], None],
    ) -> None:
        """Offer to finish or undo a half-built set of infrastructure."""
        assert outcome.partial is not None
        choice = parse_choice(confirm(explain_partial(outcome.partial)))

        if choice == "finish":
            on_progress("Trying the rest again...")
            # Re-plan first. The world moved when the first attempt partly
            # succeeded, so the saved plan no longer describes reality — and
            # applying a stale plan is how you get duplicates.
            self.runner.plan()
            try:
                self.runner.apply(on_line=_progress_filter(on_progress))
                outcome.applied = True
                outcome.recovery = "finished"
            except TerraformError as exc:
                # Do not loop. A second identical failure means the cause is
                # not transient, and asking again just wears the user down.
                outcome.recovery = "finish failed"
                outcome.error = exc
            return

        if choice == "undo":
            on_progress("Removing what was made...")
            self.runner.destroy(on_line=_progress_filter(on_progress))
            outcome.recovery = "undone"
            return

        # Anything unrecognised leaves the half-built state alone. That is
        # recoverable; guessing could delete something they wanted to keep.
        outcome.recovery = "left as is"

    def destroy(
        self,
        confirm: Callable[[str], str],
        on_progress: Callable[[str], None] = lambda _: None,
    ) -> Outcome:
        """Tear down everything in this workspace."""
        outcome = Outcome(request=f"destroy everything in '{self.workspace}'")

        owned = self.runner.state_resources()
        if not owned:
            outcome.cancelled_reason = "nothing to destroy"
            return outcome

        listing = "\n".join(f"  - {address}" for address in owned)
        answer = confirm(
            f"!! THIS WILL DESTROY THINGS. Please read carefully. !!\n\n"
            f"Deleting all {len(owned)} things in '{self.workspace}':\n{listing}\n\n"
            "Anything stored in them will be lost, permanently.\n\n"
            "To go ahead, type exactly:  DELETE\nAnything else cancels."
        )
        if answer.strip() != "DELETE":
            outcome.cancelled_reason = "not approved"
            return outcome

        outcome.approved = True
        on_progress("Tearing it down...")
        self.runner.destroy(on_line=_progress_filter(on_progress))
        outcome.applied = True
        return outcome

    def _validate(self, files: dict[str, str]) -> None:
        """Decide whether a generated configuration is acceptable.

        Three gates, cheapest first: does it parse, what would it actually do,
        and is what it would do safe.

        Putting the safety review here rather than after the plan is what
        makes it self-correcting. This function is the generator's validation
        callback, so anything it rejects goes straight back to the model with
        the reason attached — a configuration that would expose data gets
        rewritten rather than shown to the user as a refusal.

        The backend is written here rather than by the model. It is the same
        for every request, the model has no business knowing where state
        lives, and a second backend block is a hard error.
        """
        self.runner.clear_config()
        self.runner.write_config("backend.tf", self.backend.to_hcl())
        for name, contents in files.items():
            self.runner.write_config(name, contents)

        self.runner.init()
        self.runner.validate()

        plan = self.runner.plan()
        self._last_plan = plan
        self._last_review = review(plan)

        if self._last_review.is_blocked:
            raise PolicyRefused(explain_block(self._last_review))


class PolicyRefused(RuntimeError):
    """The configuration would do something Stratus will not do.

    Raised from the validation callback so the generator treats it exactly
    like a syntax error: feed the reason back, ask for a correction, try
    again. There is deliberately no way for a user to override it — a safety
    gate with a bypass is a suggestion.
    """


def _progress_filter(on_progress: Callable[[str], None]) -> Callable[[str], None]:
    """Pass on the Terraform lines a person would want, and drop the rest.

    Terraform is chatty. Forwarding every line buries the useful ones —
    "Creating...", "Still creating... [1m0s elapsed]", "Creation complete" —
    under provider noise and blank separators. Those three are what tell a
    watcher the difference between working and wedged, so they are what gets
    through.
    """
    interesting = (
        "Creating...",
        "Still creating...",
        "Creation complete",
        "Destroying...",
        "Still destroying...",
        "Destruction complete",
        "Modifying...",
        "Modifications complete",
        "Error",
    )

    def forward(line: str) -> None:
        if any(marker in line for marker in interesting):
            on_progress(line.strip())

    return forward
