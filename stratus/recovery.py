"""What to do when a build stops halfway.

A build that fails partway is the worst state infrastructure can be in.
Some things exist and some do not; the ones that exist are usually useless on
their own and are usually costing money; and the person who asked for a
website has no idea which of those two things is true.

Most tools stop at printing the error. That leaves the user to work out what
survived, whether it is safe, and how to clean it up — using the very tool
that just failed them.

Stratus is expected to know. It planned the work, so it knows what was
supposed to exist; Terraform's record says what actually does. The difference
between those two lists is the answer, and it can be worked out without
asking the cloud anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from stratus.explain import describe, is_supporting
from stratus.models import Action, Plan


@dataclass
class PartialBuild:
    """The gap between what was promised and what exists."""

    created: list[str] = field(default_factory=list)
    """Terraform addresses that now exist and are Stratus's responsibility."""

    missing: list[str] = field(default_factory=list)
    """Addresses that were planned but never made."""

    failed_at: str | None = None
    """The address the build died on, when it can be identified. The user's
    first question is always "how far did it get", and this answers it more
    precisely than two lists."""

    reason: str = ""
    """What the cloud said, kept verbatim."""

    @property
    def is_partial(self) -> bool:
        """Whether anything at all survived.

        A build that failed before creating anything needs no recovery — it
        just needs retrying. Only a genuinely half-built state does.
        """
        return bool(self.created) and bool(self.missing)

    @property
    def is_clean_failure(self) -> bool:
        """Nothing was created, so nothing needs cleaning up."""
        return not self.created


def assess(plan: Plan, state_addresses: list[str], reason: str = "") -> PartialBuild:
    """Work out how far a failed build got.

    Compares what the plan intended to create against what Terraform's record
    now contains. No cloud calls: the state file was updated as each resource
    succeeded, so it already holds the answer.
    """
    intended = [c.address for c in plan.of(Action.CREATE, Action.REPLACE)]
    owned = set(state_addresses)

    created = [address for address in intended if address in owned]
    missing = [address for address in intended if address not in owned]

    return PartialBuild(
        created=created,
        missing=missing,
        # The first thing that did not get made is where it stopped. Ordering
        # comes from the plan, which follows dependency order, so this is the
        # resource the failure actually landed on.
        failed_at=missing[0] if missing else None,
        reason=reason,
    )


def _friendly(address: str) -> str:
    """Turn a Terraform address into words. 'azurerm_storage_account.x' ->
    'place to keep files'."""
    type_ = address.split(".")[0]
    return describe(type_)


def _describe_all(addresses: list[str]) -> list[str]:
    """Name the real things, count the plumbing."""
    named = []
    supporting = 0
    for address in addresses:
        if is_supporting(address.split(".")[0]):
            supporting += 1
        else:
            named.append(f"  - {_friendly(address)}")
    if supporting:
        thing = "supporting piece" if supporting == 1 else "supporting pieces"
        named.append(f"  - {supporting} {thing}")
    return named


def explain_partial(partial: PartialBuild) -> str:
    """Describe a half-finished build, and what can be done about it."""
    if partial.is_clean_failure:
        return (
            "The build failed before anything was created, so nothing is "
            "left behind and nothing is costing you money.\n\n"
            f"What went wrong:\n{partial.reason.strip()[:800]}"
        )

    lines = ["The build stopped partway through.", ""]

    lines.append(f"Made before it stopped ({len(partial.created)}):")
    lines.extend(_describe_all(partial.created))
    lines.append("")

    if partial.missing:
        lines.append(f"Never made ({len(partial.missing)}):")
        lines.extend(_describe_all(partial.missing))
        lines.append("")

    # The part people actually need to hear. Half-built infrastructure is
    # usually unusable and always still billable, and both facts are easy to
    # miss when you are reading an error message.
    lines.append(
        "What exists is real and may be costing you money, but on its own it "
        "probably does not do anything useful."
    )
    lines.append("")

    if partial.reason:
        lines.append(f"Why it stopped:\n{partial.reason.strip()[:600]}")
        lines.append("")

    lines.append("Two ways out:")
    lines.append(
        "  finish  - try again for the parts that are missing. Sensible if "
        "the cause was temporary."
    )
    lines.append(
        "  undo    - remove what was made and return to where you started. "
        "Sensible if it cannot succeed."
    )
    lines.append("")
    lines.append("Which?  [finish / undo]")

    return "\n".join(lines)


def parse_choice(answer: str) -> str | None:
    """Read a recovery answer. Returns 'finish', 'undo', or None.

    Deliberately strict. An unrecognised answer leaves the half-built state
    exactly as it is, which is recoverable; guessing at what someone meant
    could delete infrastructure they wanted to keep.
    """
    cleaned = answer.strip().lower()
    if cleaned in {"finish", "f", "retry", "continue"}:
        return "finish"
    if cleaned in {"undo", "u", "rollback", "revert"}:
        return "undo"
    return None
