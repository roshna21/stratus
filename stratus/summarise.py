"""Turning a snapshot into something a person can read.

The whole premise of Stratus is that the user never sees infrastructure
jargon. That promise starts here: Azure's own vocabulary
("Microsoft.DBforPostgreSQL/flexibleServers") never reaches the screen.

This is deliberately plain Python with no AI involved. A language model is
the right tool for open-ended writing, but "count the resources and name
them" is a fixed job — doing it in code makes it instant, free, and identical
every time.
"""

from __future__ import annotations

from stratus.models import Origin, Snapshot

# Azure's type strings translated into words a person would actually use.
# Unknown types fall back to a readable version of the raw string rather than
# being hidden, so an unfamiliar resource is never silently dropped from a
# summary the user is about to make decisions from.
FRIENDLY_NAMES: dict[str, tuple[str, str]] = {
    "Microsoft.Storage/storageAccounts": ("storage account", "storage accounts"),
    "Microsoft.Web/sites": ("web app", "web apps"),
    "Microsoft.Web/serverfarms": ("hosting plan", "hosting plans"),
    "Microsoft.Compute/virtualMachines": ("virtual machine", "virtual machines"),
    "Microsoft.DBforPostgreSQL/flexibleServers": (
        "PostgreSQL database",
        "PostgreSQL databases",
    ),
    "Microsoft.DBforMySQL/flexibleServers": ("MySQL database", "MySQL databases"),
    "Microsoft.Sql/servers": ("SQL server", "SQL servers"),
    "Microsoft.Network/virtualNetworks": ("private network", "private networks"),
    "Microsoft.Network/networkSecurityGroups": ("firewall rule set", "firewall rule sets"),
    "Microsoft.Network/publicIPAddresses": ("public IP address", "public IP addresses"),
    "Microsoft.Network/dnsZones": ("DNS zone", "DNS zones"),
    "Microsoft.KeyVault/vaults": ("secret store", "secret stores"),
    "Microsoft.ContainerRegistry/registries": ("container registry", "container registries"),
    "Microsoft.Insights/components": ("monitoring service", "monitoring services"),
}


def friendly_type(azure_type: str, plural: bool = False) -> str:
    """Translate one Azure type string into everyday words."""
    if azure_type in FRIENDLY_NAMES:
        return FRIENDLY_NAMES[azure_type][1 if plural else 0]

    # Unknown type: "Microsoft.Foo/barWidgets" -> "bar widget".
    tail = azure_type.split("/")[-1]
    spaced = "".join(f" {c.lower()}" if c.isupper() else c for c in tail).strip()
    if plural:
        return spaced
    # Best-effort singular for the common "-s" plural the API uses.
    return spaced[:-1] if spaced.endswith("s") and not spaced.endswith("ss") else spaced


def summarise(snapshot: Snapshot) -> str:
    """Describe a whole account in plain English."""
    if len(snapshot) == 0:
        return "This account is empty — there's nothing in it yet."

    lines: list[str] = []
    total = len(snapshot)
    lines.append(f"You have {total} {'thing' if total == 1 else 'things'} in this account:")
    lines.append("")

    counts = snapshot.count_by_type()
    for azure_type, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        label = friendly_type(azure_type, plural=count != 1)
        lines.append(f"  {count} x {label}")

    # Who is responsible for what. This is the distinction that governs how
    # cautious the agent has to be later, so the user should see it early.
    managed = [r for r in snapshot.resources if r.origin is Origin.MANAGED]
    discovered = [r for r in snapshot.resources if r.origin is Origin.DISCOVERED]

    lines.append("")
    if managed and discovered:
        lines.append(
            f"{len(managed)} of these were set up by me, and {len(discovered)} "
            "were already here before I arrived. I'll treat the ones I didn't "
            "create as off-limits unless you tell me otherwise."
        )
    elif managed:
        lines.append("I set all of these up, so I can safely change them.")
    else:
        lines.append(
            "None of these were set up by me, so I'll leave them alone unless "
            "you specifically ask me to change something."
        )

    # Grouping, because "everything in one bucket" vs "spread across five" is
    # the first thing a person wants to know about an unfamiliar account.
    groups = sorted({r.resource_group for r in snapshot.resources if r.resource_group})
    if len(groups) > 1:
        lines.append("")
        lines.append(f"They're organised into {len(groups)} groups: {', '.join(groups)}.")

    return "\n".join(lines)
