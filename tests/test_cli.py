"""Tests for the command line.

Mostly about argument handling, which is the part users notice when it is
wrong and nobody thinks to test.
"""

from __future__ import annotations

from stratus.__main__ import main


class TestSharedOptions:
    """--workspace and --subscription must work either side of the command."""

    def _workspace(self, argv, monkeypatch) -> str:
        seen = {}

        class FakeStratus:
            def __init__(self, subscription, workspace="default", **kw):
                seen["subscription"] = subscription
                seen["workspace"] = workspace

            def check_drift(self):
                from stratus.drift import Drift

                return Drift()

        monkeypatch.setattr("stratus.pipeline.Stratus", FakeStratus)
        main(argv)
        return seen["workspace"]

    def test_before_the_subcommand(self, monkeypatch):
        assert (
            self._workspace(
                ["--subscription", "s", "--workspace", "mine", "drift"], monkeypatch
            )
            == "mine"
        )

    def test_after_the_subcommand(self, monkeypatch):
        # How people actually write it. argparse rejects this unless the
        # option is attached to the subparser too.
        assert (
            self._workspace(
                ["drift", "--subscription", "s", "--workspace", "mine"], monkeypatch
            )
            == "mine"
        )

    def test_defaults_when_given_neither(self, monkeypatch):
        assert self._workspace(["--subscription", "s", "drift"], monkeypatch) == "default"

    def test_a_top_level_value_is_not_overwritten_by_the_subcommand_default(self, monkeypatch):
        # The argparse trap this design exists to avoid: with an ordinary
        # default on the subparser, the top-level value is silently replaced.
        assert (
            self._workspace(
                ["--workspace", "mine", "--subscription", "s", "drift"], monkeypatch
            )
            == "mine"
        )


class TestDemoMode:
    def test_runs_with_no_arguments_and_no_cloud(self, capsys):
        # A fresh clone should do something immediately.
        assert main([]) == 0
        assert "demo account" in capsys.readouterr().out

    def test_show_without_live_uses_the_demo(self, capsys):
        assert main(["show"]) == 0
        assert "nothing billed" in capsys.readouterr().out


class TestDriftExitCode:
    def test_exits_zero_when_clean(self, monkeypatch):
        from stratus.drift import Drift

        class Clean:
            def __init__(self, *a, **k):
                pass

            def check_drift(self):
                return Drift()

        monkeypatch.setattr("stratus.pipeline.Stratus", Clean)
        assert main(["--subscription", "s", "drift"]) == 0

    def test_exits_non_zero_when_things_moved(self, monkeypatch):
        # So a scheduled job can raise an alarm rather than log quietly.
        from stratus.drift import Drift, DriftItem

        class Drifted:
            def __init__(self, *a, **k):
                pass

            def check_drift(self):
                return Drift(
                    vanished=[DriftItem("a.b", "vanished", "azurerm_storage_account", "b")]
                )

        monkeypatch.setattr("stratus.pipeline.Stratus", Drifted)
        assert main(["--subscription", "s", "drift"]) == 1
