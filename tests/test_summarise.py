"""Tests for the plain-English summary.

The product promise is that the user never sees infrastructure jargon, so
these tests check for the *absence* of Azure vocabulary as much as the
presence of the right numbers.
"""

from __future__ import annotations

from stratus.azure.reader import STRATUS_TAG, STRATUS_TAG_VALUE, FakeAzureReader
from stratus.models import Resource, Snapshot
from stratus.summarise import friendly_type, summarise


def _snapshot(*resources: Resource) -> Snapshot:
    return Snapshot(subscription_id="test-sub", resources=list(resources))


def _resource(name: str, type_: str, *, group="rg", managed=False) -> Resource:
    tags = {STRATUS_TAG: STRATUS_TAG_VALUE} if managed else {}
    from stratus.azure.reader import _origin_from_tags

    return Resource(
        id=f"/subscriptions/s/resourceGroups/{group}/providers/{type_}/{name}",
        name=name,
        type=type_,
        resource_group=group,
        tags=tags,
        origin=_origin_from_tags(tags),
    )


class TestFriendlyType:
    def test_translates_a_known_type(self):
        assert friendly_type("Microsoft.Storage/storageAccounts") == "storage account"

    def test_pluralises_a_known_type(self):
        assert (
            friendly_type("Microsoft.Storage/storageAccounts", plural=True)
            == "storage accounts"
        )

    def test_translates_the_worst_offender(self):
        # If any Azure type string justifies this whole module, it's this one.
        assert (
            friendly_type("Microsoft.DBforPostgreSQL/flexibleServers") == "PostgreSQL database"
        )

    def test_falls_back_readably_for_an_unknown_type(self):
        # Unknown resources must still be shown. Hiding them would mean the
        # user makes decisions from an incomplete picture.
        assert friendly_type("Microsoft.Foo/barWidgets", plural=True) == "bar widgets"

    def test_fallback_does_not_mangle_words_ending_in_double_s(self):
        assert friendly_type("Microsoft.Foo/express") == "express"


class TestSummarise:
    def test_empty_account_says_so_plainly(self):
        assert "empty" in summarise(_snapshot()).lower()

    def test_reports_the_total(self):
        text = summarise(FakeAzureReader().read())
        assert "5 things" in text

    def test_uses_singular_for_one_resource(self):
        text = summarise(_snapshot(_resource("solo", "Microsoft.Web/sites")))
        assert "1 thing in this account" in text
        assert "1 things" not in text

    def test_never_leaks_azure_type_strings(self):
        # The core product promise, asserted directly.
        text = summarise(FakeAzureReader().read())
        assert "Microsoft." not in text
        assert "flexibleServers" not in text
        assert "storageAccounts" not in text

    def test_distinguishes_what_it_made_from_what_it_found(self):
        text = summarise(FakeAzureReader().read())
        assert "2 of these were set up by me" in text
        assert "3 were already here" in text

    def test_when_it_owns_everything_it_says_so(self):
        text = summarise(_snapshot(_resource("a", "Microsoft.Web/sites", managed=True)))
        assert "I set all of these up" in text

    def test_when_it_owns_nothing_it_promises_to_be_careful(self):
        text = summarise(_snapshot(_resource("a", "Microsoft.Web/sites")))
        assert "leave them alone" in text

    def test_mentions_groups_only_when_there_is_more_than_one(self):
        many = summarise(FakeAzureReader().read())
        assert "2 groups" in many

        one = summarise(_snapshot(_resource("a", "Microsoft.Web/sites", group="only")))
        assert "groups:" not in one

    def test_groups_identical_resources_into_a_count(self):
        text = summarise(
            _snapshot(
                _resource("a", "Microsoft.Web/sites"),
                _resource("b", "Microsoft.Web/sites"),
                _resource("c", "Microsoft.Web/sites"),
            )
        )
        assert "3 x web apps" in text
