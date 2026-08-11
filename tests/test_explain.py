"""Tests for the approval text.

This is the screen a person reads before consenting to a change, so these
tests care about what it does NOT say as much as what it does. A plan that
quietly omits a deletion produces consent that was never actually given.
"""

from __future__ import annotations

import pytest

from stratus.explain import confirmation_is_valid, describe, explain, is_supporting
from stratus.models import Action, Plan, PlannedChange


def _change(type_: str, name: str, action: Action) -> PlannedChange:
    after = {"name": name} if action is not Action.DELETE else None
    before = {"name": name} if action in (Action.DELETE, Action.REPLACE) else None
    return PlannedChange(
        address=f"{type_}.{name}",
        type=type_,
        name=name,
        action=action,
        before=before,
        after=after,
    )


def _plan(*changes: PlannedChange) -> Plan:
    return Plan(changes=list(changes))


class TestVocabulary:
    def test_translates_a_known_type(self):
        assert describe("azurerm_storage_account") == "place to keep files"

    def test_pluralises(self):
        assert describe("azurerm_linux_web_app", plural=True) == "websites"

    def test_shows_unknown_types_rather_than_hiding_them(self):
        # A resource the user is not told about is a change they did not
        # agree to, so an unfamiliar type must still appear.
        assert describe("azurerm_cognitive_account") == "cognitive account"

    def test_knows_what_is_plumbing(self):
        assert is_supporting("azurerm_resource_group")
        assert is_supporting("random_string")
        assert not is_supporting("azurerm_storage_account")


class TestCreating:
    def test_names_what_the_user_asked_for(self):
        text = explain(_plan(_change("azurerm_storage_account", "myfiles", Action.CREATE)))
        assert "place to keep files (myfiles)" in text

    def test_counts_plumbing_instead_of_naming_it(self):
        # Listing a resource group and a random-string generator beside the
        # one thing the user wanted makes a simple request look alarming.
        text = explain(
            _plan(
                _change("azurerm_storage_account", "myfiles", Action.CREATE),
                _change("azurerm_resource_group", "rg-files", Action.CREATE),
                _change("random_string", "suffix", Action.CREATE),
            )
        )
        assert "place to keep files (myfiles)" in text
        assert "plus 2 supporting pieces" in text
        assert "rg-files" not in text

    def test_reassures_when_nothing_is_at_risk(self):
        text = explain(_plan(_change("azurerm_storage_account", "f", Action.CREATE)))
        assert "Nothing existing will be changed or deleted." in text

    def test_does_not_shout_about_a_safe_plan(self):
        text = explain(_plan(_change("azurerm_storage_account", "f", Action.CREATE)))
        assert "DESTROY" not in text

    def test_handles_a_plan_that_is_only_plumbing(self):
        text = explain(_plan(_change("azurerm_resource_group", "rg", Action.CREATE)))
        assert "1 supporting piece" in text


class TestDestroying:
    def test_warns_before_anything_else(self):
        # A deletion listed after a page of harmless creations is how someone
        # approves it without noticing.
        text = explain(
            _plan(
                _change("azurerm_storage_account", "new", Action.CREATE),
                _change("azurerm_postgresql_flexible_server", "old-db", Action.DELETE),
            )
        )
        assert text.index("DESTROY") < text.index("Creating")

    def test_says_data_will_be_lost(self):
        text = explain(
            _plan(_change("azurerm_postgresql_flexible_server", "prod", Action.DELETE))
        )
        assert "everything stored in it will be lost, permanently" in text

    def test_does_not_claim_data_loss_for_things_that_hold_none(self):
        text = explain(_plan(_change("azurerm_resource_group", "rg", Action.DELETE)))
        assert "permanently" not in text

    def test_names_the_resource_being_deleted(self):
        # "a database" is not enough to decide on. Which one matters.
        text = explain(
            _plan(_change("azurerm_postgresql_flexible_server", "customers", Action.DELETE))
        )
        assert "customers" in text

    def test_still_names_plumbing_when_it_is_being_deleted(self):
        # Grouping is a courtesy when creating. When destroying, every item
        # gets named — the user needs the full list.
        text = explain(_plan(_change("azurerm_resource_group", "rg-prod", Action.DELETE)))
        assert "rg-prod" in text


class TestReplacing:
    def test_explains_that_a_replacement_destroys_the_original(self):
        # The trap this whole design exists for: Terraform calls it a
        # "replace", which sounds harmless, and it is not.
        text = explain(
            _plan(_change("azurerm_storage_account", "files", Action.REPLACE))
        )
        assert "Destroying and rebuilding" in text
        assert "current contents are lost" in text

    def test_warns_about_downtime_for_things_holding_no_data(self):
        text = explain(_plan(_change("azurerm_linux_web_app", "site", Action.REPLACE)))
        assert "unavailable while this happens" in text

    def test_a_replacement_counts_as_destructive(self):
        text = explain(_plan(_change("azurerm_linux_web_app", "site", Action.REPLACE)))
        assert "DESTROY" in text


class TestApproval:
    def test_a_safe_plan_asks_a_simple_question(self):
        text = explain(_plan(_change("azurerm_storage_account", "f", Action.CREATE)))
        assert "[yes / no]" in text

    def test_a_destructive_plan_demands_a_typed_word(self):
        # Pressing y is reflexive. Typing DELETE is deliberate, and that
        # difference is the entire point of the gate.
        text = explain(_plan(_change("azurerm_storage_account", "f", Action.DELETE)))
        assert "type exactly:  DELETE" in text
        assert "[yes / no]" not in text

    @pytest.mark.parametrize("answer", ["yes", "y", "YES", " yes "])
    def test_accepts_ordinary_agreement_for_a_safe_plan(self, answer):
        plan = _plan(_change("azurerm_storage_account", "f", Action.CREATE))
        assert confirmation_is_valid(plan, answer)

    @pytest.mark.parametrize("answer", ["no", "", "maybe", "sure"])
    def test_rejects_anything_else_for_a_safe_plan(self, answer):
        plan = _plan(_change("azurerm_storage_account", "f", Action.CREATE))
        assert not confirmation_is_valid(plan, answer)

    def test_accepts_only_the_exact_word_for_a_destructive_plan(self):
        plan = _plan(_change("azurerm_storage_account", "f", Action.DELETE))
        assert confirmation_is_valid(plan, "DELETE")
        assert confirmation_is_valid(plan, "  DELETE  ")

    @pytest.mark.parametrize("answer", ["yes", "y", "delete", "Delete", "DELETE!"])
    def test_a_destructive_plan_refuses_near_misses(self, answer):
        # "delete" in lower case is something you might type while thinking
        # aloud. Only the deliberate form counts.
        plan = _plan(_change("azurerm_storage_account", "f", Action.DELETE))
        assert not confirmation_is_valid(plan, answer)


class TestNothingToDo:
    def test_says_so_plainly(self):
        # What the user sees when they ask twice for the same thing. This is
        # the payoff for reading the account before planning.
        text = explain(Plan(changes=[]))
        assert "already have everything you asked for" in text
        assert "?" not in text  # nothing to approve, so nothing is asked

    def test_a_plan_of_only_no_ops_counts_as_nothing_to_do(self):
        plan = _plan(_change("azurerm_storage_account", "f", Action.NO_OP))
        assert "already have everything" in explain(plan)


class TestNoJargon:
    """The product promise, asserted directly."""

    @pytest.mark.parametrize(
        "action", [Action.CREATE, Action.UPDATE, Action.DELETE, Action.REPLACE]
    )
    def test_never_leaks_terraform_vocabulary(self, action):
        text = explain(
            _plan(
                _change("azurerm_storage_account", "files", action),
                _change("azurerm_resource_group", "rg", action),
            )
        )
        for word in ("terraform", "azurerm_", "resource_group", "tfstate", "hcl"):
            assert word not in text.lower(), f"leaked {word!r}"
