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
        # flush matters: Python buffers stdout when it is not a terminal, so
        # without it every progress line arrives at once when the command
        # ends. Steps here take minutes, and a user watching a silent screen
        # has no way to tell working from hung.
        print(f"  {message}", flush=True)

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
    elif outcome.cancelled_reason == "failed, nothing left behind":
        print("That didn't work, but nothing was created — you're back where you started.")
        print(f"\n{outcome.error}")
    elif outcome.recovery == "undone":
        print("Removed what was built. You're back where you started.")
    elif outcome.recovery == "finished":
        print("Finished on the second attempt.")
        if outcome.config:
            print(f"\n{outcome.config.summary}")
    elif outcome.recovery == "finish failed":
        # The user is still holding half-built infrastructure and needs to
        # know that, plus how to get rid of it.
        print("It failed again, so I stopped rather than keep retrying.")
        print(f"\nWhat's still there:\n{_leftovers(outcome)}")
        print(f"\nRemove it with:  python -m stratus destroy --workspace {args.workspace}")
        print(f"\n{outcome.error}")
    elif outcome.recovery == "left as is":
        print("Left the half-finished build alone, as asked.")
        print(f"\nWhat's still there:\n{_leftovers(outcome)}")
        print(f"\nRemove it with:  python -m stratus destroy --workspace {args.workspace}")
    elif outcome.applied:
        print("Done.")
        if outcome.config:
            print(f"\n{outcome.config.summary}")

    if outcome.repairs_used:
        print(f"\n(needed {outcome.repairs_used} correction(s) along the way)")
    print(f"(model cost: ${outcome.cost_usd:.4f})")
    return 0


def _leftovers(outcome) -> str:
    """List what a half-finished build left behind."""
    if not outcome.partial:
        return "  (nothing)"
    from stratus.explain import describe

    return "\n".join(
        f"  - {describe(address.split('.')[0])}" for address in outcome.partial.created
    )


def cmd_destroy(args, parser) -> int:
    from stratus.pipeline import Stratus

    def progress(message: str) -> None:
        print(f"  {message}", flush=True)

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
        outcome = stratus.destroy(confirm=confirm, on_progress=progress)
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


def cmd_history(args, parser) -> int:
    from stratus.history import describe_entry, describe_history
    from stratus.pipeline import Stratus

    try:
        stratus = Stratus(_subscription(args, parser), workspace=args.workspace)
    except Exception as exc:  # noqa: BLE001
        return _fail("Couldn't open that workspace.", str(exc))

    if args.id:
        entry = stratus.history.get(args.id)
        if entry is None:
            return _fail(f"No change matching '{args.id}'.")
        print(describe_entry(entry))
        return 0

    entries = stratus.history.entries()
    print(describe_history(entries, stratus.history.unreadable))
    return 0


def cmd_rollback(args, parser) -> int:
    from stratus.pipeline import Stratus

    def confirm(text: str) -> str:
        print("\n" + "-" * 64)
        print(text)
        print("-" * 64)
        try:
            return input("> ")
        except (EOFError, KeyboardInterrupt):
            return ""

    def progress(message: str) -> None:
        print(f"  {message}", flush=True)

    try:
        stratus = Stratus(_subscription(args, parser), workspace=args.workspace)
        outcome = stratus.rollback(args.id, confirm=confirm, on_progress=progress)
    except Exception as exc:  # noqa: BLE001
        return _fail("Couldn't roll back.", str(exc))

    print()
    if outcome.cancelled_reason == "no such change":
        print(f"No change matching '{args.id}'. See:  stratus history")
        return 1
    if outcome.cancelled_reason == "nothing to do":
        print("Things are already the way they were then. Nothing changed.")
    elif outcome.cancelled_reason == "not approved":
        print("Cancelled. Nothing was changed.")
    elif outcome.applied:
        print("Rolled back.")
        if outcome.history_entry:
            print(f"(recorded as {outcome.history_entry.id})")
    return 0


def cmd_drift(args, parser) -> int:
    from stratus.drift import explain_drift
    from stratus.pipeline import Stratus

    try:
        stratus = Stratus(_subscription(args, parser), workspace=args.workspace)
        drift = stratus.check_drift()
    except Exception as exc:  # noqa: BLE001
        return _fail("Couldn't check for changes.", str(exc))

    print(explain_drift(drift))
    # A non-zero exit when things have moved, so this is usable from a
    # scheduled job that should raise an alarm rather than log quietly.
    return 1 if drift.has_drift else 0


def main(argv: list[str] | None = None) -> int:
    # Shared options are attached to the top level *and* to every subcommand,
    # so `stratus --workspace x build "..."` and
    # `stratus build "..." --workspace x` both work. People write it the
    # second way, and argparse only accepts the first unless told otherwise.
    #
    # The defaults are SUPPRESS rather than real values: with a real default
    # the subcommand's copy overwrites whatever was given at the top level,
    # so the option would silently do nothing in the first form.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--subscription",
        metavar="ID",
        default=argparse.SUPPRESS,
        help="Azure subscription id (defaults to AZURE_SUBSCRIPTION_ID from .env)",
    )
    common.add_argument(
        "--workspace",
        default=argparse.SUPPRESS,
        help="which set of infrastructure to work on (default: 'default')",
    )

    parser = argparse.ArgumentParser(
        prog="stratus",
        parents=[common],
        description="Describe the infrastructure you need in plain English.",
    )

    sub = parser.add_subparsers(dest="command")

    show = sub.add_parser("show", parents=[common], help="describe what's in the account")
    show.add_argument(
        "--live",
        action="store_true",
        help="read real Azure instead of the built-in demo account",
    )

    build = sub.add_parser("build", parents=[common], help="build something from a description")
    build.add_argument("request", help='what you need, e.g. "a website with a database"')

    sub.add_parser("destroy", parents=[common], help="tear down everything in a workspace")

    sub.add_parser(
        "drift", parents=[common], help="check whether anything changed outside Stratus"
    )

    history = sub.add_parser(
        "history", parents=[common], help="show what has been built and when"
    )
    history.add_argument("id", nargs="?", help="show one change in detail")

    rollback = sub.add_parser(
        "rollback", parents=[common], help="put things back to a previous change"
    )
    rollback.add_argument("id", help="the change to go back to (from `stratus history`)")

    args = parser.parse_args(argv)

    # Fill in what neither position supplied.
    if not getattr(args, "subscription", None):
        args.subscription = os.getenv("AZURE_SUBSCRIPTION_ID")
    if not getattr(args, "workspace", None):
        args.workspace = "default"

    if args.command == "build":
        return cmd_build(args, parser)
    if args.command == "destroy":
        return cmd_destroy(args, parser)
    if args.command == "history":
        return cmd_history(args, parser)
    if args.command == "rollback":
        return cmd_rollback(args, parser)
    if args.command == "drift":
        return cmd_drift(args, parser)
    if args.command == "show":
        return cmd_show(args, parser)

    # No subcommand: the demo, so a fresh clone does something immediately.
    args.live = False
    return cmd_show(args, parser)


if __name__ == "__main__":
    raise SystemExit(main())
