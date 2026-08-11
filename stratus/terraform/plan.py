"""Turning Terraform's JSON plan into something Stratus can reason about.

Terraform can emit a plan as machine-readable JSON. Parsing that is far safer
than scraping the human-readable text output, which is designed for terminals,
changes between versions, and contains colour codes.

Nothing in this file runs Terraform. It is pure parsing, which means every
case below — including the awkward ones — can be tested from a fixture with
no Terraform, no Azure and no network.
"""

from __future__ import annotations

from typing import Any

from stratus.models import Action, Plan, PlannedChange


def _action_from_terraform(actions: list[str]) -> Action:
    """Collapse Terraform's action list into a single action.

    Terraform reports a replacement as a two-element list, and the order tells
    you which way round it happens:

        ["delete", "create"]  destroy first, then create  (downtime)
        ["create", "delete"]  create first, then destroy  (no downtime)

    Both are a *replacement* as far as the user is concerned, and both mean
    the original resource — and anything stored on it — is gone. Flattening
    them to a single REPLACE keeps that fact impossible to overlook.
    """
    unique = set(actions)

    if unique == {"delete", "create"}:
        return Action.REPLACE
    if unique == {"create"}:
        return Action.CREATE
    if unique == {"update"}:
        return Action.UPDATE
    if unique == {"delete"}:
        return Action.DELETE
    if unique == {"no-op"} or unique == {"read"}:
        # "read" is a data source being refreshed. It changes nothing.
        return Action.NO_OP

    # An action combination we have not seen. Treating it as a replacement is
    # the cautious choice: it routes the change through the destructive-change
    # confirmation gate rather than letting something unrecognised through
    # unchallenged.
    return Action.REPLACE


def parse_plan(document: dict[str, Any]) -> Plan:
    """Build a Plan from the output of `terraform show -json <planfile>`."""
    changes: list[PlannedChange] = []

    for entry in document.get("resource_changes", []):
        change = entry.get("change", {})
        actions = change.get("actions", [])

        changes.append(
            PlannedChange(
                address=entry.get("address", ""),
                type=entry.get("type", ""),
                name=entry.get("name", ""),
                action=_action_from_terraform(actions),
                before=change.get("before"),
                after=change.get("after"),
            )
        )

    return Plan(changes=changes, raw=document)
