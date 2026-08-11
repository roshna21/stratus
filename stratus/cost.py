"""What a plan will cost, and — more importantly — what it might.

The single most useful thing to tell someone on a free tier is not a precise
number. It is which of three categories each thing falls into:

  free          costs nothing to exist and nothing to use
  usage-based   costs nothing to exist; the bill depends on what you do
  fixed         charges every hour it exists, whether used or not

That third category is what empties a free account, and it is invisible on an
approval screen unless something says so.

The rule this module is built around: **never report zero when the answer is
unknown.** A wrong "free" is how someone finds a surprise on a bill, and it
is far worse than admitting ignorance. Anything unrecognised is reported as
unknown, out loud.

Prices come from Azure's public retail price list, which needs no account and
no key. When it cannot be reached the estimate degrades to categories without
numbers, which is still the useful part.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from stratus.models import Action, Plan, PlannedChange

PRICES_URL = "https://prices.azure.com/api/retail/prices"
HOURS_PER_MONTH = 730
CACHE_PATH = Path.home() / ".stratus" / "prices.json"


class Kind(StrEnum):
    FREE = "free"
    USAGE = "usage"
    FIXED = "fixed"
    UNKNOWN = "unknown"


# Things that genuinely cost nothing to exist and nothing to run. Only
# entries verified to be free belong here — a wrong one produces a
# confident, wrong "this is free".
ALWAYS_FREE: dict[str, str] = {
    "azurerm_resource_group": "grouping things together is free",
    "random_string": "not a cloud resource at all",
    "random_password": "not a cloud resource at all",
    "random_id": "not a cloud resource at all",
    "random_integer": "not a cloud resource at all",
    "azurerm_storage_container": "a folder inside storage you already pay for",
    "azurerm_virtual_network": "a private network costs nothing by itself",
    "azurerm_subnet": "part of a network that is already free",
    "azurerm_network_security_group": "firewall rules are free",
    "azurerm_storage_account_static_website": "serving pages from storage adds no fixed charge",
}

# Things with no charge for existing, billed on what you actually use. The
# text says what drives the bill, because "usage-based" alone tells nobody
# whether to worry.
USAGE_BASED: dict[str, str] = {
    "azurerm_storage_account": "about 2 cents per GB stored per month, plus a little per operation",
    "azurerm_storage_blob": "counts towards the storage it lives in",
    "azurerm_log_analytics_workspace": "charged per GB of logs kept",
    "azurerm_application_insights": "charged per GB of data collected",
    "azurerm_container_registry": "charged for storage above the included allowance",
}

# Things that charge continuously. Looked up live where possible; these are
# the fallback when the price list cannot be reached, and are deliberately
# rounded and marked approximate rather than presented as exact.
FIXED_FALLBACK: dict[str, float] = {
    "azurerm_nat_gateway": 32.0,
    "azurerm_lb": 18.0,
    "azurerm_application_gateway": 125.0,
    "azurerm_virtual_network_gateway": 140.0,
    "azurerm_firewall": 600.0,
    "azurerm_public_ip": 3.0,
}

# How to ask the price list about a resource: (serviceName, sku attribute).
PRICED: dict[str, tuple[str, str]] = {
    "azurerm_service_plan": ("Azure App Service", "sku_name"),
    "azurerm_app_service_plan": ("Azure App Service", "sku_name"),
    "azurerm_postgresql_flexible_server": ("Azure Database for PostgreSQL", "sku_name"),
    "azurerm_mysql_flexible_server": ("Azure Database for MySQL", "sku_name"),
}

# Free tiers that would otherwise be priced as if they were paid.
FREE_SKUS = {"F1", "Free", "Y1", "FREE"}


@dataclass
class LineItem:
    resource: str
    kind: Kind
    monthly_usd: float = 0.0
    note: str = ""


@dataclass
class Estimate:
    items: list[LineItem] = field(default_factory=list)
    priced_live: bool = False
    """Whether real prices were fetched, or only categories worked out."""

    @property
    def fixed_monthly(self) -> float:
        return sum(i.monthly_usd for i in self.items if i.kind is Kind.FIXED)

    @property
    def has_fixed_cost(self) -> bool:
        return any(i.kind is Kind.FIXED for i in self.items)

    @property
    def unknowns(self) -> list[LineItem]:
        return [i for i in self.items if i.kind is Kind.UNKNOWN]

    @property
    def usage_based(self) -> list[LineItem]:
        return [i for i in self.items if i.kind is Kind.USAGE]


class PriceBook:
    """Looks up Azure's published prices, and remembers what it found.

    Prices change rarely and the lookup is slow, so results are cached on
    disk. A cache miss with no network is not an error — it produces an
    unknown, which is reported honestly.
    """

    def __init__(self, cache_path: Path | None = None, offline: bool = False):
        self.cache_path = cache_path or CACHE_PATH
        self.offline = offline
        self._cache: dict[str, Any] = self._load()
        self.used_network = False

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.cache_path.read_text())
        except Exception:  # noqa: BLE001 - a missing or corrupt cache is normal
            return {}

    def _save(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self._cache, indent=2))
        except OSError:
            # An unwritable cache slows things down; it does not break them.
            pass

    def hourly(self, service: str, sku: str, region: str) -> float | None:
        """The hourly price, or None when it cannot be established."""
        key = f"{service}|{sku}|{region}"
        if key in self._cache:
            return self._cache[key]
        if self.offline:
            return None

        price = self._fetch(service, sku, region)
        if price is not None:
            self._cache[key] = price
            self._save()
        return price

    def _fetch(self, service: str, sku: str, region: str) -> float | None:
        try:
            import httpx

            response = httpx.get(
                PRICES_URL,
                params={
                    "$filter": (
                        f"armRegionName eq '{region}' and "
                        f"serviceName eq '{service}' and "
                        f"skuName eq '{sku}'"
                    ),
                    "currencyCode": "USD",
                },
                timeout=20,
            )
            self.used_network = True
            items = response.json().get("Items", [])
        except Exception:  # noqa: BLE001 - no network is a normal condition
            return None

        # Consumption prices only. Reservations and spot pricing are cheaper
        # and do not apply to something being created right now, so including
        # them would understate the bill.
        hourly = [
            item["retailPrice"]
            for item in items
            if item.get("type") == "Consumption"
            and "Hour" in str(item.get("unitOfMeasure", ""))
            and item.get("retailPrice", 0) > 0
        ]
        # The cheapest matching meter, since a SKU often has several (Linux
        # and Windows, for instance) and overstating is the safer error only
        # up to a point — an inflated number teaches people to ignore it.
        return min(hourly) if hourly else None


def _sku_of(change: PlannedChange, attribute: str) -> str | None:
    value = (change.after or {}).get(attribute)
    return str(value) if value else None


def estimate(plan: Plan, region: str = "eastus", prices: PriceBook | None = None) -> Estimate:
    """Work out what a plan would add to the monthly bill."""
    book = prices or PriceBook()
    result = Estimate()

    for change in plan.changes:
        if change.action not in (Action.CREATE, Action.REPLACE):
            continue

        type_ = change.type

        if type_ in ALWAYS_FREE:
            result.items.append(LineItem(change.name, Kind.FREE, note=ALWAYS_FREE[type_]))
            continue

        if type_ in USAGE_BASED:
            result.items.append(LineItem(change.name, Kind.USAGE, note=USAGE_BASED[type_]))
            continue

        if type_ in PRICED:
            service, sku_attribute = PRICED[type_]
            sku = _sku_of(change, sku_attribute)

            if sku and sku in FREE_SKUS:
                result.items.append(
                    LineItem(change.name, Kind.FREE, note=f"the {sku} tier is free")
                )
                continue

            if sku:
                hourly = book.hourly(service, sku, region)
                if hourly is not None:
                    result.items.append(
                        LineItem(
                            change.name,
                            Kind.FIXED,
                            monthly_usd=round(hourly * HOURS_PER_MONTH, 2),
                            note=f"the {sku} size, charged for every hour it exists",
                        )
                    )
                    continue

            # Priced in principle, but the price could not be established.
            # Reporting zero here would be a confident lie.
            result.items.append(
                LineItem(
                    change.name,
                    Kind.UNKNOWN,
                    note="charges by the hour; I could not look up the rate",
                )
            )
            continue

        if type_ in FIXED_FALLBACK:
            result.items.append(
                LineItem(
                    change.name,
                    Kind.FIXED,
                    monthly_usd=FIXED_FALLBACK[type_],
                    note="charged continuously, whether used or not (approximate)",
                )
            )
            continue

        result.items.append(
            LineItem(change.name, Kind.UNKNOWN, note="I don't have pricing for this")
        )

    result.priced_live = book.used_network
    return result


def describe(estimate: Estimate) -> str:
    """The cost line shown above the approval question."""
    if not estimate.items:
        return ""

    lines: list[str] = []

    if estimate.has_fixed_cost:
        total = estimate.fixed_monthly
        lines.append(f"This will add about ${total:.2f} a month, every month:")
        for item in estimate.items:
            if item.kind is Kind.FIXED:
                lines.append(f"  - {item.resource}: ${item.monthly_usd:.2f} — {item.note}")
    else:
        lines.append("Nothing here has a fixed monthly charge.")

    if estimate.usage_based:
        lines.append("")
        lines.append("These cost nothing to exist, and bill on what you use:")
        for item in estimate.usage_based:
            lines.append(f"  - {item.resource}: {item.note}")

    if estimate.unknowns:
        # Said plainly rather than folded into the total as zero. An unknown
        # reported as free is how someone gets a surprise.
        lines.append("")
        lines.append("I could not work out the cost of these:")
        for item in estimate.unknowns:
            lines.append(f"  - {item.resource}: {item.note}")

    return "\n".join(lines)
