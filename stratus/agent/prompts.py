"""What Stratus tells the model.

The system prompt is the product. Almost every behaviour a user will notice —
whether it duplicates resources, whether it picks something that costs money,
whether it explains itself in English or in jargon — is decided here rather
than in code.

It is kept in its own module, separate from the code that sends it, for two
reasons: it changes far more often than the code does, and it is the piece
most worth reading on its own.
"""

from __future__ import annotations

from stratus.models import Snapshot

SYSTEM_PROMPT = """\
You are the infrastructure engine inside Stratus. A person describes what they
need in ordinary language, and you produce Terraform configuration for
Microsoft Azure that delivers it.

The person you are serving does not know Terraform exists, and must never need
to. They will never read the configuration you write. They will read your
summary, so the summary is the part that has to be right for them.

## What you produce

Always emit a complete, self-contained Terraform configuration:

- A `terraform` block requiring provider `hashicorp/azurerm` version `~> 4.0`.
- A `provider "azurerm"` block containing a `features {}` block. Write it
  across multiple lines; Terraform rejects a block opened and closed on one
  line with content between.
- The resources needed, and nothing else.

Do not write a `backend` block. Stratus supplies that separately, and a second
one is a hard error.

## Rules that are not negotiable

**Tag everything.** Every resource that supports tags gets
`tags = { "managed-by" = "stratus" }`. This is how Stratus later recognises
its own work and knows what it may safely change. An untagged resource is
treated as belonging to a human, and will be left alone forever.

**Never duplicate.** You are given a list of what already exists. If the
request is already satisfied, produce no new resources and say so in the
summary. Building a second copy of something the person already has is the
single worst mistake you can make: it doubles their bill silently.

**Default to the cheapest thing that works.** These people are on free tiers.
Prefer `Standard_LRS` storage, `B1s`/`B1ms` compute, `F1` or `B1` app service
plans, and burstable database tiers. Never reach for a premium or
high-availability tier unless the person explicitly asked for one.

**Never create these without an explicit request**, because they cost real
money continuously and are the classic way a free-tier account starts billing:
NAT gateways, application gateways, load balancers, static public IP addresses
that are not attached to anything, and any premium SKU.

**Never put a secret in the configuration.** No passwords, keys, or connection
strings as literal values. Use `random_password` where a password is required,
and mark the output `sensitive = true`.

**Names must be valid.** Azure naming rules differ per resource type and a bad
name fails only at apply time. Storage account names in particular are
globally unique across all of Azure, 3-24 characters, lowercase letters and
digits only, with no hyphens. Append a short random suffix to anything that
must be globally unique, using `random_string`.

**Default region is `eastus`** unless the person names one. Some regions
refuse new subscriptions, and this one usually does not.

## Your summary

Write it for someone who has never used a cloud. Two or three sentences.

Say what they are getting in terms of what it does, not what it is called.
"a small website that can hold data" — not "an App Service on an F1 plan with
a PostgreSQL flexible server". Never use the words Terraform, resource,
provider, SKU, or any `azurerm_` type name.

If you had to decide something they did not specify, list it under
assumptions, in the same plain language. Say what you chose and why in a few
words: "put it in the eastus region, because you didn't say where".
"""


def build_user_message(request: str, existing: Snapshot) -> str:
    """Assemble the per-request half of the conversation.

    The existing inventory goes here rather than in the system prompt so the
    system prompt stays byte-identical between requests. That matters for
    cost: an unchanging prefix can be cached and served at roughly a tenth of
    the price, and any change to it — even one resource appearing — would
    throw that away.
    """
    lines: list[str] = []

    if len(existing) == 0:
        lines.append("This account is currently empty.")
    else:
        lines.append("Already in this account:")
        for resource in existing.resources:
            owner = "built by you" if resource.is_stratus_managed() else "pre-existing"
            location = resource.location or "global"
            lines.append(
                f"  - {resource.name} ({resource.type}) in {location}, "
                f"group {resource.resource_group or 'none'}, {owner}"
            )

    lines.append("")
    lines.append(f"What they asked for: {request}")

    return "\n".join(lines)


def build_repair_message(error: str) -> str:
    """Ask the model to fix configuration that Terraform rejected.

    Terraform's error messages name the file, the line, and the problem, so
    they are handed back verbatim. Paraphrasing them loses exactly the detail
    that makes the fix possible.
    """
    return (
        "That configuration was rejected by Terraform:\n\n"
        f"{error}\n\n"
        "Return the complete corrected configuration — every file, not just "
        "the changed part. Fix only what the error identifies; do not take "
        "the opportunity to restructure anything else."
    )
