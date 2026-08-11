"""A record of every change, and the ability to go back to one.

Infrastructure without history is infrastructure you cannot reason about. Six
weeks after a change, "why is this configured like that?" has no answer, and
"put it back how it was on Tuesday" is not a request anyone can act on.

Every build that reaches the cloud is recorded here: what was asked for, the
exact configuration that produced it, what changed, and when. The
configuration is stored in full rather than as a difference, because a
difference is only meaningful against a base you still have, and the whole
point of this is to survive not having anything else.

Records are append-only. Editing history to make a past state look different
from what actually happened would defeat the only reason to keep it.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Entry:
    """One change that actually reached the cloud."""

    id: str
    at: str
    request: str
    summary: str
    """The plain-English description shown to the user at the time."""

    files: dict[str, str]
    """The complete configuration, not a difference. A difference is only
    meaningful against a base you still have."""

    created: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    destroyed: list[str] = field(default_factory=list)

    outcome: str = "applied"
    """'applied', 'rolled back to <id>', or 'destroyed'."""

    @property
    def when(self) -> datetime:
        return datetime.fromisoformat(self.at)

    def describe(self) -> str:
        """One line, for a list."""
        stamp = self.when.strftime("%d %b %H:%M")
        counts = []
        if self.created:
            counts.append(f"+{len(self.created)}")
        if self.changed:
            counts.append(f"~{len(self.changed)}")
        if self.destroyed:
            counts.append(f"-{len(self.destroyed)}")
        change = " ".join(counts) or "no change"
        return f"{self.id}  {stamp}  {change:<12} {self.request[:48]}"


class History:
    """Append-only history for one workspace.

    One file per entry rather than a single growing document: appending
    cannot corrupt what is already there, and a half-written file loses one
    record instead of all of them.
    """

    def __init__(self, directory: Path | str):
        # Path() will happily accept almost anything and stringify it, so a
        # mistake upstream becomes a real directory with a nonsense name
        # rather than an error. That is exactly what happened: a test passed
        # a mock here and the suite wrote history into a directory called
        # "MagicMock/mock.workdir.__truediv__()/...", fifty files of which
        # were committed before anyone noticed.
        if not isinstance(directory, (str, Path)):
            raise TypeError(
                f"History needs a path, got {type(directory).__name__}. "
                "This usually means the workspace was built with a stand-in "
                "object that has no real directory."
            )

        self.directory = Path(directory)

        self.unreadable: list[tuple[str, str]] = []
        """Files that could not be read, refreshed on every listing."""

    def record(
        self,
        request: str,
        summary: str,
        files: dict[str, str],
        created: list[str] | None = None,
        changed: list[str] | None = None,
        destroyed: list[str] | None = None,
        outcome: str = "applied",
    ) -> Entry:
        entry = Entry(
            # Short, but long enough not to collide in a lifetime of builds,
            # and short enough to type when rolling back.
            id=uuid.uuid4().hex[:8],
            at=_now(),
            request=request,
            summary=summary,
            files=dict(files),
            created=created or [],
            changed=changed or [],
            destroyed=destroyed or [],
            outcome=outcome,
        )
        self.directory.mkdir(parents=True, exist_ok=True)
        # The timestamp leads the filename so a directory listing is already
        # in order, without reading or parsing anything.
        path = self.directory / f"{entry.at.replace(':', '-')}-{entry.id}.json"
        path.write_text(json.dumps(asdict(entry), indent=2))
        return entry

    def entries(self) -> list[Entry]:
        """Every readable change, newest first.

        A damaged file is skipped rather than allowed to hide the rest — but
        it is *counted*, not swallowed. History exists to be trusted, and a
        record that silently vanishes is worse than one that is obviously
        missing: the user concludes the change never happened.
        """
        self.unreadable = []

        if not self.directory.exists():
            return []

        found: list[Entry] = []
        for path in sorted(self.directory.glob("*.json"), reverse=True):
            try:
                found.append(Entry(**json.loads(path.read_text())))
            except (OSError, ValueError, TypeError) as exc:
                self.unreadable.append((path.name, str(exc)))
        return found

    def get(self, entry_id: str) -> Entry | None:
        """Find one entry by id, or by enough of its id to be unambiguous."""
        matches = [e for e in self.entries() if e.id.startswith(entry_id)]
        return matches[0] if len(matches) == 1 else None

    def latest(self) -> Entry | None:
        found = self.entries()
        return found[0] if found else None


def describe_history(
    entries: list[Entry], unreadable: list[tuple[str, str]] | None = None
) -> str:
    if not entries and not unreadable:
        return "Nothing has been built in this workspace yet."

    lines = [f"{len(entries)} change{'' if len(entries) == 1 else 's'}, newest first:", ""]
    lines.extend(f"  {entry.describe()}" for entry in entries)
    lines.append("")
    lines.append("To go back to one:  stratus rollback <id>")

    if unreadable:
        # Said out loud. A record that silently vanishes is worse than one
        # that is obviously missing.
        lines.append("")
        lines.append(f"{len(unreadable)} record(s) could not be read:")
        lines.extend(f"  - {name}" for name, _ in unreadable)

    return "\n".join(lines)


def describe_entry(entry: Entry) -> str:
    lines = [
        f"Change {entry.id}",
        f"  when:     {entry.when.strftime('%d %B %Y at %H:%M UTC')}",
        f"  asked:    {entry.request}",
        f"  result:   {entry.summary}",
    ]
    if entry.created:
        lines.append(f"  created:  {len(entry.created)}")
    if entry.changed:
        lines.append(f"  changed:  {len(entry.changed)}")
    if entry.destroyed:
        lines.append(f"  removed:  {len(entry.destroyed)}")
    if entry.outcome != "applied":
        lines.append(f"  note:     {entry.outcome}")
    return "\n".join(lines)
