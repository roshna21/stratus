"""Rules about what Stratus is allowed to build.

The person asking for infrastructure does not know that a storage container
can be world-readable, or that leaving SSH open to the internet gets a machine
compromised within hours. They asked for somewhere to keep files. Everything
between that sentence and a safe result is Stratus's job.

These rules read the *plan*, not the generated text. Matching on configuration
text looks easier and is wrong: the same setting can be written several ways,
can come from a variable or a default, and a rule that greps for a string will
miss all of those while claiming everything is fine. The plan holds the values
Terraform actually resolved, which is what will really exist.

A blocked plan is not shown to the user for approval at all. There is no
override, deliberately — a safety gate with a bypass is a suggestion, and the
whole point is that the user should not have to know these rules exist.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from stratus.models import Action, Plan, PlannedChange


class Severity(StrEnum):
    BLOCK = "block"
    """Refuse to build. Reserved for things that expose data to strangers or
    cost real money without being asked for."""

    WARN = "warn"
    """Build it, but say so. For things that are defensible choices but worth
    knowing about."""


@dataclass(frozen=True)
class Violation:
    rule: str
    severity: Severity
    resource: str
    problem: str
    """What is wrong, in words the person who made the request would follow."""
    fix: str
    """What should happen instead."""


def _after(change: PlannedChange, key: str, default: Any = None) -> Any:
    return (change.after or {}).get(key, default)


def _is_being_made(change: PlannedChange) -> bool:
    """Only inspect things about to exist.

    A deletion cannot introduce an insecure setting, and flagging one would
    stop a user cleaning up something the rules dislike — which is backwards.
    """
    return change.action in (Action.CREATE, Action.UPDATE, Action.REPLACE)


# --- the rules -------------------------------------------------------------


def public_storage_container(change: PlannedChange) -> Violation | None:
    """A container anyone on the internet can read.

    The classic cloud data leak. Azure calls the setting "blob" or "container"
    access, neither of which sounds like "the whole internet can read this".
    """
    if change.type != "azurerm_storage_container":
        return None
    access = _after(change, "container_access_type", "private")
    if access in ("blob", "container"):
        return Violation(
            rule="public-storage-container",
            severity=Severity.BLOCK,
            resource=change.name,
            problem=(
                "anyone on the internet would be able to read the files in "
                f"'{change.name}' without signing in"
            ),
            fix="keep it private, and grant access deliberately when needed",
        )
    return None


def publicly_readable_storage_account(change: PlannedChange) -> Violation | None:
    """The account-level switch that permits public containers at all."""
    if change.type != "azurerm_storage_account":
        return None
    if _after(change, "allow_nested_items_to_be_public") is True:
        return Violation(
            rule="public-storage-account",
            severity=Severity.BLOCK,
            resource=change.name,
            problem=(f"'{change.name}' would allow its contents to be made public"),
            fix="turn public access off at the account level",
        )
    return None


def unencrypted_transfer(change: PlannedChange) -> Violation | None:
    """Data readable by anyone able to watch the network."""
    if change.type != "azurerm_storage_account":
        return None

    # The attribute was renamed between provider versions. Both are checked
    # because a rule that silently stops applying after an upgrade is worse
    # than no rule.
    https_only = _after(change, "https_traffic_only_enabled")
    if https_only is None:
        https_only = _after(change, "enable_https_traffic_only")

    if https_only is False:
        return Violation(
            rule="unencrypted-transfer",
            severity=Severity.BLOCK,
            resource=change.name,
            problem=(
                f"files going to and from '{change.name}' could be read by "
                "anyone able to watch the network"
            ),
            fix="require encrypted connections",
        )

    tls = _after(change, "min_tls_version")
    if tls and tls in ("TLS1_0", "TLS1_1"):
        return Violation(
            rule="outdated-encryption",
            severity=Severity.WARN,
            resource=change.name,
            problem=f"'{change.name}' allows an outdated form of encryption",
            fix="require TLS 1.2 or newer",
        )
    return None


OPEN_TO_WORLD = {"*", "0.0.0.0/0", "Internet", "any"}
ADMIN_PORTS = {"22": "SSH", "3389": "remote desktop", "*": "every port"}


def admin_port_open_to_the_world(change: PlannedChange) -> Violation | None:
    """A door onto the internet with a lock anyone can pick.

    A machine with SSH open to every address is found by automated scanners
    within minutes and attacked continuously from then on.
    """
    if change.type != "azurerm_network_security_rule":
        return None
    if str(_after(change, "access", "")).lower() != "allow":
        return None
    if str(_after(change, "direction", "")).lower() != "inbound":
        return None

    source = str(_after(change, "source_address_prefix", ""))
    if source not in OPEN_TO_WORLD:
        return None

    port = str(_after(change, "destination_port_range", ""))
    if port in ADMIN_PORTS:
        return Violation(
            rule="admin-port-open",
            severity=Severity.BLOCK,
            resource=change.name,
            problem=(
                f"'{change.name}' would let anyone on the internet reach "
                f"{ADMIN_PORTS[port]}, which automated attacks find within "
                "minutes"
            ),
            fix="allow only the addresses that genuinely need it",
        )
    return None


PUBLIC_DATA_SERVICES = {
    "azurerm_postgresql_flexible_server": "database",
    "azurerm_mysql_flexible_server": "database",
    "azurerm_mssql_server": "database",
    "azurerm_cosmosdb_account": "database",
    "azurerm_key_vault": "secret store",
}


def database_open_to_the_internet(change: PlannedChange) -> Violation | None:
    if change.type not in PUBLIC_DATA_SERVICES:
        return None
    if _after(change, "public_network_access_enabled") is True:
        kind = PUBLIC_DATA_SERVICES[change.type]
        return Violation(
            rule="public-database",
            severity=Severity.WARN,
            resource=change.name,
            problem=(
                f"the {kind} '{change.name}' would be reachable from the "
                "internet rather than only from your own services"
            ),
            fix="restrict it to your private network unless you need outside access",
        )
    return None


COSTLY = {
    "azurerm_nat_gateway": ("a network gateway", "about $32 a month, even when idle"),
    "azurerm_application_gateway": ("an application gateway", "well over $100 a month"),
    "azurerm_lb": ("a load balancer", "about $18 a month"),
    "azurerm_virtual_network_gateway": ("a VPN gateway", "well over $100 a month"),
    "azurerm_firewall": ("a managed firewall", "several hundred a month"),
}


def expensive_and_unrequested(change: PlannedChange) -> Violation | None:
    """Things that quietly bill a free-tier account into the ground.

    Blocked rather than warned. These appear because a model reached for a
    textbook architecture, not because anyone asked, and the person approving
    has no way to know that one line means thirty dollars a month forever.
    """
    if change.type not in COSTLY:
        return None
    what, cost = COSTLY[change.type]
    return Violation(
        rule="expensive-resource",
        severity=Severity.BLOCK,
        resource=change.name,
        problem=f"this includes {what}, which costs {cost}",
        fix="leave it out unless you specifically need it",
    )


def premium_tier(change: PlannedChange) -> Violation | None:
    """A costly size where a free or cheap one was clearly intended."""
    for key in ("sku_name", "sku", "account_tier", "size"):
        value = str(_after(change, key, ""))
        if value and any(
            marker in value for marker in ("Premium", "P1", "P2", "P3", "Standard_D", "GP_")
        ):
            return Violation(
                rule="premium-tier",
                severity=Severity.WARN,
                resource=change.name,
                problem=f"'{change.name}' uses a paid size ({value}) rather than a free one",
                fix="use the smallest size unless you need the capacity",
            )
    return None


RULES: list[Callable[[PlannedChange], Violation | None]] = [
    public_storage_container,
    publicly_readable_storage_account,
    unencrypted_transfer,
    admin_port_open_to_the_world,
    database_open_to_the_internet,
    expensive_and_unrequested,
    premium_tier,
]


# --- running them ----------------------------------------------------------


@dataclass
class Review:
    violations: list[Violation]

    @property
    def blocked(self) -> list[Violation]:
        return [v for v in self.violations if v.severity is Severity.BLOCK]

    @property
    def warnings(self) -> list[Violation]:
        return [v for v in self.violations if v.severity is Severity.WARN]

    @property
    def is_blocked(self) -> bool:
        return bool(self.blocked)


def review(plan: Plan) -> Review:
    """Check every resource a plan would create or change."""
    found: list[Violation] = []
    for change in plan.changes:
        if not _is_being_made(change):
            continue
        for rule in RULES:
            violation = rule(change)
            if violation:
                found.append(violation)
    return Review(violations=found)


def explain_block(review: Review) -> str:
    """Why a plan was refused, for the model to correct.

    Written as instructions rather than complaints, because this text goes
    back to the generator, not to the user. It has to say what to do
    differently, not merely what was wrong.
    """
    lines = ["This configuration was refused for these reasons:", ""]
    for violation in review.blocked:
        lines.append(f"- {violation.resource}: {violation.problem}")
        lines.append(f"  Instead: {violation.fix}")
    lines.append("")
    lines.append("Return a corrected configuration that avoids all of these.")
    return "\n".join(lines)


def describe_warnings(review: Review) -> str:
    """Warnings for the user, shown alongside the approval question."""
    if not review.warnings:
        return ""
    lines = ["Worth knowing:"]
    for violation in review.warnings:
        lines.append(f"  - {violation.problem}")
    return "\n".join(lines)
