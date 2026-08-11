# Stratus

**Describe the infrastructure you need in plain English. An agent designs it, shows you exactly what would change and what it would cost, and builds it on Azure once you agree.**

You never see infrastructure code. You never learn a cloud console. You have a conversation.

```
$ stratus build "a small website that can store uploaded files"

  Looking at what you already have...
  Working out what to build...
  Checking what that would change...

  Nothing here has a fixed monthly charge.

  These cost nothing to exist, and bill on what you use:
    - website: about 2 cents per GB stored per month, plus a little per operation

  Creating:
    - place to keep files (website)
    - folder (uploads)
    - plus 2 supporting pieces needed to make that work

  Nothing existing will be changed or deleted.

  Go ahead?  [yes / no]
> yes
  Building it...
  azurerm_storage_account.website: Still creating... [01m30s elapsed]

Done.
Your new website has been set up alongside a dedicated folder for
storing uploaded files.
```

There is a web interface too, with the same approval step.

---

## The problem

Going from *"I need infrastructure for X"* to a working, secure cloud setup normally means learning cloud architecture, one provider's product catalogue, an infrastructure-as-code language, and a pile of security conventions.

AI coding tools will happily write you a configuration file. What they will not do is own the consequences. They do not know what you already have, so they build duplicates. They do not show you what is about to change before it changes. They have no answer when a deployment dies halfway and leaves your account in a broken half-built state. And they will cheerfully hand you something that costs $32 a month forever, or that leaves your files readable by anyone on the internet.

Stratus owns the whole lifecycle.

## How it works

Under the hood it uses [Terraform](https://developer.hashicorp.com/terraform) — an implementation detail the user never sees. The agent writes it, runs it, reads its output, and translates everything back into plain language.

```
  You (plain English)
        │
        ▼
  ┌──────────────────────────────────────────────────┐
  │  1. read what already exists                     │
  │  2. write configuration for the request          │
  │  3. check it parses                              │
  │  4. work out exactly what would change           │
  │  5. refuse it if it is unsafe, and try again     │
  │  6. price it                                     │
  │  7. explain it, in plain English                 │
  │  8. wait for your approval                       │
  │  9. build it, streaming progress                 │
  │ 10. recover if it fails partway                  │
  └──────────────────────────────────────────────────┘
        │
        ▼
      Azure
```

Exactly one step calls a language model: step 2. Everything else has one correct answer, so it is ordinary code — instant, free, and identical every time.

## What makes this more than a code generator

| Capability | What it means |
|---|---|
| **Knows what already exists** | The account is read before anything is planned. Asking twice does not build twice. |
| **Shows the change first** | Every action is a reviewed diff, described in plain English. Terraform vocabulary never reaches the screen. |
| **Cost preview** | Which things are free, which bill on usage, and which charge every hour — with real prices from Azure's public price list. |
| **Refuses unsafe configurations** | World-readable storage, SSH open to the internet, unencrypted transfer. The refusal goes back to the model, which rewrites it — you see the safe version, not an error. |
| **Deletion gate** | Anything destructive requires the word `DELETE`, typed exactly. |
| **Half-finished recovery** | If a build dies partway, it works out what survived and offers to finish or undo. |
| **Drift detection** | Notices when something changed in Azure outside Stratus, and says what that means. |
| **Change history and rollback** | Every change recorded with the configuration that produced it. Roll back to any of them. |
| **Not tied to one model vendor** | Gemini, Claude, or another behind one interface. |

## Try it

```bash
git clone https://github.com/roshna21/stratus && cd stratus
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m stratus            # demo account, no Azure, no cost
```

To point it at a real account you need [Terraform](https://developer.hashicorp.com/terraform/install), the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), and a free [Gemini API key](https://aistudio.google.com/apikey):

```bash
az login
cp .env.example .env      # then fill in AZURE_SUBSCRIPTION_ID and GEMINI_API_KEY

./.venv/bin/python -m stratus show --live
./.venv/bin/python -m stratus build "a private place to keep some files"
./.venv/bin/python -m stratus drift
./.venv/bin/python -m stratus history
./.venv/bin/python -m stratus rollback <id>
./.venv/bin/python -m stratus destroy
```

Web interface:

```bash
./.venv/bin/uvicorn stratus.web:app --port 8000
# or:  docker build -t stratus . && docker run -p 8000:8000 --env-file .env stratus
```

## Design decisions worth explaining

**`apply` takes no arguments.** It runs only the plan file saved by `plan`. If it re-planned, what executed could differ from what you approved — someone changes the account in the gap, and your "yes" applies to something you never saw. The web interface splits the approval across two HTTP requests and preserves the same property; a test asserts the plan count does not change between them.

**A replacement is shown as one thing, not two.** Terraform reports it as `["delete", "create"]`. Passed straight through, the user sees two lines and misses that the original — and everything in it — is destroyed.

**Safety rules read the plan, not the generated text.** The same setting can be written several ways, come from a variable, or be a default. A rule that greps configuration text misses all three while reporting that everything is fine.

**Cost never reports zero when the answer is unknown.** A resource that cannot be priced is reported as unknown, out loud, and never folded into the total as free.

**Recovery costs no cloud calls.** Stratus planned the work, so it knows what should exist; Terraform's state says what does. The difference is the answer — and calling Azure could fail for the same reason the build did.

## Limitations

**One workspace holds one set of infrastructure.** Asking for something new in a workspace that already has something replaces it — that is Terraform's model, not a bug. The deletion gate catches it (this was found by asking for "a place to keep backup files" in a workspace that already held a website, and being correctly warned that the website would be destroyed), but the natural expectation is that a new request adds rather than replaces. Use a separate workspace per thing.

**Azure only.** The provider layer is behind an interface, so a second cloud is an added reader rather than a rewrite, but only Azure is implemented.

**Free subscriptions cannot create App Service.** Their quota for it is zero, and Azure reports that as `401 Unauthorized`. Stratus recognises this and steers to storage-hosted static sites instead.

**No authentication on the web interface.** It is a demonstration. Do not expose it to the internet as-is.

## Stack

| Layer | Choice |
|---|---|
| Agent | Python, FastAPI |
| Reasoning | Gemini by default; Claude supported. Behind one interface. |
| Infrastructure engine | Terraform CLI, `azurerm` provider |
| Cloud | Microsoft Azure |
| State | Azure Storage, with locking |
| Pricing | Azure Retail Prices API (public, no key) |
| Interface | Command line, and a single-file web page |

## Tests

```bash
./.venv/bin/python -m pytest
```

359 tests. **None of them touch a network, a cloud account, or a language model.** Every external thing is behind an interface with a fake on the other side, which is why the suite runs in under a second and costs nothing.

Several exist to hold a specific line rather than to cover code:

- the plain-English output never contains the string `Microsoft.` or `azurerm_`
- an empty answer is never treated as approval
- the system prompt contains no region name
- a resource that cannot be priced is never reported as free
- the web interface does not re-plan between describing and applying

## Licence

MIT
