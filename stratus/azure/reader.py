"""Reading what already exists in an Azure account.

This is deliberately the first thing Stratus can do. The agent must be able to
see reality before it is trusted to change it — nearly every dangerous mistake
in infrastructure automation comes from acting on a stale or absent picture of
what is already there.

Two implementations live here:

  LiveAzureReader  talks to a real Azure subscription.
  FakeAzureReader  returns canned data and needs no account, no network, and
                   no money. Every test and most development runs against it.
"""

from __future__ import annotations

from typing import Any, Iterable, Protocol

from stratus.models import Origin, Resource, Snapshot

STRATUS_TAG = "managed-by"
STRATUS_TAG_VALUE = "stratus"
"""The marker Stratus writes onto everything it creates.

Tags are the only durable place to record ownership that survives Stratus
being restarted, reinstalled, or pointed at the account from a different
machine. A local database can drift or be lost; the tag travels with the
resource.
"""


def _resource_group_from_id(resource_id: str) -> str | None:
    """Pull the resource group name out of an Azure resource id.

    Azure ids look like:
        /subscriptions/<sub>/resourceGroups/<rg>/providers/<type>/<name>

    The group is not returned as its own field by the list API, but it is
    always present in the id, so we parse it out rather than making an extra
    call per resource.
    """
    parts = resource_id.split("/")
    for i, part in enumerate(parts):
        if part.lower() == "resourcegroups" and i + 1 < len(parts):
            return parts[i + 1]
    return None


def _origin_from_tags(tags: dict[str, str] | None) -> Origin:
    """Decide whether Stratus created this, based on its marker tag."""
    if tags and tags.get(STRATUS_TAG) == STRATUS_TAG_VALUE:
        return Origin.MANAGED
    return Origin.DISCOVERED


class AzureReader(Protocol):
    """Anything that can tell Stratus what exists in a subscription.

    Declaring this as a Protocol rather than a base class means the fake and
    the real reader are interchangeable without either knowing about the
    other. Code that consumes a reader never needs to know which one it got.
    """

    def read(self) -> Snapshot: ...


class LiveAzureReader:
    """Reads a real Azure subscription.

    Authentication is handled by Azure's own DefaultAzureCredential, which
    tries several sources in order and picks the first that works — for local
    development that will be the session created by `az login`. Nothing here
    ever handles a password or key directly, and no credential is stored in
    this project.
    """

    def __init__(self, subscription_id: str, credential: Any | None = None) -> None:
        # Imported lazily so that the fake reader, the models, and the whole
        # test suite work on a machine where the Azure SDK is not installed.
        #
        # Note the import path. As of azure-mgmt-resource v26 the client lives
        # in the .resources subpackage; the older top-level
        # `from azure.mgmt.resource import ResourceManagementClient` that most
        # tutorials still show now fails with a confusing "unknown location"
        # error, because azure.mgmt.resource became a namespace package with
        # nothing re-exported from it.
        from azure.identity import DefaultAzureCredential
        from azure.mgmt.resource.resources import ResourceManagementClient

        self.subscription_id = subscription_id
        self._client = ResourceManagementClient(
            credential=credential or DefaultAzureCredential(),
            subscription_id=subscription_id,
        )

    def read(self) -> Snapshot:
        """List every resource in the subscription.

        Note: Azure's list endpoint returns identity and placement for each
        resource but not its full type-specific settings — fetching those
        needs one extra call per resource. That detail is not needed yet, so
        `properties` stays empty here rather than making hundreds of calls to
        populate a field nothing reads.
        """
        resources = [
            self._to_resource(item) for item in self._client.resources.list()
        ]
        return Snapshot(subscription_id=self.subscription_id, resources=resources)

    @staticmethod
    def _to_resource(item: Any) -> Resource:
        """Convert one Azure SDK object into our own Resource type.

        Everything from the SDK is translated at this boundary and nowhere
        else, so the rest of Stratus never touches an Azure-specific object.
        That keeps the option of supporting another cloud later open, and it
        makes the fake reader genuinely equivalent to the real one.
        """
        tags = dict(item.tags or {})
        return Resource(
            id=item.id,
            name=item.name,
            type=item.type,
            location=getattr(item, "location", None),
            resource_group=_resource_group_from_id(item.id),
            tags=tags,
            origin=_origin_from_tags(tags),
        )


class FakeAzureReader:
    """A stand-in account, for tests and for building without spending money.

    Every behaviour Stratus needs to handle can be represented here, including
    the awkward ones: a resource with no location, a resource Stratus itself
    created, and an empty account.
    """

    def __init__(
        self,
        resources: Iterable[Resource] | None = None,
        subscription_id: str = "00000000-0000-0000-0000-000000000000",
    ) -> None:
        self.subscription_id = subscription_id
        self._resources = list(resources) if resources is not None else _example_account()

    def read(self) -> Snapshot:
        return Snapshot(
            subscription_id=self.subscription_id,
            resources=list(self._resources),
        )


def _make(
    name: str,
    type_: str,
    *,
    group: str = "demo-rg",
    location: str | None = "westeurope",
    tags: dict[str, str] | None = None,
    subscription: str = "00000000-0000-0000-0000-000000000000",
) -> Resource:
    """Build a Resource with a realistically-shaped Azure id."""
    resource_id = (
        f"/subscriptions/{subscription}/resourceGroups/{group}"
        f"/providers/{type_}/{name}"
    )
    tags = tags or {}
    return Resource(
        id=resource_id,
        name=name,
        type=type_,
        location=location,
        resource_group=group,
        tags=tags,
        origin=_origin_from_tags(tags),
    )


def _example_account() -> list[Resource]:
    """A small account with one of each interesting case."""
    return [
        # Something a human made before Stratus existed.
        _make("companydata", "Microsoft.Storage/storageAccounts"),
        # Something Stratus created and is therefore responsible for.
        _make(
            "stratus-web-a41f",
            "Microsoft.Web/sites",
            tags={STRATUS_TAG: STRATUS_TAG_VALUE},
        ),
        # A second resource in the same group, to prove grouping works.
        _make("stratus-plan-a41f", "Microsoft.Web/serverfarms",
              tags={STRATUS_TAG: STRATUS_TAG_VALUE}),
        # A global resource, which has no location at all.
        _make("demo-dns", "Microsoft.Network/dnsZones", location=None),
        # A resource in a different group, to prove we read across groups.
        _make("legacy-db", "Microsoft.DBforPostgreSQL/flexibleServers",
              group="old-rg", location="northeurope"),
    ]
