"""Tests for noticing when the cloud stopped matching the record.

The method is worth stating because it looks like a shortcut and is not:
drift is read out of a plan of the *unchanged* configuration. The
configuration did not move, so anything Terraform proposes is a difference
the cloud introduced. Reimplementing that comparison would mean rebuilding
Terraform's per-resource knowledge of which fields matter, and getting it
subtly wrong.
"""

from __future__ import annotations

from stratus.azure.reader import STRATUS_TAG, STRATUS_TAG_VALUE
from stratus.drift import Drift, compare, explain_drift, from_plan, unmanaged
from stratus.models import Action, Origin, Plan, PlannedChange, Resource, Snapshot


def _change(type_: str, name: str, action: Action) -> PlannedChange:
    return PlannedChange(
        address=f"{type_}.{name}", type=type_, name=name, action=action
    )


def _plan(*changes: PlannedChange) -> Plan:
    return Plan(changes=list(changes))


def _resource(name: str, managed: bool = False) -> Resource:
    tags = {STRATUS_TAG: STRATUS_TAG_VALUE} if managed else {}
    return Resource(
        id=f"/subscriptions/s/resourceGroups/rg/providers/Microsoft.Storage/x/{name}",
        name=name,
        type="Microsoft.Storage/storageAccounts",
        tags=tags,
        origin=Origin.MANAGED if managed else Origin.DISCOVERED,
    )


class TestReadingDriftFromAPlan:
    def test_a_create_means_something_was_deleted(self):
        # We still have it in the record and Terraform wants to make it
        # again, so the cloud no longer has it.
        drift = from_plan(_plan(_change("azurerm_storage_account", "data", Action.CREATE)))
        assert len(drift.vanished) == 1
        assert drift.vanished[0].name == "data"

    def test_an_update_means_settings_were_edited(self):
        drift = from_plan(_plan(_change("azurerm_storage_account", "data", Action.UPDATE)))
        assert len(drift.changed) == 1
        assert drift.changed[0].kind == "changed"

    def test_a_replace_counts_as_changed_but_is_marked(self):
        # Putting it back means destroying and recreating, which the user
        # needs to know before agreeing to it.
        drift = from_plan(_plan(_change("azurerm_storage_account", "data", Action.REPLACE)))
        assert drift.changed[0].kind == "rebuilt"

    def test_a_delete_is_not_drift(self):
        # A delete means the configuration asked for its removal. That is an
        # intended change, not something the cloud did.
        drift = from_plan(_plan(_change("azurerm_storage_account", "old", Action.DELETE)))
        assert not drift.has_drift

    def test_a_no_op_plan_means_everything_matches(self):
        drift = from_plan(_plan(_change("azurerm_storage_account", "data", Action.NO_OP)))
        assert not drift.has_drift
        assert drift.is_clean

    def test_an_empty_plan_is_clean(self):
        assert from_plan(Plan(changes=[])).is_clean


class TestUnmanagedResources:
    def test_finds_what_stratus_did_not_create(self):
        snapshot = Snapshot(
            subscription_id="s",
            resources=[_resource("ours", managed=True), _resource("theirs")],
        )
        found = unmanaged(snapshot)
        assert [r.name for r in found] == ["theirs"]

    def test_someone_elses_resources_are_not_counted_as_drift(self):
        # A colleague creating their own things is them doing their job.
        # Reporting it as a problem trains people to ignore the check.
        drift = Drift(appeared=[_resource("theirs")])
        assert not drift.has_drift
        assert not drift.is_clean  # still worth mentioning


class TestSnapshotComparison:
    def test_spots_something_new(self):
        before = Snapshot(subscription_id="s", resources=[_resource("a")])
        after = Snapshot(subscription_id="s", resources=[_resource("a"), _resource("b")])
        appeared, disappeared = compare(before, after)
        assert [r.name for r in appeared] == ["b"]
        assert disappeared == []

    def test_spots_something_gone(self):
        before = Snapshot(subscription_id="s", resources=[_resource("a"), _resource("b")])
        after = Snapshot(subscription_id="s", resources=[_resource("a")])
        appeared, disappeared = compare(before, after)
        assert appeared == []
        assert [r.name for r in disappeared] == ["b"]

    def test_identical_readings_show_nothing(self):
        snapshot = Snapshot(subscription_id="s", resources=[_resource("a")])
        assert compare(snapshot, snapshot) == ([], [])


class TestExplanation:
    def test_a_clean_check_says_so_plainly(self):
        assert "Everything matches" in explain_drift(Drift())

    def test_a_deletion_states_the_consequence(self):
        # The fact alone is not enough. Anything depending on a deleted
        # resource is already broken whether or not anyone noticed.
        drift = from_plan(_plan(_change("azurerm_storage_account", "data", Action.CREATE)))
        text = explain_drift(drift)
        assert "deleted outside of me" in text
        assert "already broken" in text

    def test_it_warns_that_rebuilding_loses_the_contents(self):
        drift = from_plan(_plan(_change("azurerm_storage_account", "data", Action.CREATE)))
        assert "whatever they contained is gone" in explain_drift(drift)

    def test_a_hand_edit_is_not_treated_as_wrong(self):
        # Someone fixing something urgently in the portal was probably right
        # to. What matters is that the next build will undo it.
        drift = from_plan(_plan(_change("azurerm_storage_account", "data", Action.UPDATE)))
        text = explain_drift(drift)
        assert "not automatically wrong" in text
        assert "will undo it" in text

    def test_a_replacement_warns_about_the_cost_of_putting_it_back(self):
        drift = from_plan(_plan(_change("azurerm_storage_account", "d", Action.REPLACE)))
        assert "destroying and recreating" in explain_drift(drift)

    def test_unmanaged_resources_are_mentioned_and_left_alone(self):
        drift = Drift(appeared=[_resource("someone-elses-db")])
        text = explain_drift(drift)
        assert "did not come from me" in text
        assert "leave these alone" in text

    def test_a_long_list_is_truncated(self):
        drift = Drift(appeared=[_resource(f"r{i}") for i in range(25)])
        text = explain_drift(drift)
        assert "and 15 more" in text

    def test_it_says_how_to_put_things_back(self):
        drift = from_plan(_plan(_change("azurerm_storage_account", "d", Action.CREATE)))
        assert "run a build again" in explain_drift(drift)

    def test_it_uses_plain_words(self):
        drift = from_plan(_plan(_change("azurerm_storage_account", "d", Action.CREATE)))
        text = explain_drift(drift)
        assert "place to keep files" in text
        assert "azurerm_" not in text
