"""Tests for the order the steps happen in.

The order is the safety property. Reading before planning is what stops
duplicates; explaining before asking is what makes an answer consent;
applying only after approval is the whole point. These tests assert that
order rather than any individual step, which is covered elsewhere.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from stratus.agent.generator import GeneratedConfig, GeneratedFile
from stratus.history import History
from stratus.models import Action, Plan, PlannedChange, Snapshot
from stratus.pipeline import Stratus


def _plan(*actions: Action) -> Plan:
    return Plan(
        changes=[
            PlannedChange(
                address=f"azurerm_storage_account.r{i}",
                type="azurerm_storage_account",
                name=f"r{i}",
                action=action,
                after={"name": f"r{i}"},
            )
            for i, action in enumerate(actions)
        ]
    )


def _stratus(plan: Plan, tmp_path) -> Stratus:
    """A Stratus with every external dependency replaced.

    Built through the real constructor with parts injected, so adding a field
    to Stratus cannot silently leave this half-initialised.
    """
    reader = MagicMock()
    reader.read.return_value = Snapshot(subscription_id="test-sub")

    config = GeneratedConfig(
        files=[GeneratedFile(filename="main.tf", contents="resource {}")],
        summary="A thing.",
    )

    runner = MagicMock()
    runner.plan.return_value = plan
    runner.state_resources.return_value = []

    generator = MagicMock()
    generator.repairs_used = 0
    generator.cost = 0.0

    def generate(request, existing, validate=None, region=None):
        # Call the validation callback, as the real generator does. That is
        # where planning and the safety review happen, so a mock that skips
        # it would leave the pipeline testing a path that cannot occur.
        if validate is not None:
            validate(config.as_dict())
        return config

    generator.generate.side_effect = generate

    return Stratus(
        "test-sub",
        workspace="test",
        reader=reader,
        runner=runner,
        generator=generator,
        backend=MagicMock(),
        # A real directory. Deriving it from the mocked runner produced a
        # path called "MagicMock/mock.workdir.__truediv__()/..." and the
        # suite wrote history files into the repository.
        history=History(tmp_path / "history"),
    )


class TestApprovalGate:
    def test_applies_when_approved(self, tmp_path):
        s = _stratus(_plan(Action.CREATE), tmp_path)
        outcome = s.build("a website", confirm=lambda _: "yes")
        assert outcome.applied
        s.runner.apply.assert_called_once()

    def test_does_not_apply_when_refused(self, tmp_path):
        s = _stratus(_plan(Action.CREATE), tmp_path)
        outcome = s.build("a website", confirm=lambda _: "no")
        assert not outcome.applied
        assert outcome.cancelled_reason == "not approved"
        s.runner.apply.assert_not_called()

    def test_silence_is_not_consent(self, tmp_path):
        # An empty answer is what a closed pipe or a Ctrl-C produces. It must
        # never be treated as agreement.
        s = _stratus(_plan(Action.CREATE), tmp_path)
        assert not s.build("a website", confirm=lambda _: "").applied
        s.runner.apply.assert_not_called()

    def test_a_destructive_plan_refuses_a_plain_yes(self, tmp_path):
        s = _stratus(_plan(Action.DELETE), tmp_path)
        outcome = s.build("remove the old one", confirm=lambda _: "yes")
        assert not outcome.applied
        s.runner.apply.assert_not_called()

    def test_a_destructive_plan_accepts_the_typed_word(self, tmp_path):
        s = _stratus(_plan(Action.DELETE), tmp_path)
        assert s.build("remove the old one", confirm=lambda _: "DELETE").applied

    def test_the_user_is_shown_the_plan_before_being_asked(self, tmp_path):
        # Approval means nothing if the text arrives after the question.
        s = _stratus(_plan(Action.CREATE), tmp_path)
        shown = []

        def confirm(text):
            shown.append(text)
            return "yes"

        s.build("a website", confirm=confirm)
        assert len(shown) == 1
        assert "Go ahead?" in shown[0]
        assert "place to keep files" in shown[0]

    def test_a_destructive_plan_is_flagged_in_the_text(self, tmp_path):
        s = _stratus(_plan(Action.DELETE), tmp_path)
        shown = []
        s.build("x", confirm=lambda t: shown.append(t) or "")
        assert "DESTROY" in shown[0]


class TestOrdering:
    def test_reads_the_account_before_generating(self, tmp_path):
        # This is what stops duplicates: the model cannot avoid rebuilding
        # something it was never told exists.
        s = _stratus(_plan(Action.CREATE), tmp_path)
        s.build("a website", confirm=lambda _: "yes")

        s.reader.read.assert_called_once()
        passed_snapshot = s.generator.generate.call_args.args[1]
        assert passed_snapshot is s.reader.read.return_value

    def test_plans_before_asking(self, tmp_path):
        s = _stratus(_plan(Action.CREATE), tmp_path)
        order = []
        s.runner.plan.side_effect = lambda: order.append("plan") or _plan(Action.CREATE)
        s.build("x", confirm=lambda _: order.append("ask") or "yes")
        assert order == ["plan", "ask"]

    def test_apply_takes_no_configuration(self, tmp_path):
        # apply() must run the saved plan, not re-derive one. Otherwise what
        # executes can differ from what was approved.
        s = _stratus(_plan(Action.CREATE), tmp_path)
        s.build("x", confirm=lambda _: "yes")
        assert s.runner.apply.call_args.args == ()


class TestNothingToDo:
    def test_does_not_ask_when_nothing_would_change(self, tmp_path):
        # Asking "shall I do nothing?" is noise. This is the payoff for
        # reading the account first.
        s = _stratus(Plan(changes=[]), tmp_path)
        asked = []
        outcome = s.build(
            "the thing I already have", confirm=lambda t: asked.append(t) or "yes"
        )

        assert outcome.cancelled_reason == "nothing to do"
        assert asked == []
        s.runner.apply.assert_not_called()

    def test_a_plan_of_only_no_ops_counts_as_nothing(self, tmp_path):
        s = _stratus(_plan(Action.NO_OP, Action.NO_OP), tmp_path)
        outcome = s.build("x", confirm=lambda _: "yes")
        assert outcome.cancelled_reason == "nothing to do"
        s.runner.apply.assert_not_called()


class TestDestroy:
    def test_refuses_without_the_typed_word(self, tmp_path):
        s = _stratus(Plan(changes=[]), tmp_path)
        s.runner.state_resources.return_value = ["azurerm_storage_account.data"]
        outcome = s.destroy(confirm=lambda _: "yes")
        assert not outcome.applied
        s.runner.destroy.assert_not_called()

    def test_destroys_with_the_typed_word(self, tmp_path):
        s = _stratus(Plan(changes=[]), tmp_path)
        s.runner.state_resources.return_value = ["azurerm_storage_account.data"]
        assert s.destroy(confirm=lambda _: "DELETE").applied

    def test_lists_what_will_go_before_asking(self, tmp_path):
        s = _stratus(Plan(changes=[]), tmp_path)
        s.runner.state_resources.return_value = ["azurerm_storage_account.data"]
        shown = []
        s.destroy(confirm=lambda t: shown.append(t) or "")
        assert "azurerm_storage_account.data" in shown[0]
        assert "permanently" in shown[0]

    def test_does_not_ask_when_there_is_nothing_to_destroy(self, tmp_path):
        s = _stratus(Plan(changes=[]), tmp_path)
        asked = []
        outcome = s.destroy(confirm=lambda t: asked.append(t) or "DELETE")
        assert outcome.cancelled_reason == "nothing to destroy"
        assert asked == []
        s.runner.destroy.assert_not_called()


class _Answers:
    """Answers a sequence of questions, and remembers what it was asked.

    One callback serves both the plan approval and the recovery choice, so a
    test has to say "yes" first and only then choose. Returning the recovery
    answer to the approval question cancels the build before it ever runs.
    """

    def __init__(self, *answers: str):
        self._answers = list(answers)
        self.asked: list[str] = []

    def __call__(self, text: str) -> str:
        self.asked.append(text)
        return self._answers.pop(0) if self._answers else ""


class TestPartialFailure:
    """A build that dies partway must not leave the user holding the pieces."""

    def _failing(self, tmp_path, survived: list[str], apply_effect=None):
        from stratus.terraform import TerraformError

        s = _stratus(_plan(Action.CREATE, Action.CREATE), tmp_path)
        s.runner.plan.return_value = _plan(Action.CREATE, Action.CREATE)
        s.runner.state_resources.return_value = survived
        s.runner.apply.side_effect = apply_effect or TerraformError(
            ["terraform", "apply"], 1, "", "quota exceeded"
        )
        return s

    def test_does_not_raise_at_the_user(self, tmp_path):
        # Raising would hand them an error and abandon them holding
        # infrastructure they did not ask to keep.
        s = self._failing(tmp_path, ["azurerm_storage_account.r0"])
        outcome = s.build("x", confirm=_Answers("yes", "undo"))
        assert outcome.partial is not None

    def test_works_out_what_survived(self, tmp_path):
        s = self._failing(tmp_path, ["azurerm_storage_account.r0"])
        outcome = s.build("x", confirm=_Answers("yes", "undo"))
        assert outcome.partial.created == ["azurerm_storage_account.r0"]
        assert outcome.partial.missing == ["azurerm_storage_account.r1"]

    def test_offers_a_choice_and_undoes_when_asked(self, tmp_path):
        s = self._failing(tmp_path, ["azurerm_storage_account.r0"])
        outcome = s.build("x", confirm=_Answers("yes", "undo"))
        assert outcome.recovery == "undone"
        s.runner.destroy.assert_called_once()

    def test_replans_before_finishing(self, tmp_path):
        # The world moved when the first attempt partly succeeded, so the
        # saved plan no longer describes reality. Applying it stale is how
        # you get duplicates.
        from stratus.terraform import TerraformError

        s = self._failing(
            tmp_path,
            ["azurerm_storage_account.r0"],
            apply_effect=[
                TerraformError(["terraform", "apply"], 1, "", "transient"),
                "ok",
            ],
        )
        outcome = s.build("x", confirm=_Answers("yes", "finish"))
        assert outcome.recovery == "finished"
        assert outcome.applied
        assert s.runner.plan.call_count == 2

    def test_does_not_loop_when_finishing_fails_again(self, tmp_path):
        # A second identical failure means the cause is not transient.
        # Asking again just wears the user down.
        s = self._failing(tmp_path, ["azurerm_storage_account.r0"])
        answers = _Answers("yes", "finish")
        outcome = s.build("x", confirm=answers)
        assert outcome.recovery == "finish failed"
        assert len(answers.asked) == 2  # the plan approval, then the choice

    def test_an_unrecognised_answer_changes_nothing(self, tmp_path):
        s = self._failing(tmp_path, ["azurerm_storage_account.r0"])
        outcome = s.build("x", confirm=_Answers("yes", "erm"))
        assert outcome.recovery == "left as is"
        s.runner.destroy.assert_not_called()

    def test_a_failure_before_anything_was_made_asks_nothing(self, tmp_path):
        # Nothing survived, so there is nothing to recover.
        s = self._failing(tmp_path, [])
        answers = _Answers("yes", "undo")
        outcome = s.build("x", confirm=answers)
        assert outcome.cancelled_reason == "failed, nothing left behind"
        assert len(answers.asked) == 1  # only the plan approval
        s.runner.destroy.assert_not_called()

    def test_keeps_what_the_cloud_said(self, tmp_path):
        s = self._failing(tmp_path, ["azurerm_storage_account.r0"])
        outcome = s.build("x", confirm=_Answers("yes", "undo"))
        assert "quota exceeded" in str(outcome.error)

    def test_the_recovery_question_describes_the_damage(self, tmp_path):
        s = self._failing(tmp_path, ["azurerm_storage_account.r0"])
        answers = _Answers("yes", "undo")
        s.build("x", confirm=answers)
        recovery_question = answers.asked[1]
        assert "stopped partway" in recovery_question
        assert "costing you money" in recovery_question


class TestReporting:
    def test_carries_the_cost_and_repair_count(self, tmp_path):
        s = _stratus(_plan(Action.CREATE), tmp_path)
        s.generator.repairs_used = 2
        s.generator.cost = 0.0134
        outcome = s.build("x", confirm=lambda _: "yes")
        assert outcome.repairs_used == 2
        assert outcome.cost_usd == pytest.approx(0.0134)

    def test_reports_progress_as_it_goes(self, tmp_path):
        s = _stratus(_plan(Action.CREATE), tmp_path)
        steps = []
        s.build("x", confirm=lambda _: "yes", on_progress=steps.append)
        assert len(steps) >= 3


class TestSafetyRules:
    """A configuration that would expose data never reaches the user."""

    def test_a_blocked_plan_is_sent_back_to_be_rewritten(self, tmp_path):
        # The user should never see "I refuse to build that". They should see
        # the corrected thing. Policy runs inside the validation callback, so
        # the generator's repair loop handles it exactly like a syntax error.
        from stratus.pipeline import PolicyRefused

        dangerous = _plan(Action.CREATE)
        dangerous.changes[0].type = "azurerm_storage_container"
        dangerous.changes[0].after = {"container_access_type": "blob", "name": "leaky"}

        s = _stratus(dangerous, tmp_path)
        with pytest.raises(PolicyRefused, match="read the files"):
            s._validate({"main.tf": "whatever"})

    def test_a_safe_plan_passes_validation(self, tmp_path):
        s = _stratus(_plan(Action.CREATE), tmp_path)
        s._validate({"main.tf": "whatever"})  # must not raise
        assert s._last_plan is not None
        assert not s._last_review.is_blocked

    def test_the_refusal_tells_the_model_what_to_do(self, tmp_path):
        from stratus.pipeline import PolicyRefused

        dangerous = _plan(Action.CREATE)
        dangerous.changes[0].type = "azurerm_nat_gateway"
        dangerous.changes[0].after = {"name": "gw"}

        s = _stratus(dangerous, tmp_path)
        with pytest.raises(PolicyRefused) as caught:
            s._validate({"main.tf": "whatever"})
        assert "Instead:" in str(caught.value)

    def test_warnings_reach_the_approval_screen(self, tmp_path):
        # Warnings are things to weigh before answering, so they belong with
        # the question, not printed earlier where they get skimmed past.
        warned = _plan(Action.CREATE)
        warned.changes[0].type = "azurerm_service_plan"
        warned.changes[0].after = {"sku_name": "P1v3", "name": "plan"}

        s = _stratus(warned, tmp_path)
        answers = _Answers("yes")
        s.build("x", confirm=answers)
        assert "Worth knowing" in answers.asked[0]
        assert "paid size" in answers.asked[0]

    def test_plans_only_once(self, tmp_path):
        # Planning happens inside validation. Doing it again in build() would
        # be a second slow round trip to Azure for an answer already held.
        s = _stratus(_plan(Action.CREATE), tmp_path)
        s.build("x", confirm=_Answers("yes"))
        assert s.runner.plan.call_count == 1


class TestHistoryAndRollback:
    def test_a_successful_build_is_recorded(self, tmp_path):
        s = _stratus(_plan(Action.CREATE), tmp_path)
        s.history = __import__("stratus.history", fromlist=["History"]).History(tmp_path / "h")
        outcome = s.build("a website", confirm=_Answers("yes"))
        assert outcome.history_entry is not None
        assert s.history.entries()[0].request == "a website"

    def test_a_refused_build_is_not_recorded(self, tmp_path):
        # A history full of things that did not happen cannot be trusted to
        # answer "what does this account look like".
        s = _stratus(_plan(Action.CREATE), tmp_path)
        s.build("a website", confirm=_Answers("no"))
        assert s.history.entries() == []

    def test_the_record_keeps_the_configuration(self, tmp_path):
        s = _stratus(_plan(Action.CREATE), tmp_path)
        s.build("x", confirm=_Answers("yes"))
        assert s.history.entries()[0].files == {"main.tf": "resource {}"}

    def test_rollback_refuses_an_unknown_id(self, tmp_path):
        s = _stratus(_plan(Action.CREATE), tmp_path)
        outcome = s.rollback("nope", confirm=_Answers("yes"))
        assert outcome.cancelled_reason == "no such change"
        s.runner.apply.assert_not_called()

    def test_rollback_asks_before_changing_anything(self, tmp_path):
        # Going backwards can destroy things, so it earns no shortcut.
        s = _stratus(_plan(Action.CREATE), tmp_path)
        entry = s.history.record("earlier", "An earlier thing.", {"main.tf": "old"})

        answers = _Answers("no")
        outcome = s.rollback(entry.id, confirm=answers)
        assert outcome.cancelled_reason == "not approved"
        assert len(answers.asked) == 1
        s.runner.apply.assert_not_called()

    def test_rollback_says_what_it_is_going_back_to(self, tmp_path):
        s = _stratus(_plan(Action.CREATE), tmp_path)
        entry = s.history.record("the old website", "s", {"main.tf": "old"})

        answers = _Answers("no")
        s.rollback(entry.id, confirm=answers)
        assert "the old website" in answers.asked[0]
        assert "Rolling back" in answers.asked[0]

    def test_rollback_applies_the_stored_configuration(self, tmp_path):
        s = _stratus(_plan(Action.CREATE), tmp_path)
        entry = s.history.record("earlier", "s", {"main.tf": "the old contents"})

        outcome = s.rollback(entry.id, confirm=_Answers("yes"))
        assert outcome.applied
        written = [c.args for c in s.runner.write_config.call_args_list]
        assert ("main.tf", "the old contents") in written

    def test_rollback_is_itself_recorded(self, tmp_path):
        # Append-only. A rollback is something that happened.
        s = _stratus(_plan(Action.CREATE), tmp_path)
        entry = s.history.record("earlier", "s", {"main.tf": "old"})

        s.rollback(entry.id, confirm=_Answers("yes"))
        newest = s.history.entries()[0]
        assert newest.outcome == f"rolled back to {entry.id}"
        assert len(s.history.entries()) == 2

    def test_rollback_to_the_current_state_changes_nothing(self, tmp_path):
        s = _stratus(Plan(changes=[]), tmp_path)
        entry = s.history.record("earlier", "s", {"main.tf": "old"})

        outcome = s.rollback(entry.id, confirm=_Answers("yes"))
        assert outcome.cancelled_reason == "nothing to do"
        s.runner.apply.assert_not_called()
