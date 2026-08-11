"""Describing a plan in plain English, so a person can approve it.

This is the moment the whole product either works or does not. Everything
before it happens out of sight; this is the one screen the user reads, and
what they consent to is whatever this text says. If it is unclear, or if it
buries something destructive under something routine, then their "yes" did
not mean what we treated it as meaning.

No language model is involved. A model would produce nicer prose and would
occasionally describe the plan wrongly, and a wrong description here is the
worst bug this project could have. Counting changes and naming them is a
fixed job, so it is done in code: instant, free, and identical every time.
"""

from __future__ import annotations

from stratus.models import Action, Plan, PlannedChange

# Terraform type -> (singular, plural, is_supporting)
#
# "Supporting" means infrastructure that exists only to make something else
# work — a group to organise resources, a plan to host a website, a generator
# for a random suffix. Nobody asks for these; they come along for the ride.
# Listing them beside the thing the user actually wanted makes a simple
# request look alarming, so they are counted rather than named.
FRIENDLY: dict[str, tuple[str, str, bool]] = {
    # Things people actually ask for
    "azurerm_storage_account": ("place to keep files", "places to keep files", False),
    "azurerm_storage_container": ("folder", "folders", False),
    "azurerm_linux_web_app": ("website", "websites", False),
    "azurerm_windows_web_app": ("website", "websites", False),
    "azurerm_static_site": ("website", "websites", False),
    "azurerm_linux_virtual_machine": ("virtual computer", "virtual computers", False),
    "azurerm_windows_virtual_machine": ("virtual computer", "virtual computers", False),
    "azurerm_postgresql_flexible_server": ("database", "databases", False),
    "azurerm_mysql_flexible_server": ("database", "databases", False),
    "azurerm_mssql_server": ("database server", "database servers", False),
    "azurerm_cosmosdb_account": ("database", "databases", False),
    "azurerm_container_registry": ("container store", "container stores", False),
    "azurerm_key_vault": ("secret store", "secret stores", False),
    "azurerm_dns_zone": ("domain name setup", "domain name setups", False),
    # Plumbing
    "azurerm_resource_group": ("group", "groups", True),
    "azurerm_service_plan": ("hosting plan", "hosting plans", True),
    "azurerm_app_service_plan": ("hosting plan", "hosting plans", True),
    "azurerm_virtual_network": ("private network", "private networks", True),
    "azurerm_subnet": ("network section", "network sections", True),
    "azurerm_network_interface": ("network connection", "network connections", True),
    "azurerm_network_security_group": ("firewall", "firewalls", True),
    "azurerm_public_ip": ("public address", "public addresses", True),
    "azurerm_postgresql_flexible_server_database": ("database", "databases", True),
    "random_string": ("random name", "random names", True),
    "random_password": ("generated password", "generated passwords", True),
    "random_id": ("random name", "random names", True),
}

# Things that hold data. Destroying one loses whatever was in it, and that
# has to be said out loud rather than left for the user to infer.
HOLDS_DATA = {
    "azurerm_storage_account",
    "azurerm_storage_container",
    "azurerm_postgresql_flexible_server",
    "azurerm_mysql_flexible_server",
    "azurerm_mssql_server",
    "azurerm_cosmosdb_account",
    "azurerm_key_vault",
    "azurerm_managed_disk",
}


def describe(type_: str, plural: bool = False) -> str:
    """One resource type in everyday words."""
    if type_ in FRIENDLY:
        singular, plural_form, _ = FRIENDLY[type_]
        return plural_form if plural else singular

    # Unknown type: "azurerm_cognitive_account" -> "cognitive account".
    # Shown rather than hidden — a resource the user is not told about is a
    # change they did not agree to.
    words = type_.removeprefix("azurerm_").removeprefix("azuread_").replace("_", " ")
    return words + "s" if plural else words


def is_supporting(type_: str) -> bool:
    """Whether this exists only to make something else work."""
    return FRIENDLY.get(type_, ("", "", False))[2]


def _name(change: PlannedChange) -> str:
    """The most human-recognisable name for one resource."""
    for source in (change.after, change.before):
        if source and isinstance(source.get("name"), str):
            return source["name"]
    return change.name


def _group(changes: list[PlannedChange]) -> tuple[list[str], int]:
    """Split changes into named primary items and a count of plumbing."""
    primary: list[str] = []
    supporting = 0

    for change in changes:
        if is_supporting(change.type):
            supporting += 1
        else:
            primary.append(f"{describe(change.type)} ({_name(change)})")

    return primary, supporting


def _bullet_list(items: list[str], supporting: int) -> list[str]:
    lines = [f"  - {item}" for item in items]
    if supporting:
        thing = "supporting piece" if supporting == 1 else "supporting pieces"
        lines.append(f"  - plus {supporting} {thing} needed to make that work")
    return lines


def explain(plan: Plan) -> str:
    """Describe a plan for a person about to approve or reject it."""
    if plan.is_empty:
        return (
            "Nothing needs to change — you already have everything you asked "
            "for. I haven't touched anything."
        )

    creates = plan.of(Action.CREATE)
    updates = plan.of(Action.UPDATE)
    deletes = plan.of(Action.DELETE)
    replaces = plan.of(Action.REPLACE)

    lines: list[str] = []

    # Destructive changes go first and unmissably. Putting them after a list
    # of harmless creations is how someone approves a deletion by accident.
    if deletes or replaces:
        lines.append("!! THIS WILL DESTROY THINGS. Please read carefully. !!")
        lines.append("")

    if deletes:
        count = len(deletes)
        lines.append(f"Deleting {count} {'thing' if count == 1 else 'things'}:")
        for change in deletes:
            warning = (
                "  <- everything stored in it will be lost, permanently"
                if change.type in HOLDS_DATA
                else ""
            )
            lines.append(f"  - {describe(change.type)} ({_name(change)}){warning}")
        lines.append("")

    if replaces:
        count = len(replaces)
        lines.append(
            f"Destroying and rebuilding {count} {'thing' if count == 1 else 'things'}:"
        )
        for change in replaces:
            warning = (
                "  <- the replacement starts empty; current contents are lost"
                if change.type in HOLDS_DATA
                else "  <- it will be unavailable while this happens"
            )
            lines.append(f"  - {describe(change.type)} ({_name(change)}){warning}")
        lines.append("")

    if creates:
        primary, supporting = _group(creates)
        if primary:
            lines.append("Creating:")
            lines.extend(_bullet_list(primary, supporting))
        else:
            # Everything being built is plumbing, which is unusual but real —
            # say so rather than printing an empty heading.
            count = len(creates)
            lines.append(
                f"Creating {count} supporting "
                f"{'piece' if count == 1 else 'pieces'} of infrastructure."
            )
        lines.append("")

    if updates:
        primary, supporting = _group(updates)
        lines.append("Changing settings on:")
        lines.extend(
            _bullet_list(primary, supporting)
            if primary
            else [f"  - {supporting} supporting piece(s)"]
        )
        lines.append("")

    if not deletes and not replaces:
        lines.append("Nothing existing will be changed or deleted.")
        lines.append("")

    lines.append(_question(plan))
    return "\n".join(lines)


def _question(plan: Plan) -> str:
    """The approval prompt.

    A destructive plan asks for a typed word rather than "y". Pressing y is
    reflexive; typing DELETE is not, and that difference is the entire point
    of the gate.
    """
    if plan.is_destructive:
        return "To go ahead, type exactly:  DELETE\nAnything else cancels."
    return "Go ahead?  [yes / no]"


def confirmation_is_valid(plan: Plan, answer: str) -> bool:
    """Whether an answer counts as approval for this plan."""
    cleaned = answer.strip()
    if plan.is_destructive:
        # Case-sensitive on purpose: "delete" is something you might type
        # while thinking aloud. "DELETE" is deliberate.
        return cleaned == "DELETE"
    return cleaned.lower() in {"yes", "y"}
