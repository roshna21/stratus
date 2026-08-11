"""Tests for the remote state configuration.

No Azure needed: the naming and config rendering are pure logic, and they
are the parts that would cause real damage if they were wrong.
"""

from __future__ import annotations

import re

from stratus.azure.state import (
    STATE_CONTAINER,
    STATE_RESOURCE_GROUP,
    BackendConfig,
    StateStorage,
    state_account_name,
)

SUB_A = "62b44261-c42a-4346-b65d-496a653e7b2d"
SUB_B = "11111111-2222-3333-4444-555555555555"


class TestAccountNaming:
    """Azure storage account names have strict rules, and getting one wrong
    fails at creation time with an unhelpful message."""

    def test_is_within_the_length_limit(self):
        name = state_account_name(SUB_A)
        assert 3 <= len(name) <= 24, f"{name!r} is {len(name)} characters"

    def test_uses_only_lowercase_letters_and_digits(self):
        # Azure rejects hyphens, underscores and capitals here, unlike almost
        # every other resource type.
        assert re.fullmatch(r"[a-z0-9]+", state_account_name(SUB_A))

    def test_is_the_same_every_time(self):
        # This is what lets Stratus find existing state on a fresh machine
        # without having recorded the name anywhere.
        assert state_account_name(SUB_A) == state_account_name(SUB_A)

    def test_differs_between_subscriptions(self):
        # Two people running Stratus must not collide on a globally unique
        # name, and must never share a state file.
        assert state_account_name(SUB_A) != state_account_name(SUB_B)

    def test_starts_with_a_recognisable_prefix(self):
        # So a human scanning the Azure portal can tell what it is.
        assert state_account_name(SUB_A).startswith("stratus")


class TestBackendConfig:
    def _config(self, key="default.tfstate") -> BackendConfig:
        return BackendConfig(
            resource_group=STATE_RESOURCE_GROUP,
            storage_account="stratusabc123def456",
            container=STATE_CONTAINER,
            key=key,
        )

    def test_renders_a_valid_backend_block(self):
        hcl = self._config().to_hcl()
        assert 'backend "azurerm"' in hcl
        assert "stratusabc123def456" in hcl
        assert STATE_CONTAINER in hcl

    def test_authenticates_with_an_identity_not_a_key(self):
        # Without this, Terraform uses a shared storage key that has to be
        # fetched, passed around and stored. With it, there is no key to leak.
        assert "use_azuread_auth     = true" in self._config().to_hcl()

    def test_different_infrastructure_gets_a_different_state_file(self):
        # One key per set of infrastructure. Sharing one file would mean two
        # unrelated requests block each other on the lock, and a mistake in
        # one could damage the other.
        a = self._config("website.tfstate").to_hcl()
        b = self._config("database.tfstate").to_hcl()
        assert a != b
        assert "website.tfstate" in a
        assert "database.tfstate" in b


class TestStateStorage:
    def test_derives_its_account_name_from_the_subscription(self):
        assert StateStorage(SUB_A).account_name == state_account_name(SUB_A)

    def test_describes_the_backend_without_touching_azure(self):
        # config_for() must make no network call — it is used on the hot path
        # of every plan.
        config = StateStorage(SUB_A).config_for("thing.tfstate")
        assert config.storage_account == state_account_name(SUB_A)
        assert config.key == "thing.tfstate"
        assert config.resource_group == STATE_RESOURCE_GROUP

    def test_falls_back_across_regions(self):
        # Azure lists regions it has, not regions your subscription may use.
        # New subscriptions are routinely refused by capacity-constrained
        # ones, so there has to be more than one candidate.
        assert len(StateStorage(SUB_A).locations) > 1

    def test_accepts_an_explicit_region_list(self):
        storage = StateStorage(SUB_A, locations=["uksouth"])
        assert storage.locations == ["uksouth"]

    def test_location_is_unknown_until_storage_is_created(self):
        # It is discovered by trying, not assumed up front.
        assert StateStorage(SUB_A).location is None

    def test_access_hint_names_the_exact_role_and_scope(self):
        # The 403 this explains gives no clue about its own fix, so the hint
        # has to carry the role name and the precise scope.
        hint = StateStorage(SUB_A).access_hint()
        assert "Storage Blob Data Contributor" in hint
        assert state_account_name(SUB_A) in hint
        assert SUB_A in hint
        assert "az role assignment create" in hint

    def test_state_lives_in_its_own_resource_group(self):
        # Separate from anything Stratus builds, so tearing down your
        # infrastructure cannot delete the record of what you had.
        assert STATE_RESOURCE_GROUP == "stratus-state"
        assert StateStorage(SUB_A).config_for("k").resource_group == "stratus-state"
