"""Tests for the failures that actually happened.

Each of these comes from a real run against a real Azure account, not from
imagining what might go wrong. Terraform and Azure both report these
accurately and unhelpfully, and a user who cannot act on an error is stuck.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stratus.agent.prompts import DEFAULT_REGION, FALLBACK_REGIONS, build_user_message
from stratus.models import Snapshot
from stratus.pipeline import _progress_filter
from stratus.terraform.runner import (
    CapacityUnavailable,
    QuotaBlocked,
    StateLocked,
    TerraformError,
    _extract_lock_id,
    _looks_like_capacity,
    _looks_like_quota,
)

# Verbatim from the run that produced it.
LOCK_OUTPUT = """
Error: Error acquiring the state lock

Lock Info:
  ID:        822ebbb4-13c4-c5db-05f2-4326bbc276b6
  Path:      tfstate/default.tfstate
  Operation: OperationTypeApply
  Who:       roshnasai@roshnas-Laptop.local
  Created:   2026-08-11 16:44:50.59897 +0000 UTC
"""

GATEWAY_TIMEOUT = (
    'Error: creating Service Plan: {"error":{"code":"GatewayTimeout",'
    '"message":"The gateway did not receive a response from '
    "'Microsoft.Web' within the specified time period.\"}}"
)

REGION_REFUSED = (
    "Error: RequestDisallowedByAzure: The selected region is currently "
    "not accepting new customers"
)


def _error(text: str) -> TerraformError:
    return TerraformError(["terraform", "apply"], 1, text, "")


class TestStaleLock:
    """Killing Terraform mid-apply leaves the lock held. It happened."""

    def test_pulls_the_lock_id_out(self):
        assert _extract_lock_id(LOCK_OUTPUT) == "822ebbb4-13c4-c5db-05f2-4326bbc276b6"

    def test_copes_with_no_id_present(self):
        assert _extract_lock_id("Error acquiring the state lock") is None

    def test_the_message_gives_the_exact_command(self):
        locked = StateLocked(_error(LOCK_OUTPUT), Path("/workspaces/example"))
        message = str(locked)
        assert "terraform force-unlock 822ebbb4-13c4-c5db-05f2-4326bbc276b6" in message
        assert "/workspaces/example" in message

    def test_it_tells_you_to_check_first(self):
        # Unlocking underneath a live operation is how state gets corrupted,
        # so the check has to come before the fix.
        message = str(StateLocked(_error(LOCK_OUTPUT), Path("/workspaces/example")))
        assert "pgrep" in message
        assert message.index("pgrep") < message.index("force-unlock")

    def test_it_explains_why_the_lock_exists(self):
        # A user who thinks the lock is a bug will disable locking, which
        # removes the protection entirely.
        message = str(StateLocked(_error(LOCK_OUTPUT), Path("/workspaces/example")))
        assert "safety" in message.lower()
        assert "corrupt" in message.lower()

    def test_still_usable_without_an_id(self):
        message = str(StateLocked(_error("Error acquiring the state lock"), Path("/x")))
        assert "force-unlock" in message


class TestCapacity:
    """Azure never says "we are full". It says something else."""

    @pytest.mark.parametrize(
        "text",
        [
            GATEWAY_TIMEOUT,
            REGION_REFUSED,
            "There are no available instances in this region",
        ],
    )
    def test_recognises_the_phrasings(self, text):
        assert _looks_like_capacity(text)

    def test_an_sku_quota_message_is_quota_not_capacity(self):
        # Reads like capacity, is not. Moving region will not fix a quota.
        assert _looks_like_quota("SubscriptionIsOverQuotaForSku")
        assert not _looks_like_capacity("SubscriptionIsOverQuotaForSku")

    def test_does_not_cry_wolf_on_ordinary_errors(self):
        assert not _looks_like_capacity("Error: Unsupported argument on line 12")

    def test_the_message_suggests_other_regions(self):
        message = str(CapacityUnavailable(_error(GATEWAY_TIMEOUT)))
        assert "STRATUS_REGION" in message
        assert "westus2" in message

    def test_it_keeps_what_azure_actually_said(self):
        # Our interpretation could be wrong; the original has to stay visible.
        assert "GatewayTimeout" in str(CapacityUnavailable(_error(GATEWAY_TIMEOUT)))

    def test_it_explains_that_this_is_not_the_user_s_fault(self):
        message = str(CapacityUnavailable(_error(GATEWAY_TIMEOUT)))
        assert "capacity" in message.lower()


QUOTA_REFUSED = (
    'unexpected status 401 (401 Unauthorized) with response: {"Code":'
    '"Unauthorized","Message":"Operation cannot be completed without '
    "additional quota. \\r\\nAdditional details - Location:  \\r\\nCurrent "
    'Limit (Total VMs): 0 \\r\\nCurrent Usage: 0"}'
)


class TestQuota:
    """A free subscription gets an App Service quota of zero. It is reported
    as 401 Unauthorized, which sounds like a login problem and is not."""

    def test_recognises_the_quota_message(self):
        assert _looks_like_quota(QUOTA_REFUSED)

    def test_quota_is_not_mistaken_for_capacity(self):
        # The distinction matters: capacity clears if you move region, a
        # quota of zero does not. Sending someone region-hopping when their
        # limit is zero everywhere wastes their afternoon.
        error = QuotaBlocked(_error(QUOTA_REFUSED))
        assert "Changing region will not help" in str(error)

    def test_it_reads_the_actual_limit_out(self):
        error = QuotaBlocked(_error(QUOTA_REFUSED))
        assert error.quota_name == "Total VMs"
        assert error.quota_limit == "0"

    def test_it_offers_a_way_forward_that_works_today(self):
        # A quota increase takes days. Something buildable now matters more.
        message = str(QuotaBlocked(_error(QUOTA_REFUSED)))
        assert "storage" in message.lower()
        assert "Static Web Apps" in message

    def test_it_says_the_401_is_not_a_login_problem(self):
        message = str(QuotaBlocked(_error(QUOTA_REFUSED)))
        assert "not" in message and "signed in correctly" in message


class TestPromptAvoidsBlockedServices:
    """The model should not generate something the account cannot create."""

    def test_it_is_told_to_avoid_app_service_plans(self):
        from stratus.agent.prompts import SYSTEM_PROMPT

        assert "azurerm_service_plan" in SYSTEM_PROMPT
        assert "quota" in SYSTEM_PROMPT.lower()

    def test_it_is_given_alternatives_for_a_website(self):
        from stratus.agent.prompts import SYSTEM_PROMPT

        assert "azurerm_static_web_app" in SYSTEM_PROMPT
        assert "static_website" in SYSTEM_PROMPT


class TestRegionChoice:
    def test_the_region_is_stated_in_the_request(self):
        message = build_user_message("a website", Snapshot(subscription_id="s"), "uksouth")
        assert "uksouth" in message

    def test_it_defaults_when_not_given(self):
        message = build_user_message("a website", Snapshot(subscription_id="s"))
        assert DEFAULT_REGION in message

    def test_the_region_stays_out_of_the_system_prompt(self):
        # A region in the system prompt would invalidate the cached prefix
        # every time it changed, and would need a code change to move.
        from stratus.agent.prompts import SYSTEM_PROMPT

        assert "eastus" not in SYSTEM_PROMPT

    def test_there_are_alternatives_to_suggest(self):
        assert len(FALLBACK_REGIONS) >= 3
        assert DEFAULT_REGION not in FALLBACK_REGIONS


class TestProgressFiltering:
    """Sixteen silent minutes were indistinguishable from a hang."""

    def _captured(self, *lines: str) -> list[str]:
        seen: list[str] = []
        forward = _progress_filter(seen.append)
        for line in lines:
            forward(line)
        return seen

    def test_passes_on_the_lines_that_show_progress(self):
        seen = self._captured(
            "azurerm_storage_account.s: Creating...",
            "azurerm_storage_account.s: Still creating... [10s elapsed]",
            "azurerm_storage_account.s: Creation complete after 22s",
        )
        assert len(seen) == 3

    def test_drops_the_noise(self):
        seen = self._captured(
            "",
            "Terraform used the selected providers to generate the following",
            "  # azurerm_storage_account.s will be created",
            "Plan: 3 to add, 0 to change, 0 to destroy.",
        )
        assert seen == []

    def test_never_swallows_an_error(self):
        seen = self._captured("Error: creating Service Plan: GatewayTimeout")
        assert len(seen) == 1

    def test_reports_teardown_too(self):
        seen = self._captured(
            "azurerm_resource_group.rg: Destroying...",
            "azurerm_resource_group.rg: Still destroying... [1m0s elapsed]",
            "azurerm_resource_group.rg: Destruction complete after 1m16s",
        )
        assert len(seen) == 3
