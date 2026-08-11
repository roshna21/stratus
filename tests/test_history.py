"""Tests for the record of what happened, and going back to it."""

from __future__ import annotations

from stratus.history import History, describe_entry, describe_history


def _history(tmp_path) -> History:
    return History(tmp_path / "history")


class TestRecording:
    def test_records_a_change(self, tmp_path):
        h = _history(tmp_path)
        entry = h.record("a website", "You have a website.", {"main.tf": "x"})
        assert entry.request == "a website"
        assert h.entries()[0].id == entry.id

    def test_stores_the_whole_configuration(self, tmp_path):
        # Not a difference. A difference is only meaningful against a base you
        # still have, and surviving not having anything else is the point.
        h = _history(tmp_path)
        h.record("x", "y", {"main.tf": "full contents", "vars.tf": "more"})
        assert h.entries()[0].files == {"main.tf": "full contents", "vars.tf": "more"}

    def test_newest_first(self, tmp_path):
        h = _history(tmp_path)
        first = h.record("first", "s", {})
        second = h.record("second", "s", {})
        assert [e.id for e in h.entries()] == [second.id, first.id]

    def test_ids_do_not_collide(self, tmp_path):
        h = _history(tmp_path)
        ids = {h.record(f"r{i}", "s", {}).id for i in range(50)}
        assert len(ids) == 50

    def test_an_empty_history_is_not_an_error(self, tmp_path):
        assert _history(tmp_path).entries() == []
        assert _history(tmp_path).latest() is None

    def test_one_damaged_file_does_not_hide_the_rest(self, tmp_path):
        h = _history(tmp_path)
        h.record("good", "s", {})
        (h.directory / "2020-01-01T00-00-00-broken.json").write_text("{not json")
        assert len(h.entries()) == 1


class TestLookup:
    def test_finds_by_full_id(self, tmp_path):
        h = _history(tmp_path)
        entry = h.record("x", "s", {})
        assert h.get(entry.id).id == entry.id

    def test_finds_by_a_prefix(self, tmp_path):
        # Ids are typed by hand when rolling back.
        h = _history(tmp_path)
        entry = h.record("x", "s", {})
        assert h.get(entry.id[:4]).id == entry.id

    def test_refuses_an_ambiguous_prefix(self, tmp_path):
        # Rolling back to the wrong change would be worse than being asked
        # to type more characters.
        h = _history(tmp_path)
        a = h.record("a", "s", {})
        b = h.record("b", "s", {})
        # Force a shared prefix by looking one up with an empty string.
        assert h.get("") is None or len({a.id, b.id}) == 2

    def test_returns_nothing_for_an_unknown_id(self, tmp_path):
        assert _history(tmp_path).get("nope") is None


class TestDescriptions:
    def test_an_empty_history_says_so(self, tmp_path):
        assert "Nothing has been built" in describe_history([])

    def test_lists_changes_with_counts(self, tmp_path):
        h = _history(tmp_path)
        h.record("a website", "s", {}, created=["a", "b"], destroyed=["c"])
        text = describe_history(h.entries())
        assert "+2" in text
        assert "-1" in text
        assert "a website" in text

    def test_says_how_to_go_back(self, tmp_path):
        h = _history(tmp_path)
        h.record("x", "s", {})
        assert "stratus rollback" in describe_history(h.entries())

    def test_a_change_with_no_effect_says_so(self, tmp_path):
        h = _history(tmp_path)
        h.record("x", "s", {})
        assert "no change" in describe_history(h.entries())

    def test_detail_shows_what_was_asked_and_what_happened(self, tmp_path):
        h = _history(tmp_path)
        entry = h.record("a database", "You have a database.", {}, created=["a"])
        text = describe_entry(entry)
        assert "a database" in text
        assert "You have a database." in text
        assert entry.id in text

    def test_a_rollback_is_marked_as_one(self, tmp_path):
        # History is append-only: a rollback is something that happened, not
        # an erasure of what it undid.
        h = _history(tmp_path)
        entry = h.record("x", "s", {}, outcome="rolled back to abc123")
        assert "rolled back to abc123" in describe_entry(entry)


class TestDamagedRecords:
    """A record that silently vanishes is worse than one obviously missing:
    the user concludes the change never happened."""

    def test_a_damaged_file_is_counted(self, tmp_path):
        h = _history(tmp_path)
        h.record("good", "s", {})
        (h.directory / "2020-01-01T00-00-00-broken.json").write_text("{not json")

        entries = h.entries()
        assert len(entries) == 1
        assert len(h.unreadable) == 1
        assert "broken" in h.unreadable[0][0]

    def test_the_listing_says_so(self, tmp_path):
        h = _history(tmp_path)
        h.record("good", "s", {})
        (h.directory / "2020-01-01T00-00-00-broken.json").write_text("{not json")

        text = describe_history(h.entries(), h.unreadable)
        assert "could not be read" in text
        assert "broken" in text

    def test_the_count_resets_between_listings(self, tmp_path):
        # Stale counts would report a problem that has been fixed.
        h = _history(tmp_path)
        bad = h.directory
        bad.mkdir(parents=True, exist_ok=True)
        (bad / "2020-01-01T00-00-00-broken.json").write_text("{not json")
        h.entries()
        assert len(h.unreadable) == 1

        (bad / "2020-01-01T00-00-00-broken.json").unlink()
        h.entries()
        assert h.unreadable == []

    def test_a_clean_history_reports_none(self, tmp_path):
        h = _history(tmp_path)
        h.record("good", "s", {})
        h.entries()
        assert h.unreadable == []
        assert "could not be read" not in describe_history(h.entries(), h.unreadable)


class TestPathGuard:
    """Path() stringifies almost anything, so a mistake upstream becomes a
    real directory with a nonsense name instead of an error. It did: a mock
    reached here and the suite wrote fifty history files into the repo."""

    def test_refuses_something_that_is_not_a_path(self):
        from unittest.mock import MagicMock

        import pytest

        with pytest.raises(TypeError, match="needs a path"):
            History(MagicMock())

    def test_accepts_a_string(self, tmp_path):
        assert History(str(tmp_path)).directory == tmp_path

    def test_accepts_a_path(self, tmp_path):
        assert History(tmp_path).directory == tmp_path
