"""The flowchart CSV format, shared by every part of the agent.

One row per step. If the target app's schema changes, change it here and
nowhere else.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

HEADER = [
    "step_id", "drawio_id", "step_name", "step_type", "actor", "phase", "description",
    "form_required", "rule_ref", "deadline_question", "timeframe", "deadline_rule",
    "next_steps", "next_step_conditions", "reverse_steps", "branch", "notes",
    "pos_x", "pos_y", "node_width",
]
LAYOUT_COLUMNS = ["pos_x", "pos_y", "node_width"]
OPTIONAL_COLUMNS = [
    "required_completed", "completion_rules", "show_in_tickler", "show_upload",
    "show_analyze", "show_lawyer", "show_dates", "upload_config", "dates_config",
]
STEP_TYPES = ["START", "PLEADING", "ACTION", "EVENT", "NOTICE", "DECISION", "CONDITION", "MOTION", "OUTCOME"]
ACTORS = ["Plaintiff", "Defendant", "Both", "Moving party", "Responding party", "Court", "Registrar", "Mediator"]
NO_DATES_TYPES = ["DECISION", "CONDITION"]  # no dates/upload tab in the app
END = "END"

# <basis><+|-><N><d|w|m|y>, one or more offsets: claim+5y, pretrial-90d, struck_off+2y-30d
DEADLINE_RULE = re.compile(r"^[a-z][a-z0-9_]*([+-]\d+[dwmy])+$")
OFFSET = re.compile(r"([+-])(\d+)([dwmy])")
UNIT_WORDS = {"d": "day", "w": "week", "m": "month", "y": "year"}


@dataclass
class Offset:
    sign: str   # "+" or "-"
    amount: int
    unit: str   # d, w, m, y


@dataclass
class DeadlineRule:
    basis: str
    offsets: list[Offset]

    def __str__(self) -> str:
        return self.basis + "".join(f"{o.sign}{o.amount}{o.unit}" for o in self.offsets)

    @property
    def direction(self) -> str:
        """Sign of the first (largest) offset: '+' counts forward, '-' counts back."""
        return self.offsets[0].sign


def parse_deadline_rule(text: str) -> DeadlineRule | None:
    if not DEADLINE_RULE.match(text or ""):
        return None
    basis = re.match(r"^[a-z][a-z0-9_]*", text).group(0)
    offsets = [Offset(s, int(n), u) for s, n, u in OFFSET.findall(text)]
    return DeadlineRule(basis, offsets)


def split_list(value: str) -> list[str]:
    """Semicolon list, keeping empty slots (conditions are positional)."""
    return [s.strip() for s in (value or "").split(";")]


@dataclass
class Step:
    row: dict[str, str]
    line: int = 0

    def get(self, col: str) -> str:
        return (self.row.get(col) or "").strip()

    @property
    def id(self) -> str:
        return self.get("step_id")

    @property
    def type(self) -> str:
        return self.get("step_type") or self.get("blob_type")

    @property
    def next(self) -> list[str]:
        return [t for t in split_list(self.get("next_steps")) if t]

    @property
    def targets(self) -> list[str]:
        return [t for t in self.next if t != END]

    @property
    def conditions(self) -> list[str]:
        raw = self.get("next_step_conditions")
        return [] if raw == "" else split_list(raw)

    @property
    def rule(self) -> DeadlineRule | None:
        return parse_deadline_rule(self.get("deadline_rule"))


@dataclass
class Flowchart:
    name: str
    header: list[str]
    steps: list[Step]
    path: Path | None = None
    ragged_rows: list[tuple[int, str, int]] = field(default_factory=list)

    @property
    def by_id(self) -> dict[str, Step]:
        return {s.id: s for s in self.steps if s.id}

    def out_edges(self) -> dict[str, list[str]]:
        return {s.id: s.targets for s in self.steps if s.id}

    def to_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(self.header)
        for s in self.steps:
            w.writerow([s.row.get(h, "") for h in self.header])
        return buf.getvalue()


def read_flowchart(path: str | Path) -> Flowchart:
    path = Path(path)
    return parse_flowchart(path.read_text(encoding="utf-8-sig"), name=path.stem, path=path)


def parse_flowchart(text: str, name: str = "flowchart", path: Path | None = None) -> Flowchart:
    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if not rows:
        return Flowchart(name, [], [], path)
    header = [h.strip() for h in rows[0]]
    steps, ragged = [], []
    for i, r in enumerate(rows[1:], start=2):
        if len(r) != len(header):
            ragged.append((i, r[0] if r else "", len(r)))
        steps.append(Step(dict(zip(header, r)), line=i))
    return Flowchart(name, header, steps, path, ragged)
