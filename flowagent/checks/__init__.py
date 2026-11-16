"""Deterministic checks. No model is called anywhere under this package."""
from __future__ import annotations

from ..evidence import Evidence
from ..issues import Issue, sort_issues
from ..schema import Flowchart
from . import deadlines, grounding, structure


def check_flowchart(chart: Flowchart, evidence: Evidence | None = None,
                    require_evidence: bool = False) -> list[Issue]:
    """All single-chart checks. Grounding runs only when evidence is supplied
    (or is required, as it always is for a model-written draft)."""
    found = structure.check(chart) + deadlines.check(chart)
    if evidence is not None or require_evidence:
        found += grounding.check(chart, evidence or Evidence(), require_evidence)
    return sort_issues([Issue(**{**i.__dict__, "chart": chart.name}) for i in found])
