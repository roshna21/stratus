"""Tests for reading an Azure account.

None of these need an Azure account, a network connection, or any money.
"""

from __future__ import annotations

from types import SimpleNamespace

from stratus.azure.reader import (
    STRATUS_TAG,
    STRATUS_TAG_VALUE,
    FakeAzureReader,
    LiveAzureReader,
    _resource_group_from_id,
)
from stratus.models import Origin, Resource, Snapshot


class TestResourceGroupParsing:
    """The group name is parsed out of the id rather than fetched separately."""

    def test_extracts_group_from_a_normal_id(self):
        rid = (
            "/subscriptions/abc-123/resourceGroups/my-group"
            "/providers/Microsoft.Storage/storageAccounts/mydata"
        )
        assert _resource_group_from_id(rid) == "my-group"

    def test_is_case_insensitive_about_the_segment_name(self):
        # Azure is inconsistent about this in its own APIs: the same account
        # returns both "resourceGroups" and "resourcegroups" depending on the
        # endpoint, so matching exactly on case silently loses resources.
        rid = (
            "/subscriptions/abc-123/resourcegroups/my-group"
            "/providers/Microsoft.Storage/storageAccounts/mydata"
        )
        assert _resource_group_from_id(rid) == "my-group"

    def test_returns_none_for_subscription_level_resources(self):
        # Some resources live directly under the subscription with no group.
        assert _resource_group_from_id("/subscriptions/abc-123") is None

    def test_returns_none_rather_than_crashing_on_junk(self):
        assert _resource_group_from_id("not-a-real-id") is None


class TestOriginDetection:
    """Telling apart what Stratus made from what it found."""

    def test_resource_with_the_marker_tag_is_managed(self):
        snapshot = FakeAzureReader().read()
        web_app = next(r for r in snapshot.resources if r.name == "stratus-web-a41f")
        assert web_app.origin is Origin.MANAGED
        assert web_app.is_stratus_managed()

    def test_resource_without_the_tag_is_only_discovered(self):
        snapshot = FakeAzureReader().read()
        pre_existing = next(r for r in snapshot.resources if r.name == "companydata")
        assert pre_existing.origin is Origin.DISCOVERED
        assert not pre_existing.is_stratus_managed()

    def test_unknown_resources_default_to_discovered(self):
        # The cautious default matters: an untagged resource must never be
        # assumed safe to delete just because we failed to identify it.
        bare = Resource(id="/x", name="x", type="Microsoft.Foo/bars")
        assert bare.origin is Origin.DISCOVERED

    def test_a_different_tag_value_does_not_count_as_ours(self):
        confusing = Resource(
            id="/x",
            name="x",
            type="Microsoft.Foo/bars",
            tags={STRATUS_TAG: "some-other-tool"},
        )
        assert confusing.origin is Origin.DISCOVERED


class TestFakeReader:
    """The fake stands in for a real account during development."""

    def test_reads_the_example_account(self):
        snapshot = FakeAzureReader().read()
        assert isinstance(snapshot, Snapshot)
        assert len(snapshot) == 5

    def test_handles_an_empty_account(self):
        # A brand new subscription has nothing in it, and that must not be
        # treated as an error.
        snapshot = FakeAzureReader(resources=[]).read()
        assert len(snapshot) == 0
        assert snapshot.count_by_type() == {}

    def test_handles_resources_with_no_location(self):
        # Global resources such as DNS zones genuinely have no region.
        snapshot = FakeAzureReader().read()
        dns = next(r for r in snapshot.resources if r.name == "demo-dns")
        assert dns.location is None

    def test_reads_across_multiple_resource_groups(self):
        snapshot = FakeAzureReader().read()
        groups = {r.resource_group for r in snapshot.resources}
        assert groups == {"demo-rg", "old-rg"}

    def test_accepts_a_custom_set_of_resources(self):
        only = Resource(id="/x", name="solo", type="Microsoft.Foo/bars")
        snapshot = FakeAzureReader(resources=[only]).read()
        assert len(snapshot) == 1
        assert snapshot.resources[0].name == "solo"


class TestSnapshot:
    """The summarising helpers a human-readable answer is built from."""

    def test_counts_by_type(self):
        counts = FakeAzureReader().read().count_by_type()
        assert counts["Microsoft.Storage/storageAccounts"] == 1
        assert counts["Microsoft.Web/sites"] == 1
        assert sum(counts.values()) == 5

    def test_indexes_by_id(self):
        snapshot = FakeAzureReader().read()
        index = snapshot.by_id()
        assert len(index) == len(snapshot)
        for resource_id, resource in index.items():
            assert resource.id == resource_id

    def test_records_when_it_was_taken(self):
        # Drift detection in Phase 3 compares snapshots over time, so a
        # snapshot without a timestamp is useless.
        snapshot = FakeAzureReader().read()
        assert snapshot.taken_at is not None


class TestLiveReaderConversion:
    """The real reader's translation step, tested without touching Azure.

    Only the conversion is exercised here. It is pure logic, so it can be
    tested with a stand-in object shaped like the one the Azure SDK returns —
    no account, no network, no credentials.
    """

    def test_converts_an_sdk_object_into_a_resource(self):
        sdk_object = SimpleNamespace(
            id=(
                "/subscriptions/abc-123/resourceGroups/prod-rg"
                "/providers/Microsoft.Storage/storageAccounts/prodstore"
            ),
            name="prodstore",
            type="Microsoft.Storage/storageAccounts",
            location="uksouth",
            tags={"env": "prod"},
        )

        resource = LiveAzureReader._to_resource(sdk_object)

        assert resource.name == "prodstore"
        assert resource.type == "Microsoft.Storage/storageAccounts"
        assert resource.location == "uksouth"
        assert resource.resource_group == "prod-rg"
        assert resource.tags == {"env": "prod"}
        assert resource.origin is Origin.DISCOVERED

    def test_treats_a_tagged_sdk_object_as_managed(self):
        sdk_object = SimpleNamespace(
            id="/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Web/sites/app",
            name="app",
            type="Microsoft.Web/sites",
            location="uksouth",
            tags={STRATUS_TAG: STRATUS_TAG_VALUE},
        )
        assert LiveAzureReader._to_resource(sdk_object).origin is Origin.MANAGED

    def test_survives_a_resource_with_no_tags(self):
        # Azure returns None, not {}, when a resource has never been tagged.
        sdk_object = SimpleNamespace(
            id="/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Web/sites/app",
            name="app",
            type="Microsoft.Web/sites",
            location="uksouth",
            tags=None,
        )
        assert LiveAzureReader._to_resource(sdk_object).tags == {}

    def test_survives_a_resource_with_no_location(self):
        sdk_object = SimpleNamespace(
            id="/subscriptions/abc/providers/Microsoft.Network/dnsZones/z",
            name="z",
            type="Microsoft.Network/dnsZones",
            tags={},
        )
        assert LiveAzureReader._to_resource(sdk_object).location is None


def test_fake_and_live_readers_are_interchangeable():
    """Both satisfy the same interface, so callers cannot tell them apart.

    This is what lets every other part of Stratus be developed and tested
    without an Azure account.
    """
    assert hasattr(FakeAzureReader, "read")
    assert hasattr(LiveAzureReader, "read")
    assert isinstance(FakeAzureReader().read(), Snapshot)
