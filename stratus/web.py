"""A web interface for Stratus.

The approval step is the awkward part. On the command line the pipeline
simply blocks on a callback until someone types. HTTP has no equivalent — a
request that waits minutes for a human to read a page and click will hit
every timeout between the browser and the server.

So the flow is split at the approval point:

    POST /api/plan    work out what would happen, hold it, describe it
    POST /api/apply   the held plan is approved, carry it out

The held plan is the same saved Terraform plan the command line uses, so what
runs is still exactly what was shown. Nothing is re-planned in between: that
is the property the whole approval step exists to guarantee, and it would be
easy to lose here.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from stratus.cost import describe as describe_cost
from stratus.explain import explain
from stratus.policy import describe_warnings
from stratus.web_page import PAGE

# The command line loads this and the web app did not, so a server started
# outside a shell that already had the variables exported failed with "No
# Azure subscription configured" — which reads like a missing account rather
# than a missing file. Found by running it, not by reading it.
load_dotenv()

PENDING_TTL = timedelta(minutes=15)
"""How long a described plan stays valid.

A plan describes the world as it was when it was made. Left long enough, the
account moves underneath it and the description stops being true — so an
approval given against a stale description is not really consent. Expiring
them forces a fresh look rather than silently applying something old.
"""


@dataclass
class Pending:
    """A plan that has been described and is waiting on an answer."""

    id: str
    request: str
    question: str
    stratus: Any
    config: Any
    """The configuration that produced the plan, kept so the change can be
    recorded in history with the same detail a command-line build gets."""

    created: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def expired(self) -> bool:
        return datetime.now(UTC) - self.created > PENDING_TTL


class BuildRequest(BaseModel):
    request: str
    workspace: str = "default"


class ApplyRequest(BaseModel):
    id: str
    answer: str


def create_app(subscription_id: str | None = None) -> FastAPI:
    app = FastAPI(title="Stratus", docs_url="/api/docs")
    pending: dict[str, Pending] = {}

    def _subscription() -> str:
        found = subscription_id or os.getenv("AZURE_SUBSCRIPTION_ID")
        if not found:
            raise HTTPException(500, "No Azure subscription configured.")
        return found

    def _sweep() -> None:
        for key in [k for k, v in pending.items() if v.expired]:
            del pending[key]

    # HEAD as well as GET: load balancers and uptime checks probe with HEAD,
    # and a 405 there reads as "the service is broken" rather than "wrong
    # verb". Azure, Render and Fly all do this by default.
    @app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
    def index() -> str:
        return PAGE

    @app.api_route("/api/health", methods=["GET", "HEAD"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/account")
    def account() -> dict[str, Any]:
        from stratus.azure import LiveAzureReader
        from stratus.summarise import summarise

        snapshot = LiveAzureReader(_subscription()).read()
        return {"summary": summarise(snapshot), "count": len(snapshot)}

    @app.post("/api/plan")
    def plan(body: BuildRequest) -> dict[str, Any]:
        """Work out what would happen, and describe it. Nothing is built."""
        from stratus.pipeline import Stratus

        _sweep()
        stratus = Stratus(_subscription(), workspace=body.workspace)

        try:
            config = stratus.generator.generate(
                body.request,
                stratus.reader.read(),
                validate=stratus._validate,
                region=stratus.region,
            )
        except Exception as exc:  # noqa: BLE001 - shown to the user, not swallowed
            raise HTTPException(400, str(exc)) from exc

        proposed = stratus._last_plan
        if proposed is None:
            raise HTTPException(500, "Could not work out what to change.")

        if proposed.is_empty:
            return {
                "nothing_to_do": True,
                "summary": "You already have everything you asked for.",
            }

        from stratus.cost import estimate as estimate_cost

        cost = estimate_cost(proposed, region=stratus.region)
        blocks = [
            describe_cost(cost),
            describe_warnings(stratus._last_review) if stratus._last_review else "",
            explain(proposed),
        ]
        question = "\n\n".join(b for b in blocks if b)

        entry = Pending(
            id=uuid.uuid4().hex[:12],
            request=body.request,
            question=question,
            stratus=stratus,
            config=config,
        )
        pending[entry.id] = entry

        return {
            "id": entry.id,
            "summary": config.summary,
            "assumptions": config.assumptions,
            "question": question,
            "destructive": proposed.is_destructive,
            "monthly_cost": cost.fixed_monthly,
            "repairs": stratus.generator.repairs_used,
        }

    @app.post("/api/apply")
    def apply(body: ApplyRequest) -> dict[str, Any]:
        """Carry out a plan that was described and approved."""
        from stratus.explain import confirmation_is_valid

        entry = pending.get(body.id)
        if entry is None:
            raise HTTPException(
                404,
                "That plan is no longer available. Ask again to get a fresh "
                "one — the account may have changed since.",
            )
        if entry.expired:
            del pending[body.id]
            raise HTTPException(
                410,
                "That plan is too old to be trusted. Ask again to get a fresh one.",
            )

        stratus = entry.stratus
        proposed = stratus._last_plan

        if not confirmation_is_valid(proposed, body.answer):
            del pending[body.id]
            return {"applied": False, "message": "Cancelled. Nothing was changed."}

        # Single use. Leaving it available would let the same approval be
        # replayed against an account that has since moved on.
        del pending[body.id]

        lines: list[str] = []
        try:
            stratus.runner.apply(on_line=lines.append)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, str(exc)) from exc

        from stratus.models import Action

        record = stratus.history.record(
            request=entry.request,
            summary=entry.config.summary,
            files=entry.config.as_dict(),
            created=[c.address for c in proposed.of(Action.CREATE)],
            changed=[c.address for c in proposed.of(Action.UPDATE, Action.REPLACE)],
            destroyed=[c.address for c in proposed.of(Action.DELETE)],
        )

        return {
            "applied": True,
            "message": "Done.",
            "summary": entry.config.summary,
            "change_id": record.id,
            # The tail only. The full Terraform log is long and mostly
            # repeated "still creating" lines.
            "log": [line for line in lines if line.strip()][-20:],
        }

    @app.get("/api/history")
    def history(workspace: str = "default") -> dict[str, Any]:
        from stratus.pipeline import Stratus

        stratus = Stratus(_subscription(), workspace=workspace)
        return {
            "entries": [
                {
                    "id": e.id,
                    "at": e.at,
                    "request": e.request,
                    "summary": e.summary,
                    "created": len(e.created),
                    "changed": len(e.changed),
                    "destroyed": len(e.destroyed),
                }
                for e in stratus.history.entries()
            ]
        }

    @app.get("/api/drift")
    def drift(workspace: str = "default") -> dict[str, Any]:
        from stratus.drift import explain_drift
        from stratus.pipeline import Stratus

        stratus = Stratus(_subscription(), workspace=workspace)
        found = stratus.check_drift()
        return {"has_drift": found.has_drift, "description": explain_drift(found)}

    # Exposed so tests can age a pending plan without waiting fifteen
    # minutes. Nothing in the application reads it.
    app.state.pending = pending

    return app


app = create_app()
