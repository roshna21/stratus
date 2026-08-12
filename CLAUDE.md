# Working on Stratus

Context for anyone — human or model — picking this up fresh.

## What it is

An agent that turns a plain-English request into cloud infrastructure on
Azure. The user describes what they need, sees exactly what would change and
what it would cost, approves, and it gets built. They never see Terraform,
which runs underneath.

Built as a portfolio project. It runs against a real Azure subscription and
every feature has been verified there, including the failures.

## Run it

```bash
cd ~/Documents/stratus
./.venv/bin/python -m stratus                # demo, no cloud, no cost
./.venv/bin/python -m pytest -q              # 367 tests, all offline
```

Against the real account (needs `az login` and a filled-in `.env`):

```bash
./.venv/bin/python -m stratus show --live
./.venv/bin/python -m stratus build "a private place to keep some files"
```

Web interface — two processes:

```bash
./.venv/bin/uvicorn stratus.web:app --port 8000   # API
cd web && npm run dev                              # interface on :3000
```

## Where things are

| Path | What |
|---|---|
| `stratus/models.py` | The core types. Read this first. |
| `stratus/pipeline.py` | The whole flow in order. Read this second. |
| `stratus/agent/` | The only part that calls a language model |
| `stratus/agent/prompts.py` | The system prompt — most product behaviour is decided here |
| `stratus/terraform/` | Driving the Terraform CLI |
| `stratus/azure/` | Reading the account, and the state storage bootstrap |
| `stratus/explain.py` | Plans turned into plain English. The approval screen. |
| `stratus/policy.py` | What Stratus refuses to build |
| `stratus/cost.py` | Pricing, from Azure's public price list |
| `stratus/drift.py`, `recovery.py`, `history.py` | Phase 3–4 features |
| `stratus/web.py`, `jobs.py` | HTTP API |
| `web/` | Next.js front end |
| `~/.stratus/workspaces/` | **Outside the repo** — your actual infrastructure state |

## Rules this codebase holds to

Breaking one of these is a real bug, not a style preference.

1. **Only one thing calls a model** — turning an ambiguous sentence into
   configuration. Everything else has exactly one correct answer, so it is
   ordinary code: instant, free, identical every time. Do not reach for a
   model to summarise, count, or decide.

2. **`apply` runs only the saved plan.** If it re-planned, what executes could
   differ from what was approved. The web API preserves this across two HTTP
   requests, and a test asserts the plan count does not change between them.

3. **Never report zero when the answer is unknown.** A resource that cannot be
   priced is reported as unknown, out loud. A wrong "this is free" is how
   someone finds a surprise on a bill.

4. **No Terraform vocabulary reaches the user.** Tests assert the strings
   `Microsoft.` and `azurerm_` never appear in output.

5. **Destroying requires the word DELETE, typed.** In both interfaces. An
   empty answer is never consent.

6. **Safety rules read the plan, not the generated text.** Text matching
   misses variables and defaults while reporting all clear.

7. **Tests never touch a network, a cloud account, or a model.** Every
   external thing is behind an interface with a fake behind it. If a test
   needs a secret, something has gone wrong.

## Things that cost hours to learn

All hit against the real account.

**Owning an Azure subscription does not grant access to data inside its
storage accounts.** Separate permission systems. The 403 explains nothing.
`stratus/azure/state.py` → `access_hint()` has the fix. Hit twice, on two
different accounts. `--auth-mode key` is the alternative to a role grant.

**Free subscriptions have an App Service quota of zero.** Reported as
`401 Unauthorized`, which sounds like a login problem. No region helps. The
system prompt steers to storage-hosted static sites instead.

**Azure lists regions it operates, not regions you may use.** `westeurope`
refused outright. There is a fallback list.

**`eastus` cannot host a static web app**, which is the first thing the prompt
reaches for when someone asks for a website. The plan succeeds and the *apply*
fails, minutes later, with `LocationNotAvailableForResourceType` — after the
resource group has already been created. So the approval screen promised
something unbuildable. `Microsoft.Web/staticSites` runs in five regions only:
`centralus`, `eastus2`, `westus2`, `westeurope`, `eastasia`. `DEFAULT_REGION`
is now `eastus2` and every fallback is drawn from that list. Check
`az provider show -n Microsoft.Web --query "resourceTypes[?resourceType=='staticSites'].locations[]"`
before adding a region anywhere.

**A resource group's region cannot be changed after creation.**

**Gemini retires models for new accounts.** Use the `gemini-flash-latest`
alias, never a dated version — a pinned one 404s with a message that reads
like a broken key.

**`azure-mgmt-resource` v26 moved `ResourceManagementClient`** into the
`.resources` subpackage. Every tutorial online shows the old path.

**One workspace holds one set of infrastructure.** A new request in a
workspace that already has something *replaces* it. That is Terraform's
model. The deletion gate catches it, but use one workspace per thing.

## State of play

Phases 1–5 complete. 367 tests, lint clean, verified against real Azure.

Outstanding:

- **CI workflow is written but unpushed.** `.github/workflows/tests.yml`
  exists locally; GitHub rejects it because the stored token lacks the
  `workflow` scope. Fix with `gh auth login`, or paste the file into
  GitHub's web editor.
- **Demo video not recorded.** The strongest moment is the destructive-plan
  screen: an innocent-sounding request that would have destroyed a working
  website, caught and explained before anything happened.
- **Not deployed.** `render.yaml` is ready. Not Azure App Service — quota.

Ideas not done: rollback from the browser (deliberately CLI-only for now),
a second cloud provider (the boundary exists for it), multi-turn clarifying
questions before proposing an architecture.

## How to work here

Match what is already there. The code carries a lot of comments explaining
*why* a decision was made, especially where the obvious approach is wrong —
those are the expensive knowledge and should be preserved and extended, not
trimmed.

Commit messages are long and explain reasoning. Keep that.

Run `./.venv/bin/python -m pytest -q` and `./.venv/bin/ruff check stratus
tests` before committing.

Anything that touches the real cloud costs money and time. The fakes exist
so that almost nothing needs to.
