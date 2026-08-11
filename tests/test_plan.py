"""Tests for reading Terraform's JSON plan output.

Pure parsing, so all of it runs from fixtures — no Terraform, no Azure,
no network.
"""

from __future__ import annotations

from stratus.models import Action, Plan
from stratus.terraform.plan import _action_from_terraform, parse_plan


def _change(address: str, actions: list[str], type_: str = "azurerm_storage_account"):
    return {
        "address": address,
        "type": type_,
        "name": address.split(".")[-1],
        "change": {"actions": actions, "before": None, "after": {}},
    }


def _doc(*changes):
    return {"format_version": "1.2", "resource_changes": list(changes)}


class TestActionMapping:
    def test_create(self):
        assert _action_from_terraform(["create"]) is Action.CREATE

    def test_update(self):
        assert _action_from_terraform(["update"]) is Action.UPDATE

    def test_delete(self):
        assert _action_from_terraform(["delete"]) is Action.DELETE

    def test_no_op(self):
        assert _action_from_terraform(["no-op"]) is Action.NO_OP

    def test_reading_a_data_source_is_not_a_change(self):
        assert _action_from_terraform(["read"]) is Action.NO_OP

    def test_destroy_then_create_is_one_replacement(self):
        assert _action_from_terraform(["delete", "create"]) is Action.REPLACE

    def test_create_then_destroy_is_also_one_replacement(self):
        # create_before_destroy avoids downtime, but the old resource and
        # everything on it is still destroyed. Same warning either way.
        assert _action_from_terraform(["create", "delete"]) is Action.REPLACE

    def test_an_unrecognised_combination_is_treated_as_destructive(self):
        # The cautious default. An unknown action must be routed through the
        # confirmation gate rather than waved through.
        assert _action_from_terraform(["something-new"]) is Action.REPLACE


class TestDestructiveness:
    def test_delete_is_destructive(self):
        assert Action.DELETE.is_destructive

    def test_replace_is_destructive(self):
        # The one people forget: a replacement destroys the original, so any
        # data on it is gone.
        assert Action.REPLACE.is_destructive

    def test_create_is_not(self):
        assert not Action.CREATE.is_destructive

    def test_update_is_not(self):
        assert not Action.UPDATE.is_destructive


class TestParsePlan:
    def test_parses_an_empty_plan(self):
        plan = parse_plan(_doc())
        assert isinstance(plan, Plan)
        assert plan.changes == []
        assert plan.is_empty

    def test_parses_a_single_create(self):
        plan = parse_plan(_doc(_change("azurerm_storage_account.data", ["create"])))
        assert len(plan.changes) == 1
        change = plan.changes[0]
        assert change.address == "azurerm_storage_account.data"
        assert change.type == "azurerm_storage_account"
        assert change.name == "data"
        assert change.action is Action.CREATE

    def test_keeps_the_raw_document(self):
        # Anything we failed to anticipate is still reachable rather than lost.
        doc = _doc(_change("azurerm_storage_account.data", ["create"]))
        assert parse_plan(doc).raw == doc

    def test_survives_a_malformed_entry(self):
        # Never crash on unexpected shapes; a crash here would take down a
        # request the user is waiting on.
        plan = parse_plan({"resource_changes": [{}]})
        assert len(plan.changes) == 1
        assert plan.changes[0].address == ""


class TestPlanQuestions:
    """The questions the approval step asks a plan."""

    def _mixed(self) -> Plan:
        return parse_plan(
            _doc(
                _change("azurerm_storage_account.new", ["create"]),
                _change("azurerm_web_app.existing", ["update"]),
                _change("azurerm_postgresql.old", ["delete"]),
                _change("azurerm_network.rebuilt", ["delete", "create"]),
            )
        )

    def test_finds_destructive_changes(self):
        destructive = self._mixed().destructive_changes
        assert {c.name for c in destructive} == {"old", "rebuilt"}

    def test_flags_a_plan_as_destructive(self):
        assert self._mixed().is_destructive

    def test_a_create_only_plan_is_not_destructive(self):
        plan = parse_plan(_doc(_change("azurerm_storage_account.a", ["create"])))
        assert not plan.is_destructive
        assert plan.destructive_changes == []

    def test_filters_by_action(self):
        plan = self._mixed()
        assert len(plan.of(Action.CREATE)) == 1
        assert len(plan.of(Action.CREATE, Action.UPDATE)) == 2

    def test_a_plan_of_only_no_ops_counts_as_empty(self):
        # This is what makes asking for the same thing twice safe: Terraform
        # returns no-ops, the plan reads as empty, and Stratus can say
        # "you already have this" instead of building a duplicate.
        plan = parse_plan(
            _doc(
                _change("azurerm_storage_account.a", ["no-op"]),
                _change("azurerm_web_app.b", ["no-op"]),
            )
        )
        assert plan.is_empty
        assert not plan.is_destructive

    def test_a_plan_with_one_real_change_is_not_empty(self):
        plan = parse_plan(
            _doc(
                _change("azurerm_storage_account.a", ["no-op"]),
                _change("azurerm_web_app.b", ["create"]),
            )
        )
        assert not plan.is_empty
