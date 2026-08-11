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

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from stratus.agent import GeneratedConfig, TerraformGenerator
from stratus.azure import LiveAzureReader
from stratus.azure.state import StateStorage
from stratus.explain import confirmation_is_valid, explain
from stratus.models import Plan, Snapshot
from stratus.terraform import TerraformRunner

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


class Stratus:
    """One workspace: one set of infrastructure, one state file."""

    def __init__(
        self,
        subscription_id: str,
        workspace: str = "default",
        provider=None,
        workspace_root: Path | None = None,
    ) -> None:
        self.subscription_id = subscription_id
        self.workspace = workspace

        root = workspace_root or WORKSPACE_ROOT
        self.runner = TerraformRunner(root / workspace)
        self.reader = LiveAzureReader(subscription_id)
        self.generator = TerraformGenerator(provider=provider)

        # One state file per workspace. Sharing one would make unrelated
        # requests block each other on the lock, and would let a mistake in
        # one damage another.
        self.backend = StateStorage(subscription_id).config_for(f"{workspace}.tfstate")

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
        config = self.generator.generate(request, existing, validate=self._validate)
        outcome.config = config
        outcome.repairs_used = self.generator.repairs_used
        outcome.cost_usd = self.generator.cost

        on_progress("Checking what that would change...")
        plan = self.runner.plan()
        outcome.plan = plan

        if plan.is_empty:
            # Reading the account first is what makes this possible: the
            # request is already satisfied, so nothing is built and nothing
            # is duplicated.
            outcome.cancelled_reason = "nothing to do"
            return outcome

        answer = confirm(explain(plan))
        if not confirmation_is_valid(plan, answer):
            outcome.cancelled_reason = "not approved"
            return outcome

        outcome.approved = True
        on_progress("Building it...")
        self.runner.apply()
        outcome.applied = True

        return outcome

    def destroy(self, confirm: Callable[[str], str]) -> Outcome:
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
        self.runner.destroy()
        outcome.applied = True
        return outcome

    def _validate(self, files: dict[str, str]) -> None:
        """Write the generated configuration out and check Terraform accepts it.

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
