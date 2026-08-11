"""Where Terraform's memory lives.

Terraform records everything it has built in a "state file". Lose that file
and Terraform forgets your infrastructure exists — while the real resources
carry on running and costing money, now unmanaged and invisible. Corrupt it,
or let two processes write it at once, and Terraform can duplicate or destroy
things.

So the state file cannot live on a laptop. It belongs in cloud storage, where
it is durable, backed up, and — crucially — *lockable*, so only one operation
can modify it at a time.

There is a chicken-and-egg problem here: the storage account that holds the
state is itself a piece of infrastructure. Building it with Terraform would
require somewhere to put *that* state. The standard escape is to create this
one small piece directly through the cloud's own API, exactly once, and let
Terraform manage everything after it.

That is what this module does.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

STATE_RESOURCE_GROUP = "stratus-state"
STATE_CONTAINER = "tfstate"

CANDIDATE_LOCATIONS = [
    "eastus",
    "centralindia",
    "southeastasia",
    "uksouth",
    "northeurope",
    "westus2",
    "westeurope",
]
"""Regions to try, in order.

Azure publishes a list of regions but does not tell you which ones your
subscription may actually use. Some are capacity-constrained and closed to
new customers, and you only discover this when creation fails with
RequestDisallowedByAzure. New free subscriptions hit this regularly.

So rather than hardcoding one region and hoping, Stratus works down this list
until something succeeds. The order favours regions that are usually open.
"""

DEFAULT_LOCATION = CANDIDATE_LOCATIONS[0]


def state_account_name(subscription_id: str) -> str:
    """Work out the storage account name for a subscription.

    Azure storage account names are globally unique across every customer,
    3-24 characters, lowercase letters and digits only. So the name cannot be
    something friendly like "stratus-state" — someone else already has it.

    Deriving it from a hash of the subscription id gives a name that is
    effectively unique, and — more importantly — *the same every time*. That
    makes this function the answer to "where is my state?" without needing to
    have recorded it anywhere. If Stratus is reinstalled on a new machine it
    recomputes the same name and finds the existing state.
    """
    digest = hashlib.sha256(subscription_id.encode()).hexdigest()[:12]
    return f"stratus{digest}"  # 7 + 12 = 19 characters


@dataclass(frozen=True)
class BackendConfig:
    """Everything Terraform needs in order to find its state."""

    resource_group: str
    storage_account: str
    container: str
    key: str
    """The blob name within the container. One key per set of infrastructure,
    so separate requests never share a state file and can therefore run at
    the same time without blocking each other."""

    def to_hcl(self) -> str:
        """Render the backend block that goes into the Terraform config.

        `use_azuread_auth` matters: without it, Terraform authenticates to the
        storage account with a shared access key, which then has to be
        obtained, passed around and stored somewhere. With it, Terraform uses
        the identity you already signed in with. There is no key to leak.
        """
        return (
            "terraform {\n"
            '  backend "azurerm" {\n'
            f'    resource_group_name  = "{self.resource_group}"\n'
            f'    storage_account_name = "{self.storage_account}"\n'
            f'    container_name       = "{self.container}"\n'
            f'    key                  = "{self.key}"\n'
            "    use_azuread_auth     = true\n"
            "  }\n"
            "}\n"
        )


class StateStorage:
    """Creates and finds the storage that holds Terraform's state.

    `ensure()` is safe to call repeatedly: it creates what is missing and
    leaves alone what already exists. Bootstrap code gets run by people who
    are not sure whether they ran it before, so it has to be forgiving.
    """

    def __init__(
        self,
        subscription_id: str,
        locations: list[str] | None = None,
        credential: Any | None = None,
    ) -> None:
        self.subscription_id = subscription_id
        self.locations = locations or list(CANDIDATE_LOCATIONS)
        self.account_name = state_account_name(subscription_id)
        self.location: str | None = None
        """Set once ensure() finds a region that accepts the account."""
        self._credential = credential

    def _clients(self):
        # Imported lazily so the rest of Stratus, and the whole test suite,
        # work without the Azure SDK installed.
        from azure.identity import DefaultAzureCredential
        from azure.mgmt.resource.resources import ResourceManagementClient
        from azure.mgmt.storage import StorageManagementClient

        credential = self._credential or DefaultAzureCredential()
        return (
            ResourceManagementClient(credential, self.subscription_id),
            StorageManagementClient(credential, self.subscription_id),
        )

    def ensure(self, key: str = "default.tfstate") -> BackendConfig:
        """Make sure state storage exists, and describe how to reach it.

        Creates three things if they are missing: a resource group to hold
        them, a storage account, and a container inside it. Takes roughly
        30-60 seconds the first time and is near-instant afterwards.
        """
        from azure.core.exceptions import ResourceExistsError

        resources, storage = self._clients()

        # 1. A group to keep state storage separate from anything Stratus
        #    builds later, so a user tearing down their infrastructure cannot
        #    accidentally delete the record of what they have.
        #
        #    A resource group's region is fixed at creation and cannot be
        #    changed afterwards — calling create_or_update with a different
        #    one fails rather than moving it. So an existing group is left
        #    exactly as it is. This costs nothing: a group is only metadata,
        #    and the storage account inside it is free to live elsewhere.
        self._ensure_resource_group(resources)

        # 2. The storage account itself, in the first region that will take
        #    it. create() is a long-running operation, so we wait for it.
        if self._account_exists(storage):
            self.location = self._existing_location(storage)
        else:
            self.location = self._create_account(storage)

        # 3. The container the state blobs live in.
        try:
            storage.blob_containers.create(
                STATE_RESOURCE_GROUP,
                self.account_name,
                STATE_CONTAINER,
                {"public_access": "None"},
            )
        except ResourceExistsError:
            pass

        return BackendConfig(
            resource_group=STATE_RESOURCE_GROUP,
            storage_account=self.account_name,
            container=STATE_CONTAINER,
            key=key,
        )

    def _ensure_resource_group(self, resources: Any) -> None:
        """Create the state resource group, or leave an existing one alone."""
        from azure.core.exceptions import ResourceNotFoundError

        try:
            resources.resource_groups.get(STATE_RESOURCE_GROUP)
            return  # already there; its region is immutable, so do not touch it
        except ResourceNotFoundError:
            pass

        resources.resource_groups.create_or_update(
            STATE_RESOURCE_GROUP,
            {
                "location": self.locations[0],
                "tags": {"managed-by": "stratus", "purpose": "terraform-state"},
            },
        )

    def _create_account(self, storage: Any) -> str:
        """Create the storage account in the first region that accepts it.

        Returns the region that worked. Raises if every candidate refuses,
        with the reasons collected — a bare "it failed" would leave the user
        with nothing to act on.
        """
        from azure.core.exceptions import HttpResponseError

        refusals: list[str] = []

        for location in self.locations:
            try:
                poller = storage.storage_accounts.begin_create(
                    STATE_RESOURCE_GROUP,
                    self.account_name,
                    {
                        "location": location,
                        "sku": {"name": "Standard_LRS"},
                        "kind": "StorageV2",
                        "tags": {
                            "managed-by": "stratus",
                            "purpose": "terraform-state",
                        },
                        # Settings other than identity and placement go under
                        # "properties" — that is Azure's REST shape, and this
                        # SDK passes the dictionary straight through rather
                        # than translating field names for us.
                        "properties": {
                            # State files can contain secrets, so the
                            # container must never be readable without
                            # credentials.
                            "allowBlobPublicAccess": False,
                            "minimumTlsVersion": "TLS1_2",
                        },
                    },
                )
                poller.result()
                return location
            except HttpResponseError as exc:
                # Capacity refusals are expected and mean "try elsewhere".
                # Anything else is a real problem and should surface at once
                # rather than being buried under six more failed attempts.
                if "RequestDisallowedByAzure" not in str(exc):
                    raise
                refusals.append(location)

        raise RuntimeError(
            "No available Azure region would accept the state storage account.\n"
            f"Tried: {', '.join(refusals)}\n\n"
            "Every one reported that it is not accepting new customers. This "
            "affects new subscriptions and usually clears within a day or two. "
            "You can also pass your own list:\n"
            '    StateStorage(subscription_id, locations=["yourregion"])'
        )

    def _account_exists(self, storage: Any) -> bool:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            storage.storage_accounts.get_properties(STATE_RESOURCE_GROUP, self.account_name)
            return True
        except ResourceNotFoundError:
            return False

    def _existing_location(self, storage: Any) -> str:
        """Where an already-created account lives."""
        account = storage.storage_accounts.get_properties(
            STATE_RESOURCE_GROUP, self.account_name
        )
        return account.location

    def access_hint(self) -> str:
        """The command that fixes the most confusing failure in this setup.

        Azure separates *managing* a storage account from *reading the data
        inside it*. Being subscription Owner grants the first and not the
        second, so a brand-new account can create the state storage and then
        be refused when Terraform tries to write to it:

            403 AuthorizationPermissionMismatch

        Nothing about that message suggests the fix, so the fix is spelled
        out here rather than left to be rediscovered.

        Deliberately returns the command instead of running it. Granting
        permissions on someone's cloud account is their decision to make
        knowingly, not something a tool should quietly do on their behalf.
        """
        scope = (
            f"/subscriptions/{self.subscription_id}"
            f"/resourceGroups/{STATE_RESOURCE_GROUP}"
            f"/providers/Microsoft.Storage/storageAccounts/{self.account_name}"
        )
        return (
            "Terraform cannot read or write its state file.\n\n"
            "In Azure, managing a storage account and reading the data inside "
            "it are separate permissions. Subscription Owner grants the first "
            "but not the second, so this role has to be added once:\n\n"
            "  az role assignment create \\\n"
            '    --role "Storage Blob Data Contributor" \\\n'
            "    --assignee $(az ad signed-in-user show --query id -o tsv) \\\n"
            f'    --scope "{scope}"\n\n'
            "It grants access to this one storage account and nothing else.\n"
            "Azure takes up to two minutes to apply role changes, so wait a "
            "moment before retrying."
        )

    def config_for(self, key: str) -> BackendConfig:
        """Describe the backend without creating anything.

        Used once the storage is known to exist, so that planning a change
        does not make a network call just to rebuild a string.
        """
        return BackendConfig(
            resource_group=STATE_RESOURCE_GROUP,
            storage_account=self.account_name,
            container=STATE_CONTAINER,
            key=key,
        )
