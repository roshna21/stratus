"""Tests for the web interface.

The property under test is the one the split flow could easily lose: what
gets applied must be exactly what was described. On the command line the
pipeline holds the plan in memory across the approval; over HTTP it has to
survive two separate requests, and nothing may be re-planned in between.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from stratus.agent.generator import GeneratedConfig, GeneratedFile
from stratus.models import Action, Plan, PlannedChange, Snapshot
from stratus.web import PENDING_TTL, create_app


def _plan(*actions: Action) -> Plan:
    return Plan(changes=[
        PlannedChange(
            address=f"azurerm_storage_account.r{i}", type="azurerm_storage_account",
            name=f"r{i}", action=a, after={"name": f"r{i}"},
        ) for i, a in enumerate(actions)
    ])


@pytest.fixture
def client(monkeypatch, tmp_path):
    """A test client with a Stratus whose parts are all fakes."""
    from stratus.history import History

    plan = _plan(Action.CREATE)
    config = GeneratedConfig(
        files=[GeneratedFile(filename="main.tf", contents="resource {}")],
        summary="A private place for your files.",
        assumptions=["put it in eastus"],
    )

    holder = {}

    class FakeStratus:
        def __init__(self, subscription, workspace="default", **kw):
            self.region = "eastus"
            self.reader = MagicMock()
            self.reader.read.return_value = Snapshot(subscription_id="s")
            self.runner = MagicMock()
            self.generator = MagicMock()
            self.generator.repairs_used = 0
            self.generator.generate.return_value = config
            self.history = History(tmp_path / workspace / "history")
            self._last_plan = holder.get("plan", plan)
            self._last_review = None
            holder["instance"] = self

        def _validate(self, files): pass

    monkeypatch.setattr("stratus.pipeline.Stratus", FakeStratus)
    app = create_app("test-sub")
    return TestClient(app), holder


class TestPlanning:
    def test_describes_without_building(self, client):
        c, holder = client
        r = c.post("/api/plan", json={"request": "a place for files"})
        assert r.status_code == 200
        assert r.json()["summary"] == "A private place for your files."
        holder["instance"].runner.apply.assert_not_called()

    def test_returns_the_approval_text(self, client):
        c, _ = client
        body = c.post("/api/plan", json={"request": "x"}).json()
        assert "place to keep files" in body["question"]
        assert "Go ahead?" in body["question"]

    def test_passes_on_the_assumptions(self, client):
        c, _ = client
        assert c.post("/api/plan", json={"request": "x"}).json()["assumptions"]

    def test_says_when_there_is_nothing_to_do(self, client, monkeypatch):
        c, holder = client
        holder["plan"] = Plan(changes=[])
        body = c.post("/api/plan", json={"request": "x"}).json()
        assert body["nothing_to_do"]
        assert "id" not in body


class TestApproval:
    def test_applies_what_was_described(self, client):
        c, holder = client
        pending = c.post("/api/plan", json={"request": "x"}).json()
        r = c.post("/api/apply", json={"id": pending["id"], "answer": "yes"})
        assert r.json()["applied"]
        holder["instance"].runner.apply.assert_called_once()

    def test_never_replans_between_the_two_requests(self, client):
        # The property the whole approval step exists to guarantee. If the
        # plan were recomputed here, what runs could differ from what was
        # shown and agreed to.
        c, holder = client
        pending = c.post("/api/plan", json={"request": "x"}).json()
        before = holder["instance"].runner.plan.call_count
        c.post("/api/apply", json={"id": pending["id"], "answer": "yes"})
        assert holder["instance"].runner.plan.call_count == before

    def test_refusing_builds_nothing(self, client):
        c, holder = client
        pending = c.post("/api/plan", json={"request": "x"}).json()
        r = c.post("/api/apply", json={"id": pending["id"], "answer": "no"})
        assert not r.json()["applied"]
        holder["instance"].runner.apply.assert_not_called()

    def test_an_approval_cannot_be_replayed(self, client):
        # Single use. Otherwise the same yes could be applied again later,
        # against an account that has moved on.
        c, _ = client
        pending = c.post("/api/plan", json={"request": "x"}).json()
        c.post("/api/apply", json={"id": pending["id"], "answer": "yes"})
        again = c.post("/api/apply", json={"id": pending["id"], "answer": "yes"})
        assert again.status_code == 404

    def test_an_unknown_plan_is_refused(self, client):
        c, _ = client
        assert c.post("/api/apply", json={"id": "nope", "answer": "yes"}).status_code == 404

    def test_a_stale_plan_is_refused(self, client):
        # A plan describes the world as it was. Left long enough the account
        # moves underneath it, and consent given against a stale description
        # is not really consent.
        c, holder = client
        pending = c.post("/api/plan", json={"request": "x"}).json()

        aged = c.app.state.pending[pending["id"]]
        aged.created = aged.created - PENDING_TTL - timedelta(seconds=1)

        r = c.post("/api/apply", json={"id": pending["id"], "answer": "yes"})
        assert r.status_code == 410
        assert "too old" in r.json()["detail"]
        holder["instance"].runner.apply.assert_not_called()

    def test_a_fresh_plan_is_not_refused_as_stale(self, client):
        c, _ = client
        pending = c.post("/api/plan", json={"request": "x"}).json()
        assert c.post(
            "/api/apply", json={"id": pending["id"], "answer": "yes"}
        ).status_code == 200


class TestDestructivePlans:
    def test_flagged_so_the_page_can_demand_the_word(self, client):
        c, holder = client
        holder["plan"] = _plan(Action.DELETE)
        body = c.post("/api/plan", json={"request": "remove it"}).json()
        assert body["destructive"]

    def test_a_plain_yes_is_not_enough(self, client):
        c, holder = client
        holder["plan"] = _plan(Action.DELETE)
        pending = c.post("/api/plan", json={"request": "remove it"}).json()
        r = c.post("/api/apply", json={"id": pending["id"], "answer": "yes"})
        assert not r.json()["applied"]
        holder["instance"].runner.apply.assert_not_called()

    def test_the_typed_word_is(self, client):
        c, holder = client
        holder["plan"] = _plan(Action.DELETE)
        pending = c.post("/api/plan", json={"request": "remove it"}).json()
        r = c.post("/api/apply", json={"id": pending["id"], "answer": "DELETE"})
        assert r.json()["applied"]


class TestHistoryRecording:
    def test_a_build_is_recorded(self, client):
        c, holder = client
        pending = c.post("/api/plan", json={"request": "a place for files"}).json()
        out = c.post("/api/apply", json={"id": pending["id"], "answer": "yes"}).json()
        assert out["change_id"]
        assert holder["instance"].history.entries()[0].request == "a place for files"

    def test_a_refusal_is_not(self, client):
        c, holder = client
        pending = c.post("/api/plan", json={"request": "x"}).json()
        c.post("/api/apply", json={"id": pending["id"], "answer": "no"})
        assert holder["instance"].history.entries() == []


class TestPage:
    def test_serves_a_page(self, client):
        c, _ = client
        r = c.get("/")
        assert r.status_code == 200
        assert "Stratus" in r.text

    def test_the_page_needs_nothing_from_the_internet(self, client):
        # No CDN, no build step. The container is Python and nothing else.
        c, _ = client
        text = c.get("/").text
        assert "https://cdn" not in text
        assert "<script src=" not in text

    def test_health_check(self, client):
        c, _ = client
        assert c.get("/api/health").json() == {"status": "ok"}


class TestOperability:
    """Things that only show up when you actually run the server."""

    def test_head_is_allowed_on_the_page(self, client):
        # Load balancers and uptime checks probe with HEAD. A 405 there reads
        # as "the service is broken" rather than "wrong verb".
        c, _ = client
        assert c.head("/").status_code == 200

    def test_head_is_allowed_on_the_health_check(self, client):
        c, _ = client
        assert c.head("/api/health").status_code == 200

    def test_configuration_is_read_from_a_dotenv_file(self):
        # The web app did not load .env while the command line did, so a
        # server started outside an already-exported shell reported "No Azure
        # subscription configured" — which reads like a missing account.
        import stratus.web as web

        assert "load_dotenv" in open(web.__file__).read()
