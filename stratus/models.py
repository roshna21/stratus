"""The shapes of things Stratus knows about.

Everything the agent understands about your cloud passes through these types.
Keeping them in one small file means there is exactly one answer to "what does
Stratus think a resource is".
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Origin(str, Enum):
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
