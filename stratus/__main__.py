"""Command-line entry point, so Phase 1 is something you can actually run.

    python -m stratus                          # demo account, no Azure needed
    python -m stratus --live --subscription ID # a real Azure subscription

The `--live` path needs you to have run `az login` first. Nothing here ever
asks for or stores a credential.
"""

from __future__ import annotations

import argparse
import sys

from stratus.azure import FakeAzureReader, LiveAzureReader
from stratus.summarise import summarise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stratus",
        description="Show what exists in a cloud account, in plain English.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="read a real Azure subscription instead of the built-in demo account",
    )
    parser.add_argument(
        "--subscription",
        metavar="ID",
        help="Azure subscription id (required with --live)",
    )
    args = parser.parse_args(argv)

    if args.live:
        if not args.subscription:
            parser.error("--live also needs --subscription <id>")
        try:
            reader = LiveAzureReader(args.subscription)
            snapshot = reader.read()
        except Exception as exc:  # noqa: BLE001 - surfaced to a human, not swallowed
            # Azure failures are usually "you aren't logged in" or "wrong
            # subscription id". Both are fixable by the person reading this,
            # so say so plainly instead of printing a stack trace at them.
            print(f"Couldn't read that Azure subscription.\n\n  {exc}\n", file=sys.stderr)
            print(
                "Two things worth checking:\n"
                "  1. Are you logged in?      az login\n"
                "  2. Is the id right?        az account list --output table",
                file=sys.stderr,
            )
            return 1
    else:
        snapshot = FakeAzureReader().read()
        print("(demo account — no Azure connection, nothing real, nothing billed)\n")

    print(summarise(snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
