"""Driving the Terraform command-line tool from Python.

Stratus does not reimplement Terraform. It writes configuration files, runs
the real `terraform` binary, and reads the machine-readable results. Anything
else would mean maintaining our own version of Terraform's dependency
resolution and provider handling, which is a losing battle.

The safety-critical rule in this file: **apply never re-plans.** `plan()`
saves its decision to a file, and `apply()` executes exactly that file. If it
re-planned, the thing that ran could differ from the thing the user approved —
someone else changes the account in the gap, and now their "yes" applies to
something they never saw.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from stratus.models import Plan
from stratus.terraform.plan import parse_plan

PLAN_FILENAME = "stratus.tfplan"

# Terraform can legitimately take minutes to build cloud resources, so these
# are generous. They exist only to stop a wedged process hanging forever.
INIT_TIMEOUT = 300
PLAN_TIMEOUT = 300
APPLY_TIMEOUT = 1800


class TerraformError(RuntimeError):
    """A Terraform command failed.

    Carries the raw output, because Terraform's own error messages are usually
    the most useful thing available and swallowing them makes debugging far
    harder than it needs to be.
    """

    def __init__(self, command: list[str], returncode: int, stdout: str, stderr: str):
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        detail = (stderr or stdout).strip()
        super().__init__(
            f"`{' '.join(command)}` failed with exit code {returncode}\n\n{detail}"
        )


class TerraformRunner:
    """Runs Terraform inside one working directory.

    Each set of infrastructure gets its own directory containing its
    configuration files and its own local record. Keeping them apart means one
    request can never accidentally plan against another's configuration.
    """

    def __init__(self, workdir: str | Path, binary: str | None = None) -> None:
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)

        resolved = binary or shutil.which("terraform")
        if not resolved:
            raise TerraformError(
                ["terraform"],
                127,
                "",
                "The terraform command was not found.\n"
                "Install it with:  brew install hashicorp/tap/terraform",
            )
        self.binary = resolved

    # -- running commands ---------------------------------------------------

    def _run(self, args: list[str], timeout: int) -> subprocess.CompletedProcess:
        """Run one terraform subcommand.

        Always passes -input=false. Without it, Terraform will stop and wait
        for someone to type an answer when it wants a variable — and since
        nobody is watching this terminal, it would hang until the timeout.
        """
        command = [self.binary, *args]
        result = subprocess.run(  # noqa: S603 - args are built here, never from user text
            command,
            cwd=self.workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise TerraformError(command, result.returncode, result.stdout, result.stderr)
        return result

    # -- writing configuration ----------------------------------------------

    def write_config(self, filename: str, contents: str) -> Path:
        """Write one .tf file into the working directory."""
        if not filename.endswith(".tf"):
            raise ValueError(f"Terraform config files must end in .tf, got {filename!r}")
        path = self.workdir / filename
        path.write_text(contents)
        return path

    def clear_config(self) -> None:
        """Remove all .tf files, leaving state and provider plugins alone.

        Used when regenerating configuration for a changed request. Deleting
        the state here instead would orphan real cloud resources — Terraform
        would forget they exist while they carry on costing money.
        """
        for path in self.workdir.glob("*.tf"):
            path.unlink()

    # -- the lifecycle ------------------------------------------------------

    def init(self) -> None:
        """Download the provider plugins this configuration needs.

        Slow the first time, near-instant afterwards thanks to the shared
        plugin cache configured via TF_PLUGIN_CACHE_DIR.
        """
        self._run(["init", "-input=false", "-no-color"], INIT_TIMEOUT)

    def plan(self) -> Plan:
        """Work out what would change, and save that decision to a file.

        Two steps: `plan -out` computes and saves it, `show -json` reads it
        back in a form we can parse. The saved file is what apply() will run,
        so what the user approves is exactly what executes.
        """
        self._run(
            ["plan", "-input=false", "-no-color", f"-out={PLAN_FILENAME}"],
            PLAN_TIMEOUT,
        )
        shown = self._run(
            ["show", "-json", PLAN_FILENAME],
            PLAN_TIMEOUT,
        )
        return parse_plan(json.loads(shown.stdout))

    def apply(self) -> str:
        """Execute the plan that was saved by the last plan() call.

        Deliberately takes no arguments. Passing a configuration here would
        let a caller apply something other than what was reviewed.
        """
        plan_file = self.workdir / PLAN_FILENAME
        if not plan_file.exists():
            raise TerraformError(
                ["terraform", "apply"],
                1,
                "",
                "No saved plan to apply. Call plan() first — Stratus never "
                "applies anything a human has not seen.",
            )
        result = self._run(
            ["apply", "-input=false", "-no-color", "-auto-approve", PLAN_FILENAME],
            APPLY_TIMEOUT,
        )
        # The saved plan is single-use. Removing it prevents the same approval
        # being replayed later against a cloud account that has since moved on.
        plan_file.unlink(missing_ok=True)
        return result.stdout

    def destroy(self) -> str:
        """Tear everything in this directory back down.

        Used to clean up after demos and tests. The user-facing confirmation
        gate lives above this, in the approval layer — by the time execution
        reaches here, permission has already been given.
        """
        result = self._run(
            ["destroy", "-input=false", "-no-color", "-auto-approve"],
            APPLY_TIMEOUT,
        )
        return result.stdout

    def state_resources(self) -> list[str]:
        """List the resource addresses Terraform currently believes it owns.

        Compared against a real account read, this is how half-finished
        builds get detected: anything Terraform thinks exists but the cloud
        does not have is a leftover from a build that died partway.
        """
        try:
            result = self._run(["state", "list"], PLAN_TIMEOUT)
        except TerraformError:
            # No state yet is a normal condition, not an error.
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def version(self) -> dict[str, Any]:
        result = self._run(["version", "-json"], 60)
        return json.loads(result.stdout)
