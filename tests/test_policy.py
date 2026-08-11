"""Tests for the safety rules.

The person asking for infrastructure does not know a storage container can be
world-readable, or that open SSH is found by scanners within minutes. These
rules are the whole of what stands between a plain-English request and a
result that leaks data or bills quietly.

Every rule is tested for both directions: that it fires on the dangerous
setting, and that it stays quiet on the safe one. A rule that fires on
everything gets switched off, which is worse than not having it.
"""

from __future__ import annotations

import pytest

from stratus.models import Action, Plan, PlannedChange
from stratus.policy import describe_warnings, explain_block, review


def _change(type_: str, name: str = "thing", action=Action.CREATE, **after) -> PlannedChange:
    return PlannedChange(
        address=f"{type_}.{name}",
        type=type_,
        name=name,
        action=action,
        after=after or {"name": name},
    )


def _review(*changes: PlannedChange):
    return review(Plan(changes=list(changes)))


class TestPublicStorage:
    """The classic cloud data leak."""

    @pytest.mark.parametrize("access", ["blob", "container"])
    def test_blocks_a_world_readable_container(self, access):
        result = _review(
            _change("azurerm_storage_container", "uploads", container_access_type=access)
        )
        assert result.is_blocked
        assert "read the files" in result.blocked[0].problem

    def test_allows_a_private_container(self):
        result = _review(
            _change("azurerm_storage_container", "uploads", container_access_type="private")
        )
        assert not result.is_blocked

    def test_treats_a_missing_setting_as_private(self):
        # Azure's default is private, and assuming the worst here would block
        # every ordinary container.
        assert not _review(_change("azurerm_storage_container", "uploads")).is_blocked

    def test_blocks_an_account_that_permits_public_contents(self):
        result = _review(
            _change("azurerm_storage_account", "data", allow_nested_items_to_be_public=True)
        )
        assert result.is_blocked


class TestEncryption:
    def test_blocks_unencrypted_transfer(self):
        result = _review(
            _change("azurerm_storage_account", "data", https_traffic_only_enabled=False)
        )
        assert result.is_blocked
        assert "watch the network" in result.blocked[0].problem

    def test_checks_the_older_attribute_name_too(self):
        # The provider renamed this between major versions. A rule that
        # silently stops applying after an upgrade is worse than no rule.
        result = _review(
            _change("azurerm_storage_account", "data", enable_https_traffic_only=False)
        )
        assert result.is_blocked

    def test_allows_encrypted_transfer(self):
        result = _review(
            _change("azurerm_storage_account", "data", https_traffic_only_enabled=True)
        )
        assert not result.is_blocked

    @pytest.mark.parametrize("version", ["TLS1_0", "TLS1_1"])
    def test_warns_about_outdated_encryption(self, version):
        result = _review(_change("azurerm_storage_account", "data", min_tls_version=version))
        assert not result.is_blocked  # a warning, not a refusal
        assert result.warnings

    def test_accepts_current_encryption(self):
        result = _review(_change("azurerm_storage_account", "d", min_tls_version="TLS1_2"))
        assert not result.warnings


class TestOpenAdminPorts:
    def _rule(self, **overrides):
        settings = {
            "access": "Allow",
            "direction": "Inbound",
            "source_address_prefix": "*",
            "destination_port_range": "22",
        }
        settings.update(overrides)
        return _change("azurerm_network_security_rule", "ssh", **settings)

    def test_blocks_ssh_open_to_everyone(self):
        result = _review(self._rule())
        assert result.is_blocked
        assert "SSH" in result.blocked[0].problem

    def test_blocks_remote_desktop_too(self):
        assert _review(self._rule(destination_port_range="3389")).is_blocked

    def test_blocks_every_port_open(self):
        assert _review(self._rule(destination_port_range="*")).is_blocked

    @pytest.mark.parametrize("source", ["0.0.0.0/0", "Internet", "any"])
    def test_recognises_the_other_ways_of_saying_everyone(self, source):
        assert _review(self._rule(source_address_prefix=source)).is_blocked

    def test_allows_ssh_from_a_specific_address(self):
        assert not _review(self._rule(source_address_prefix="203.0.113.4")).is_blocked

    def test_ignores_a_deny_rule(self):
        # A deny rule mentioning port 22 is the opposite of a problem.
        assert not _review(self._rule(access="Deny")).is_blocked

    def test_ignores_outbound_rules(self):
        assert not _review(self._rule(direction="Outbound")).is_blocked

    def test_allows_ordinary_web_ports_from_anywhere(self):
        # A website open to the internet is the entire point of a website.
        assert not _review(self._rule(destination_port_range="443")).is_blocked


class TestCost:
    """Things that quietly bill a free account into the ground."""

    @pytest.mark.parametrize(
        "type_", ["azurerm_nat_gateway", "azurerm_application_gateway", "azurerm_lb"]
    )
    def test_blocks_expensive_infrastructure(self, type_):
        result = _review(_change(type_, "gw"))
        assert result.is_blocked
        assert "month" in result.blocked[0].problem

    def test_the_message_says_what_it_costs(self):
        # "Blocked for cost reasons" is not actionable. A number is.
        result = _review(_change("azurerm_nat_gateway", "gw"))
        assert "$32" in result.blocked[0].problem

    def test_warns_about_a_paid_size(self):
        result = _review(_change("azurerm_service_plan", "plan", sku_name="P1v3"))
        assert result.warnings
        assert not result.is_blocked

    def test_says_nothing_about_a_free_size(self):
        assert not _review(_change("azurerm_service_plan", "plan", sku_name="F1")).warnings


class TestExposedData:
    def test_warns_when_a_database_faces_the_internet(self):
        result = _review(
            _change(
                "azurerm_postgresql_flexible_server", "db", public_network_access_enabled=True
            )
        )
        assert result.warnings
        assert "internet" in result.warnings[0].problem

    def test_quiet_when_a_database_is_private(self):
        result = _review(
            _change(
                "azurerm_postgresql_flexible_server", "db", public_network_access_enabled=False
            )
        )
        assert not result.warnings


class TestScope:
    def test_ignores_deletions(self):
        # A deletion cannot introduce an insecure setting, and flagging one
        # would stop a user cleaning up something the rules dislike.
        result = _review(
            _change(
                "azurerm_storage_container",
                "old",
                action=Action.DELETE,
                container_access_type="container",
            )
        )
        assert not result.is_blocked

    def test_ignores_unchanged_resources(self):
        result = _review(
            _change(
                "azurerm_storage_container",
                "existing",
                action=Action.NO_OP,
                container_access_type="container",
            )
        )
        assert not result.is_blocked

    def test_checks_replacements(self):
        # A replacement creates something new, so its settings matter.
        result = _review(
            _change(
                "azurerm_storage_container",
                "rebuilt",
                action=Action.REPLACE,
                container_access_type="blob",
            )
        )
        assert result.is_blocked

    def test_a_safe_plan_passes_cleanly(self):
        result = _review(
            _change("azurerm_resource_group", "rg"),
            _change("azurerm_storage_account", "data", https_traffic_only_enabled=True),
            _change("azurerm_storage_container", "files", container_access_type="private"),
        )
        assert not result.is_blocked
        assert not result.warnings


class TestMessages:
    def test_the_refusal_tells_the_model_what_to_do_instead(self):
        # This text goes back to the generator, not the user, so it has to be
        # an instruction rather than a complaint.
        result = _review(
            _change("azurerm_storage_container", "uploads", container_access_type="blob")
        )
        text = explain_block(result)
        assert "Instead:" in text
        assert "corrected configuration" in text

    def test_warnings_are_written_for_a_person(self):
        result = _review(_change("azurerm_service_plan", "p", sku_name="P1v3"))
        text = describe_warnings(result)
        assert "Worth knowing" in text
        assert "azurerm_" not in text

    def test_no_warning_text_when_there_is_nothing_to_say(self):
        assert describe_warnings(_review(_change("azurerm_resource_group", "rg"))) == ""

    def test_violations_name_the_resource_the_user_would_recognise(self):
        result = _review(
            _change(
                "azurerm_storage_container", "customer-uploads", container_access_type="blob"
            )
        )
        assert "customer-uploads" in result.blocked[0].problem
