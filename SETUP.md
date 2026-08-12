# Setting up on a new machine

Everything needed is in this folder. Two things live outside it: your
secrets in `.env` (never committed) and your infrastructure state in
`~/.stratus/workspaces/`.

## 1. Tools

```bash
brew install hashicorp/tap/terraform      # writes the infrastructure
brew install azure-cli                    # talks to Azure
# Python 3.11+ and Node 20+ also needed
```

One setting worth adding, or Terraform downloads a ~300MB provider copy into
every workspace:

```bash
echo 'export TF_PLUGIN_CACHE_DIR="$HOME/.terraform.d/plugin-cache"' >> ~/.zshrc
mkdir -p ~/.terraform.d/plugin-cache
```

## 2. Python

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/python -m pytest -q      # should pass with no cloud, no keys
```

## 3. Front end

```bash
cd web && npm install
```

## 4. Credentials

```bash
az login
cp .env.example .env
```

Fill in `.env`:

- `AZURE_SUBSCRIPTION_ID` — from `az account list --output table`
- `GEMINI_API_KEY` — free, no card, from https://aistudio.google.com/apikey

## 5. Run it

```bash
./.venv/bin/python -m stratus                      # demo, no cloud
./.venv/bin/python -m stratus show --live          # your real account
./.venv/bin/python -m stratus build "a place to keep files"

./.venv/bin/uvicorn stratus.web:app --port 8000    # API
cd web && npm run dev                              # interface on :3000
```

## In an IDE

Open this folder. VS Code, PyCharm and Cursor will all find the project.

Point the interpreter at `./.venv/bin/python` — otherwise imports appear
broken even though the tests pass.

`.claude/launch.json` defines both dev servers.

## If something fails

`CLAUDE.md` lists the traps that cost hours the first time: Azure storage
permissions, the App Service quota of zero on free subscriptions, regions
that refuse new customers, and the Gemini model alias. Read that before
debugging anything cloud-related.
