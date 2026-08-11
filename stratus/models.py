"""The shapes of things Stratus knows about.

Everything the agent understands about your cloud passes through these types.
Keeping them in one small file means there is exactly one answer to "what does
Stratus think a resource is".
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(UTC)


class Origin(StrEnum):
    """Where a resource came from, from Stratus's point of view.

    This distinction is load-bearing. Stratus is allowed to modify and delete
    things it created; it must be far more cautious with things that were
    already in the account before it arrived, because a human put them there
    for a reason Stratus does not know.
    """

    MANAGED = "managed"
    """Stratus created this and is responsible for it."""

    DISCOVERED = "discovered"
    """This already existed. Stratus can read it, but must not assume it is
    safe to change or delete."""


class Resource(BaseModel):
    """One thing that exists in a cloud account.

    A virtual machine, a database, a network, a storage account — from
    Stratus's perspective they are all the same shape. The parts that differ
    between resource types live in `properties`.
    """

    # --- Identity -----------------------------------------------------------
    id: str
    """The cloud provider's unique identifier. On Azure this is a path, e.g.
    /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Storage/
    storageAccounts/mystorage — globally unique and stable for the life of
    the resource."""

    name: str
    """The short human-facing name, e.g. "mystorage"."""

    type: str
    """The provider's type string, e.g. "Microsoft.Storage/storageAccounts".
    Kept verbatim rather than mapped to our own vocabulary: the moment we
    invent our own names we have to maintain a translation table for every
    Azure service, and it will always be out of date."""

    # --- Placement ----------------------------------------------------------
    location: str | None = None
    """Physical region, e.g. "westeurope". Some resources are global and have
    none."""

    resource_group: str | None = None
    """Azure groups resources into named buckets. Deleting a group deletes
    everything in it, which is exactly the kind of thing the safety checks in
    Phase 3 need to know about."""

    # --- Everything else ----------------------------------------------------
    tags: dict[str, str] = Field(default_factory=dict)
    """Free-form labels. Stratus writes its own marker tag here so it can
    recognise its work on a later run."""

    properties: dict[str, Any] = Field(default_factory=dict)
    """Type-specific settings, kept as raw JSON on purpose.

    Azure has hundreds of resource types and each one has a completely
    different settings shape. Defining a Python class per type would mean
    writing and maintaining hundreds of classes that break every time
    Microsoft ships a change. Instead we keep the handful of fields that are
    common to everything as real typed fields above, and let the rest ride
    along untyped. Code that cares about a specific type reads what it needs
    out of here."""

    # --- Stratus's own bookkeeping ------------------------------------------
    origin: Origin = Origin.DISCOVERED
    """Defaults to DISCOVERED, which is the cautious answer. A resource is
    only MANAGED if Stratus has positive evidence it created it."""

    first_seen_at: datetime = Field(default_factory=_now)
    last_seen_at: datetime = Field(default_factory=_now)

    def is_stratus_managed(self) -> bool:
        return self.origin is Origin.MANAGED


class Action(StrEnum):
    """What is about to happen to one resource.

    These mirror Terraform's own vocabulary, because inventing our own would
    mean a translation layer that can silently disagree with what actually
    runs. The user never sees these strings — they get English, built from
    them.
    """

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"

    REPLACE = "replace"
    """Delete and recreate. Terraform reports this as a delete plus a create,
    but they are one indivisible event and must be shown to the user as one:
    "replace" means downtime, and anything stored on the old resource is gone.
    Presenting it as two separate lines hides that."""

    NO_OP = "no-op"
    """Already in the desired state. Nothing happens."""

    @property
    def is_destructive(self) -> bool:
        """Whether this action can lose data or cause an outage.

        This is the single most important question the safety layer asks, so
        it lives on the type itself rather than being re-derived by every
        caller that needs it.
        """
        return self in (Action.DELETE, Action.REPLACE)


class PlannedChange(BaseModel):
    """One resource that a plan intends to change."""

    address: str
    """Terraform's internal handle, e.g. "azurerm_storage_account.data".
    Used to correlate a plan with what actually happened afterwards."""

    type: str
    """Terraform's resource type, e.g. "azurerm_storage_account"."""

    name: str
    """The name given in the configuration."""

    action: Action

    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    """Settings before and after. `before` is None for a create, `after` is
    None for a delete."""


class Plan(BaseModel):
    """What Terraform intends to do, before anything has been done.

    This is the object the user approves or rejects. Everything shown to them
    at the approval step is derived from here, so it must be a complete and
    honest account — anything omitted here is a change that happens without
    consent.
    """

    changes: list[PlannedChange] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict, repr=False)
    """The full JSON Terraform produced. Kept so that anything we did not
    think to model is still available rather than discarded."""

    def of(self, *actions: Action) -> list[PlannedChange]:
        """Changes matching any of the given actions."""
        wanted = set(actions)
        return [c for c in self.changes if c.action in wanted]

    @property
    def destructive_changes(self) -> list[PlannedChange]:
        """Everything that deletes or replaces something.

        If this is non-empty the user must give explicit confirmation. That
        rule is enforced in the approval layer, not here.
        """
        return [c for c in self.changes if c.action.is_destructive]

    @property
    def is_destructive(self) -> bool:
        return bool(self.destructive_changes)

    @property
    def is_empty(self) -> bool:
        """True when nothing would change.

        This is the answer that makes asking twice safe: if the user requests
        something they already have, the plan comes back empty and Stratus can
        say "you already have this" instead of building a duplicate.
        """
        return all(c.action is Action.NO_OP for c in self.changes)


class Snapshot(BaseModel):
    """Everything found in one account at one moment in time.

    Stratus compares snapshots to answer "what changed?". That comparison is
    what makes drift detection possible later: if a resource is in yesterday's
    snapshot but not today's, someone deleted it outside of Stratus.
    """

    subscription_id: str
    """Which Azure subscription (billing account) this was read from."""

    taken_at: datetime = Field(default_factory=_now)
    resources: list[Resource] = Field(default_factory=list)

    def by_id(self) -> dict[str, Resource]:
        """Resources keyed by id, for cheap lookups when comparing snapshots."""
        return {r.id: r for r in self.resources}

    def count_by_type(self) -> dict[str, int]:
        """How many of each resource type — the basis of a human summary."""
        counts: dict[str, int] = {}
        for r in self.resources:
            counts[r.type] = counts.get(r.type, 0) + 1
        return counts

    def __len__(self) -> int:
        return len(self.resources)
