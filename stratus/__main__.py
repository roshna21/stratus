"""Command line for Stratus.

    python -m stratus                              show the demo account
    python -m stratus show                         show your real Azure account
    python -m stratus build "I need a website"     build something
    python -m stratus destroy                      tear a workspace down

Everything needing Azure expects `az login` to have been run. No credential
is ever asked for or stored by Stratus itself.
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from stratus.azure import FakeAzureReader, LiveAzureReader
from stratus.summarise import summarise

# Reads a local .env if there is one. Keeping the subscription id out of the
# command line means it never lands in your shell history or a screenshot.
load_dotenv()


def _subscription(args, parser) -> str:
    if args.subscription:
        return args.subscription
    parser.error(
        "no subscription id. Either pass --subscription <id>, or put\n"
        "AZURE_SUBSCRIPTION_ID in a .env file (see .env.example).\n"
        "Find yours with:  az account list --output table"
    )


def _fail(message: str, detail: str = "") -> int:
    print(f"\n{message}", file=sys.stderr)
    if detail:
        print(f"\n{detail}", file=sys.stderr)
    return 1


def cmd_show(args, parser) -> int:
    if not args.live:
        print("(demo account — no Azure connection, nothing real, nothing billed)\n")
        print(summarise(FakeAzureReader().read()))
        return 0

    try:
        snapshot = LiveAzureReader(_subscription(args, parser)).read()
    except Exception as exc:  # noqa: BLE001 - shown to a human, not swallowed
        return _fail(
            "Couldn't read that Azure subscription.",
            f"  {exc}\n\n"
            "Two things worth checking:\n"
            "  1. Are you logged in?      az login\n"
            "  2. Is the id right?        az account list --output table",
        )

    print(summarise(snapshot))
    return 0


def cmd_build(args, parser) -> int:
    from stratus.pipeline import Stratus

    def confirm(text: str) -> str:
        print("\n" + "-" * 64)
        print(text)
        print("-" * 64)
        try:
            return input("> ")
        except (EOFError, KeyboardInterrupt):
            # A closed pipe or Ctrl-C must never read as approval.
            return ""

    def progress(message: str) -> None:
        print(f"  {message}")

    try:
        stratus = Stratus(_subscription(args, parser), workspace=args.workspace)
        outcome = stratus.build(args.request, confirm=confirm, on_progress=progress)
    except Exception as exc:  # noqa: BLE001
        return _fail("Couldn't complete that.", str(exc))

    print()
    if outcome.cancelled_reason == "nothing to do":
        print("You already have everything you asked for. Nothing was changed.")
    elif outcome.cancelled_reason == "not approved":
        print("Cancelled. Nothing was created or changed.")
    elif outcome.applied:
        print("Done.")
        if outcome.config:
            print(f"\n{outcome.config.summary}")

    if outcome.repairs_used:
        print(f"\n(needed {outcome.repairs_used} correction(s) along the way)")
    print(f"(model cost: ${outcome.cost_usd:.4f})")
    return 0


def cmd_destroy(args, parser) -> int:
    from stratus.pipeline import Stratus

    def confirm(text: str) -> str:
        print("\n" + "-" * 64)
        print(text)
        print("-" * 64)
        try:
            return input("> ")
        except (EOFError, KeyboardInterrupt):
            return ""

    try:
        stratus = Stratus(_subscription(args, parser), workspace=args.workspace)
        outcome = stratus.destroy(confirm=confirm)
    except Exception as exc:  # noqa: BLE001
        return _fail("Couldn't tear that down.", str(exc))

    print()
    if outcome.cancelled_reason == "nothing to destroy":
        print(f"There's nothing in '{args.workspace}' to tear down.")
    elif outcome.cancelled_reason == "not approved":
        print("Cancelled. Nothing was deleted.")
    elif outcome.applied:
        print("Torn down. Everything in that workspace is gone.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stratus",
        description="Describe the infrastructure you need in plain English.",
    )
    parser.add_argument(
        "--subscription",
        metavar="ID",
        default=os.getenv("AZURE_SUBSCRIPTION_ID"),
        help="Azure subscription id (defaults to AZURE_SUBSCRIPTION_ID from .env)",
    )
    parser.add_argument(
        "--workspace",
        default="default",
        help="which set of infrastructure to work on (default: 'default')",
    )

    sub = parser.add_subparsers(dest="command")

    show = sub.add_parser("show", help="describe what's in the account")
    show.add_argument(
        "--live",
        action="store_true",
        help="read real Azure instead of the built-in demo account",
    )

    build = sub.add_parser("build", help="build something from a description")
    build.add_argument("request", help='what you need, e.g. "a website with a database"')

    sub.add_parser("destroy", help="tear down everything in a workspace")

    args = parser.parse_args(argv)

    if args.command == "build":
        return cmd_build(args, parser)
    if args.command == "destroy":
        return cmd_destroy(args, parser)
    if args.command == "show":
        return cmd_show(args, parser)

    # No subcommand: the demo, so a fresh clone does something immediately.
    args.live = False
    return cmd_show(args, parser)


if __name__ == "__main__":
    raise SystemExit(main())
