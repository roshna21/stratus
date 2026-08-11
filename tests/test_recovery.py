"""Tests for half-finished builds.

Not hypothetical. Two real builds against a live Azure account died partway
and left resources behind — once on a gateway timeout, once on a quota of
zero. The addresses below are the ones that actually survived.
"""

from __future__ import annotations

import pytest

from stratus.models import Action, Plan, PlannedChange
from stratus.recovery import assess, explain_partial, parse_choice

# What the real failure left: the group, the storage and the container were
# made; the hosting plan and the website never were.
SURVIVED = [
    "azurerm_resource_group.rg",
    "azurerm_storage_account.storage",
    "azurerm_storage_container.uploads",
    "random_string.suffix",
]
PLANNED = SURVIVED + [
    "azurerm_service_plan.plan",
    "azurerm_linux_web_app.app",
]

QUOTA_ERROR = (
    "Error: creating App Service Plan: unexpected status 401 "
    "(401 Unauthorized): Operation cannot be completed without additional quota."
)


def _plan(*addresses: str) -> Plan:
    return Plan(
        changes=[
            PlannedChange(
                address=address,
                type=address.split(".")[0],
                name=address.split(".")[1],
                action=Action.CREATE,
                after={"name": address.split(".")[1]},
            )
            for address in addresses
        ]
    )


class TestAssessment:
    def test_splits_what_exists_from_what_does_not(self):
        partial = assess(_plan(*PLANNED), SURVIVED)
        assert partial.created == SURVIVED
        assert partial.missing == ["azurerm_service_plan.plan", "azurerm_linux_web_app.app"]

    def test_identifies_where_it_stopped(self):
        # Plans are in dependency order, so the first thing missing is the
        # one the failure landed on.
        partial = assess(_plan(*PLANNED), SURVIVED)
        assert partial.failed_at == "azurerm_service_plan.plan"

    def test_recognises_a_genuinely_partial_build(self):
        assert assess(_plan(*PLANNED), SURVIVED).is_partial

    def test_a_failure_before_anything_was_made_is_not_partial(self):
        # Nothing survived, so there is nothing to clean up — it just needs
        # retrying, and offering a recovery choice would be noise.
        partial = assess(_plan(*PLANNED), [])
        assert not partial.is_partial
        assert partial.is_clean_failure

    def test_a_complete_build_leaves_nothing_missing(self):
        partial = assess(_plan(*SURVIVED), SURVIVED)
        assert partial.missing == []
        assert not partial.is_partial

    def test_it_asks_the_cloud_nothing(self):
        # The state file was updated as each resource succeeded, so it
        # already holds the answer. Calling Azure here would be slower and
        # could fail for the same reason the build did.
        partial = assess(_plan(*PLANNED), SURVIVED, reason=QUOTA_ERROR)
        assert partial.reason == QUOTA_ERROR

    def test_ignores_resources_that_were_never_going_to_be_created(self):
        plan = Plan(
            changes=[
                PlannedChange(
                    address="azurerm_storage_account.existing",
                    type="azurerm_storage_account",
                    name="existing",
                    action=Action.NO_OP,
                )
            ]
        )
        assert assess(plan, []).missing == []


class TestExplanation:
    def _text(self) -> str:
        return explain_partial(assess(_plan(*PLANNED), SURVIVED, reason=QUOTA_ERROR))

    def test_says_plainly_that_it_stopped_partway(self):
        assert "stopped partway" in self._text()

    def test_separates_what_was_made_from_what_was_not(self):
        text = self._text()
        assert "Made before it stopped" in text
        assert "Never made" in text

    def test_warns_that_the_leftovers_may_cost_money(self):
        # The thing people miss when reading an error: half-built
        # infrastructure is useless but still billable.
        assert "costing you money" in self._text()

    def test_keeps_what_the_cloud_said(self):
        assert "401" in self._text()

    def test_offers_both_ways_out(self):
        text = self._text()
        assert "finish" in text
        assert "undo" in text

    def test_uses_plain_words_for_the_resources(self):
        text = self._text()
        assert "place to keep files" in text
        assert "azurerm_storage_account" not in text

    def test_counts_plumbing_rather_than_naming_it(self):
        assert "supporting piece" in self._text()

    def test_a_clean_failure_says_nothing_was_left_behind(self):
        text = explain_partial(assess(_plan(*PLANNED), [], reason=QUOTA_ERROR))
        assert "nothing is left behind" in text
        assert "finish" not in text  # nothing to recover, so no choice offered


class TestChoiceParsing:
    @pytest.mark.parametrize("answer", ["finish", "FINISH", " finish ", "f", "retry", "continue"])
    def test_reads_finish(self, answer):
        assert parse_choice(answer) == "finish"

    @pytest.mark.parametrize("answer", ["undo", "UNDO", "u", "rollback", "revert"])
    def test_reads_undo(self, answer):
        assert parse_choice(answer) == "undo"

    @pytest.mark.parametrize("answer", ["", "yes", "no", "maybe", "delete", "y"])
    def test_refuses_to_guess(self, answer):
        # An unrecognised answer leaves the half-built state alone, which is
        # recoverable. Guessing could delete something they wanted to keep.
        assert parse_choice(answer) is None
