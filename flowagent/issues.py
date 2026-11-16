"""One finding from a check. The repair loop feeds errors back to the model;
the report turns everything else into questions for the lawyers."""
from __future__ import annotations

from dataclasses import asdict, dataclass

ERROR, WARNING, INFO = "error", "warning", "info"
ORDER = {ERROR: 0, WARNING: 1, INFO: 2}


@dataclass(frozen=True)
class Issue:
    code: str            # stable id, e.g. G02; see docs/CHECKS.md
    severity: str        # error | warning | info
    message: str
    step_id: str = ""
    chart: str = ""
    hint: str = ""       # what would fix it; sent to the model in the repair round

    def line(self) -> str:
        where = f"{self.step_id}: " if self.step_id else ""
        return f"{self.severity.upper():7} {self.code} {where}{self.message}"

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v}


def errors(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity == ERROR]


def sort_issues(issues: list[Issue]) -> list[Issue]:
    return sorted(issues, key=lambda i: (ORDER[i.severity], i.code, i.step_id))
