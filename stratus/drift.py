"""Noticing when the cloud stopped matching the record.

Infrastructure changes behind your back. Someone opens the portal to fix
something urgently, a script runs, a colleague tidies up. The record of what
should exist and the reality of what does quietly diverge, and nobody finds
out until the next change goes wrong in a way nobody can explain.

There are two questions here, and they need different methods.

*Did something we manage change?* Terraform already answers this: plan the
unchanged configuration against the real cloud, and anything it proposes is
drift by definition — the configuration did not move, so the cloud did.
Reimplementing that comparison would mean rebuilding Terraform's per-resource
knowledge of which fields are meaningful, and getting it subtly wrong.

*Did something appear that we do not manage?* Terraform cannot answer that,
because it only looks at resources it knows about. Comparing two readings of
the account does.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from stratus.explain import describe
from stratus.models import Action, Plan, Resource, Snapshot


@dataclass
class DriftItem:
    address: str
    kind: str
    """One of: 'vanished', 'changed', 'rebuilt'."""
    resource_type: str
    name: str


@dataclass
class Drift:
    vanished: list[DriftItem] = field(default_factory=list)
    """We believe these exist. The cloud does not have them."""

    changed: list[DriftItem] = field(default_factory=list)
    """Settings differ from what was agreed."""

    appeared: list[Resource] = field(default_factory=list)
    """In the account, created by someone other than Stratus."""

    @property
    def has_drift(self) -> bool:
        """Whether anything we manage has moved.

        Deliberately excludes `appeared`. Someone else creating their own
        resources is not drift — it is a colleague doing their job, and
        reporting it as a problem would train people to ignore the check.
        """
        return bool(self.vanished or self.changed)

    @property
    def is_clean(self) -> bool:
        return not self.has_drift and not self.appeared


def from_plan(plan: Plan) -> Drift:
    """Read drift out of a plan of unchanged configuration.

    The configuration did not move, so anything Terraform now proposes is a
    difference the cloud introduced:

      create   we expect it; the cloud does not have it. Someone deleted it.
      update   it exists, with different settings than agreed.
      replace  it changed in a way that cannot be adjusted in place.

    A delete would mean the configuration asked for its removal, which is an
    intended change rather than drift, so it is not counted.
    """
    drift = Drift()

    for change in plan.changes:
        item = DriftItem(
            address=change.address,
            kind="",
            resource_type=change.type,
            name=change.name,
        )
        if change.action is Action.CREATE:
            item.kind = "vanished"
            drift.vanished.append(item)
        elif change.action is Action.UPDATE:
            item.kind = "changed"
            drift.changed.append(item)
        elif change.action is Action.REPLACE:
            item.kind = "rebuilt"
            drift.changed.append(item)

    return drift


def unmanaged(snapshot: Snapshot) -> list[Resource]:
    """Resources in the account that Stratus did not create."""
    return [r for r in snapshot.resources if not r.is_stratus_managed()]


def compare(before: Snapshot, after: Snapshot) -> tuple[list[Resource], list[Resource]]:
    """What appeared and what disappeared between two readings.

    Used for history rather than for the live check: two readings taken
    minutes apart say little, but two taken a week apart say a lot.
    """
    was = before.by_id()
    now = after.by_id()
    appeared = [r for rid, r in now.items() if rid not in was]
    disappeared = [r for rid, r in was.items() if rid not in now]
    return appeared, disappeared


def explain_drift(drift: Drift) -> str:
    """Describe drift for a person."""
    if drift.is_clean:
        return "Everything matches. Nothing has changed outside of me."

    lines: list[str] = []

    if drift.vanished:
        count = len(drift.vanished)
        lines.append(
            f"{count} {'thing has' if count == 1 else 'things have'} been "
            "deleted outside of me:"
        )
        for item in drift.vanished:
            lines.append(f"  - {describe(item.resource_type)} ({item.name})")
        lines.append("")
        # The consequence, not just the fact. Anything depending on a deleted
        # resource is already broken, whether or not anyone has noticed.
        lines.append(
            "Anything that relied on these is already broken. I can rebuild "
            "them, but whatever they contained is gone."
        )
        lines.append("")

    if drift.changed:
        count = len(drift.changed)
        lines.append(
            f"{count} {'thing has' if count == 1 else 'things have'} been "
            "changed outside of me:"
        )
        for item in drift.changed:
            suffix = (
                "  <- putting this back means destroying and recreating it"
                if item.kind == "rebuilt"
                else ""
            )
            lines.append(f"  - {describe(item.resource_type)} ({item.name}){suffix}")
        lines.append("")
        lines.append(
            "Someone changed these by hand. That is not automatically wrong — "
            "but the next change I make will undo it, because I work from the "
            "agreed configuration."
        )
        lines.append("")

    if drift.appeared:
        count = len(drift.appeared)
        lines.append(
            f"{count} {'thing' if count == 1 else 'things'} in this account "
            "did not come from me:"
        )
        for resource in drift.appeared[:10]:
            lines.append(f"  - {resource.name}")
        if len(drift.appeared) > 10:
            lines.append(f"  - and {len(drift.appeared) - 10} more")
        lines.append("")
        lines.append("I will leave these alone.")
        lines.append("")

    if drift.has_drift:
        lines.append(
            "To put things back the way they were agreed, run a build again — "
            "you will be shown exactly what that would change before anything "
            "happens."
        )

    return "\n".join(lines).rstrip()
