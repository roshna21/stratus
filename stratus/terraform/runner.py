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
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from stratus.models import Plan
from stratus.terraform.plan import parse_plan

PLAN_FILENAME = "stratus.tfplan"

INIT_TIMEOUT = 300
PLAN_TIMEOUT = 300

APPLY_TIMEOUT = 1200
"""Twenty minutes.

Some cloud resources genuinely take a quarter of an hour to build, so this
cannot be tight. It was thirty minutes, which turned out to be far too long:
when Azure's App Service API began returning gateway timeouts, Terraform
retried in silence and the command sat there for sixteen minutes looking
identical to a hang. Streaming progress is the real fix; this is the backstop.
"""

LOCK_ID = re.compile(r"^\s*ID:\s*([0-9a-f-]{36})", re.MULTILINE)

CAPACITY_SIGNS = (
    "GatewayTimeout",
    "RequestDisallowedByAzure",
    "not accepting new customers",
    "There are no available instances",
)
"""What Azure says when a region has no room for you.

None of these mention capacity. They surface as timeouts or flat refusals,
and on a free subscription they are common enough to be worth recognising by
name rather than leaving the user to interpret.
"""

QUOTA_SIGNS = (
    "without additional quota",
    "SubscriptionIsOverQuotaForSku",
    "Current Limit (Total VMs): 0",
    "quota limit",
)
"""What Azure says when your account is not *allowed* the resource at all.

Different from capacity, and the distinction matters: capacity clears if you
move region or wait, a quota of zero does neither. Free subscriptions get an
App Service quota of zero, so no region will ever accept one — and Azure
reports that as `401 Unauthorized`, which sounds like a login problem.
"""

QUOTA_DETAIL = re.compile(r"Current Limit \(([^)]+)\): (\d+)")


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


class StateLocked(TerraformError):
    """Someone — possibly a dead process — is holding the state lock.

    The lock exists so two operations cannot write the state at once. It is
    doing its job here, but the message Terraform prints is long and does not
    say what to do, and the commonest cause is a previous run that was killed
    and never released it.
    """

    def __init__(self, base: TerraformError, workdir: Path):
        self.lock_id = _extract_lock_id(base.stdout + base.stderr)
        self.workdir = workdir
        super().__init__(base.command, base.returncode, base.stdout, base.stderr)

    def __str__(self) -> str:
        unlock = (
            f"terraform force-unlock {self.lock_id}"
            if self.lock_id
            else "terraform force-unlock <id from the message above>"
        )
        return (
            "The infrastructure record is locked by another operation.\n\n"
            "This is a safety mechanism: two operations writing at once would "
            "corrupt the record of what exists. Usually it means an earlier "
            "run was interrupted and never released the lock.\n\n"
            "First check nothing is genuinely still running:\n\n"
            "    pgrep -fl terraform\n\n"
            "If that prints nothing, release the lock:\n\n"
            f"    cd {self.workdir}\n"
            f"    {unlock}\n\n"
            "Only do this when you are certain no operation is in progress. "
            "Unlocking underneath a live run is how state gets corrupted."
        )


class CapacityUnavailable(TerraformError):
    """The region has no room, however it chose to phrase that."""

    def __init__(self, base: TerraformError, region_hint: str | None = None):
        self.region_hint = region_hint
        super().__init__(base.command, base.returncode, base.stdout, base.stderr)

    def __str__(self) -> str:
        detail = (self.stderr or self.stdout).strip()
        return (
            "Azure could not provide what was asked for in that region.\n\n"
            "Free-tier capacity is limited and varies by region and by day. "
            "Azure rarely says so directly — it surfaces as a timeout, a quota "
            "error, or a flat refusal.\n\n"
            "Try somewhere else:\n\n"
            "    STRATUS_REGION=westus2 python -m stratus build \"...\"\n\n"
            "Regions usually worth trying: westus2, uksouth, northeurope, "
            "centralindia, southeastasia.\n\n"
            f"Azure said:\n{detail[:600]}"
        )


class QuotaBlocked(TerraformError):
    """The account is not permitted this kind of resource at all.

    Distinct from CapacityUnavailable on purpose. Capacity clears if you move
    region or come back tomorrow; a quota of zero does neither, and telling
    someone to try another region when their limit is zero everywhere just
    wastes their afternoon.
    """

    def __init__(self, base: TerraformError):
        text = base.stdout + base.stderr
        match = QUOTA_DETAIL.search(text)
        self.quota_name = match.group(1) if match else "the required quota"
        self.quota_limit = match.group(2) if match else "0"
        super().__init__(base.command, base.returncode, base.stdout, base.stderr)

    def __str__(self) -> str:
        return (
            "Your Azure subscription is not allowed to create this.\n\n"
            f"Azure reports your limit for {self.quota_name} as "
            f"{self.quota_limit}. This is an account-level restriction, not a "
            "shortage — free and trial subscriptions get a quota of zero for "
            "some services, App Service being the usual one. Changing region "
            "will not help, because the limit applies everywhere.\n\n"
            "Three ways forward:\n\n"
            "  1. Ask for something that does not need that quota. Websites "
            "can be served from storage or from Static Web Apps, neither of "
            "which counts against it.\n"
            "  2. Request a quota increase in the Azure portal:\n"
            "     Subscriptions -> Usage + quotas -> Request increase\n"
            "  3. Upgrade to pay-as-you-go. Your credit still applies, and "
            "quotas are raised.\n\n"
            "Azure reported this as 401 Unauthorized, which sounds like a "
            "login problem. It is not — you are signed in correctly."
        )


def _extract_lock_id(text: str) -> str | None:
    match = LOCK_ID.search(text)
    return match.group(1) if match else None


def _looks_like_capacity(text: str) -> bool:
    return any(sign in text for sign in CAPACITY_SIGNS)


def _looks_like_quota(text: str) -> bool:
    return any(sign in text for sign in QUOTA_SIGNS)


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
        """Run one terraform subcommand and wait for it.

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
            raise self._interpret(
                TerraformError(command, result.returncode, result.stdout, result.stderr)
            )
        return result

    def _run_streaming(
        self,
        args: list[str],
        timeout: int,
        on_line: Callable[[str], None] | None = None,
    ) -> str:
        """Run a subcommand, reporting each line as it appears.

        Used for apply and destroy, which take minutes. Capturing their output
        and showing it at the end means the user stares at a silent screen and
        cannot tell slow progress from a stuck process — which is exactly how
        sixteen minutes of Azure gateway timeouts went unnoticed.
        """
        command = [self.binary, *args]
        collected: list[str] = []

        process = subprocess.Popen(  # noqa: S603 - args built here, never from user text
            command,
            cwd=self.workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        try:
            assert process.stdout is not None
            for line in process.stdout:
                collected.append(line)
                if on_line:
                    stripped = line.rstrip()
                    if stripped:
                        on_line(stripped)
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise TerraformError(
                command,
                -1,
                "".join(collected),
                f"Gave up after {timeout // 60} minutes.\n\n"
                "Terraform was still retrying. That usually means the cloud "
                "is refusing the request rather than working slowly — check "
                "the messages above for what it kept trying.",
            ) from None

        output = "".join(collected)
        if process.returncode != 0:
            raise self._interpret(TerraformError(command, process.returncode, output, ""))
        return output

    def _interpret(self, error: TerraformError) -> TerraformError:
        """Recognise failures worth explaining rather than passing through raw.

        Terraform's messages are accurate and unhelpful. These two come up
        often enough on a free subscription that leaving the user to decode
        them is a poor trade.
        """
        text = error.stdout + error.stderr

        if "Error acquiring the state lock" in text or "state blob is already locked" in text:
            return StateLocked(error, self.workdir)
        # Quota before capacity: a quota message often also contains words
        # that look like capacity, and sending someone region-hopping when
        # their limit is zero everywhere wastes their time.
        if _looks_like_quota(text):
            return QuotaBlocked(error)
        if _looks_like_capacity(text):
            return CapacityUnavailable(error)
        return error

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

    def validate(self) -> None:
        """Check the configuration is syntactically valid and self-consistent.

        Cheap and offline — it never contacts Azure. That makes it the right
        first gate on generated configuration: a language model will sometimes
        produce Terraform that does not parse, or that references an argument
        the provider does not have, and catching that here costs nothing.
        Letting it reach `plan` instead means a slow round trip to Azure to
        learn the same thing.

        Raises TerraformError carrying Terraform's own message, which is
        specific enough to hand straight back to the model for a repair.
        """
        self._run(["validate", "-no-color"], PLAN_TIMEOUT)

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

    def apply(self, on_line: Callable[[str], None] | None = None) -> str:
        """Execute the plan that was saved by the last plan() call.

        Takes no configuration. Passing one here would let a caller apply
        something other than what was reviewed; `on_line` only observes.
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
        output = self._run_streaming(
            ["apply", "-input=false", "-no-color", "-auto-approve", PLAN_FILENAME],
            APPLY_TIMEOUT,
            on_line=on_line,
        )
        # The saved plan is single-use. Removing it prevents the same approval
        # being replayed later against a cloud account that has since moved on.
        plan_file.unlink(missing_ok=True)
        return output

    def destroy(self, on_line: Callable[[str], None] | None = None) -> str:
        """Tear everything in this directory back down.

        The user-facing confirmation gate lives above this, in the approval
        layer — by the time execution reaches here, permission has been given.
        """
        return self._run_streaming(
            ["destroy", "-input=false", "-no-color", "-auto-approve"],
            APPLY_TIMEOUT,
            on_line=on_line,
        )

    def force_unlock(self, lock_id: str) -> None:
        """Release a lock left behind by an interrupted run.

        Not called automatically anywhere, and it should not be: a lock held
        by a *live* operation is the one thing standing between you and a
        corrupted state file. StateLocked prints this as a command for the
        user to run once they have checked nothing is running.
        """
        self._run(["force-unlock", "-force", lock_id], PLAN_TIMEOUT)

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
