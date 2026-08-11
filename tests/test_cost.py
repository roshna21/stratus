"""Tests for cost estimation.

The rule everything here protects: never report zero when the answer is
unknown. A wrong "this is free" is how someone finds a surprise on a bill,
and it is far worse than admitting ignorance.

All offline. A test that reaches Azure's price list would be slow, would fail
on a train, and would change its answer when Microsoft changes a price.
"""

from __future__ import annotations

import json

import pytest

from stratus.cost import Kind, PriceBook, describe, estimate
from stratus.models import Action, Plan, PlannedChange


def _change(type_: str, name: str = "thing", action=Action.CREATE, **after) -> PlannedChange:
    return PlannedChange(
        address=f"{type_}.{name}", type=type_, name=name, action=action, after=after
    )


def _plan(*changes: PlannedChange) -> Plan:
    return Plan(changes=list(changes))


@pytest.fixture
def offline(tmp_path) -> PriceBook:
    """A price book that never touches the network."""
    return PriceBook(cache_path=tmp_path / "prices.json", offline=True)


@pytest.fixture
def cached(tmp_path) -> PriceBook:
    """A price book with a known price already in its cache."""
    path = tmp_path / "prices.json"
    path.write_text(json.dumps({"Azure App Service|B1|eastus": 0.017}))
    return PriceBook(cache_path=path, offline=True)


class TestCategories:
    def test_a_resource_group_is_free(self, offline):
        result = estimate(_plan(_change("azurerm_resource_group", "rg")), prices=offline)
        assert result.items[0].kind is Kind.FREE

    def test_storage_bills_on_usage_not_existence(self, offline):
        # The distinction that matters on a free tier: an empty storage
        # account costs nothing, so calling it "a cost" would be wrong.
        result = estimate(_plan(_change("azurerm_storage_account", "data")), prices=offline)
        assert result.items[0].kind is Kind.USAGE
        assert not result.has_fixed_cost

    def test_the_usage_note_says_what_drives_the_bill(self, offline):
        # "Usage-based" alone tells nobody whether to worry.
        result = estimate(_plan(_change("azurerm_storage_account", "data")), prices=offline)
        assert "per GB" in result.items[0].note

    def test_a_gateway_charges_continuously(self, offline):
        result = estimate(_plan(_change("azurerm_nat_gateway", "gw")), prices=offline)
        assert result.items[0].kind is Kind.FIXED
        assert result.fixed_monthly == pytest.approx(32.0)


class TestUnknownIsNotFree:
    """The rule the whole module is built around."""

    def test_an_unrecognised_resource_is_unknown_not_free(self, offline):
        result = estimate(_plan(_change("azurerm_cognitive_account", "ai")), prices=offline)
        assert result.items[0].kind is Kind.UNKNOWN
        assert result.items[0].kind is not Kind.FREE

    def test_an_unknown_never_lands_in_the_total(self, offline):
        result = estimate(_plan(_change("azurerm_cognitive_account", "ai")), prices=offline)
        assert result.fixed_monthly == 0.0
        assert result.unknowns

    def test_a_priced_resource_with_no_price_available_is_unknown(self, offline):
        # It charges hourly and we could not find the rate. Reporting zero
        # here would be a confident lie.
        result = estimate(
            _plan(_change("azurerm_service_plan", "plan", sku_name="P1v3")), prices=offline
        )
        assert result.items[0].kind is Kind.UNKNOWN
        assert "could not look up" in result.items[0].note

    def test_the_summary_says_so_out_loud(self, offline):
        text = describe(estimate(_plan(_change("azurerm_cognitive_account", "ai")), prices=offline))
        assert "could not work out the cost" in text


class TestPricedResources:
    def test_uses_a_cached_price(self, cached):
        result = estimate(
            _plan(_change("azurerm_service_plan", "plan", sku_name="B1")), prices=cached
        )
        assert result.items[0].kind is Kind.FIXED
        # 0.017 an hour across 730 hours.
        assert result.fixed_monthly == pytest.approx(12.41, abs=0.01)

    def test_a_free_tier_is_free_without_a_lookup(self, offline):
        # F1 costs nothing, and asking the price list would return a number
        # for the paid meters of the same service.
        result = estimate(
            _plan(_change("azurerm_service_plan", "plan", sku_name="F1")), prices=offline
        )
        assert result.items[0].kind is Kind.FREE
        assert "free" in result.items[0].note

    def test_caches_what_it_looked_up(self, tmp_path):
        path = tmp_path / "prices.json"
        path.write_text(json.dumps({"Azure App Service|B1|eastus": 0.017}))
        book = PriceBook(cache_path=path, offline=True)
        assert book.hourly("Azure App Service", "B1", "eastus") == 0.017
        assert book.used_network is False

    def test_a_missing_cache_file_is_not_an_error(self, tmp_path):
        book = PriceBook(cache_path=tmp_path / "nope.json", offline=True)
        assert book.hourly("Azure App Service", "B1", "eastus") is None

    def test_a_corrupt_cache_file_is_not_an_error(self, tmp_path):
        path = tmp_path / "prices.json"
        path.write_text("{not json")
        assert PriceBook(cache_path=path, offline=True)._cache == {}


class TestScope:
    def test_ignores_deletions(self, offline):
        # Removing something does not add to the bill.
        result = estimate(
            _plan(_change("azurerm_nat_gateway", "gw", action=Action.DELETE)), prices=offline
        )
        assert result.items == []

    def test_ignores_unchanged_resources(self, offline):
        result = estimate(
            _plan(_change("azurerm_nat_gateway", "gw", action=Action.NO_OP)), prices=offline
        )
        assert result.items == []

    def test_counts_replacements(self, offline):
        result = estimate(
            _plan(_change("azurerm_nat_gateway", "gw", action=Action.REPLACE)), prices=offline
        )
        assert result.has_fixed_cost


class TestSummary:
    def test_says_plainly_when_there_is_no_fixed_charge(self, offline):
        result = estimate(_plan(_change("azurerm_storage_account", "data")), prices=offline)
        assert "Nothing here has a fixed monthly charge" in describe(result)

    def test_leads_with_the_monthly_figure(self, offline):
        text = describe(estimate(_plan(_change("azurerm_nat_gateway", "gw")), prices=offline))
        assert text.startswith("This will add about $32.00 a month")

    def test_says_every_month(self, offline):
        # The word people miss. A one-off charge and a recurring one read the
        # same on an approval screen unless it is spelled out.
        text = describe(estimate(_plan(_change("azurerm_nat_gateway", "gw")), prices=offline))
        assert "every month" in text

    def test_separates_fixed_from_usage_based(self, offline):
        result = estimate(
            _plan(
                _change("azurerm_nat_gateway", "gw"),
                _change("azurerm_storage_account", "data"),
            ),
            prices=offline,
        )
        text = describe(result)
        assert "every month" in text
        assert "bill on what you use" in text

    def test_nothing_to_say_about_an_empty_plan(self, offline):
        assert describe(estimate(Plan(changes=[]), prices=offline)) == ""

    def test_a_free_build_reads_reassuringly(self, offline):
        # The successful build from earlier: storage static website.
        result = estimate(
            _plan(
                _change("azurerm_resource_group", "rg"),
                _change("random_string", "suffix"),
                _change("azurerm_storage_account", "website"),
                _change("azurerm_storage_container", "uploads"),
            ),
            prices=offline,
        )
        text = describe(result)
        assert "Nothing here has a fixed monthly charge" in text
        assert not result.unknowns
