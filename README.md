# Stratus

**Describe the infrastructure you need in plain English. An AI agent designs it, shows you what it will do, and builds it on Azure.**

You never see infrastructure code. You never learn a cloud console. You have a conversation.

```
You:      I need a small website with a database behind it.

Stratus:  Here's what I'd build:
            • a web app (smallest tier, free for 12 months)
            • a PostgreSQL database (smallest tier)
            • a private network so only the web app can reach the database

          Nothing existing will be changed or deleted.
          Estimated cost: about $0/month for the first year, then ~$18/month.

          Build this?  [yes / no]

You:      yes

Stratus:  Done — 3 resources created in 2m 14s.
          Your site: https://stratus-demo-a41f.azurewebsites.net
          I checked it: responding normally.
```

---

## The problem

Going from *"I need infrastructure for X"* to a working, secure cloud setup normally means learning
cloud architecture, one specific cloud provider's product catalogue, an infrastructure-as-code
language, and a pile of security conventions.

AI coding tools will happily write you a configuration file. What they won't do is own the
consequences: they don't know what you already have, they don't show you what's about to change
before it changes, and they have no answer when a deployment dies halfway through and leaves your
account in a broken half-built state.

Stratus owns the whole lifecycle.

## How it works

Under the hood Stratus uses [Terraform](https://developer.hashicorp.com/terraform) — but that is an
implementation detail the user never sees. The agent writes it, runs it, reads its output, and
translates everything back into plain language.

```
  You (plain English)
        │
        ▼
  ┌─────────────────────────────────────────────┐
  │  Agent                                      │
  │   1. reads what already exists              │
  │   2. plans the change                       │
  │   3. checks it against safety + cost rules  │
  │   4. explains it to you in plain English    │
  │   5. waits for your approval                │
  │   6. builds it, then verifies it works      │
  └─────────────────────────────────────────────┘
        │
        ▼
     Azure
```

## What makes this more than a code generator

These are the parts that break in practice, and the parts this project is actually about:

| Capability | What it means |
|---|---|
| **Knows what already exists** | Asking for a database twice doesn't create two databases |
| **Shows the change before making it** | Every action is a reviewed diff, described in plain English |
| **Cost preview** | You see the monthly bill impact before you approve |
| **Safety rules** | Refuses publicly-readable storage, SSH open to the internet, and similar |
| **Deletion gate** | Anything destructive requires explicit typed confirmation |
| **Half-finished recovery** | If a build dies partway, the agent detects the mismatch and offers to finish or undo |
| **Drift detection** | Notices when something was changed outside of Stratus and tells you |
| **Full history** | Every change is recorded, and you can roll back to a previous known-good state |

## Status

🚧 Early development.

- [ ] **Phase 1** — Read and describe an existing Azure account
- [ ] **Phase 2** — Plain English → plan → approve → build
- [ ] **Phase 3** — Cost preview, safety rules, deletion gate, failure recovery, drift detection
- [ ] **Phase 4** — Multiple environments, change history, rollback, multi-step planning
- [ ] **Phase 5** — Deploy Stratus itself to Azure

## Stack

| Layer | Choice |
|---|---|
| Agent backend | Python + FastAPI |
| Reasoning | Claude (Anthropic API), tool-use loop |
| Infrastructure engine | Terraform CLI (`azurerm` provider) |
| Cloud | Microsoft Azure |
| Agent's own database | PostgreSQL |
| Interface | Next.js chat UI |

## Licence

MIT
