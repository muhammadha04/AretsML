"""The loop: ingest -> extract -> check -> repair -> report.

The model drafts. The checker decides. A lawyer signs off. Nothing here writes
into the app or its data folder: a run produces files for review, and a chart
goes live only when a reviewer imports it by hand.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import prompts, report
from .checks import check_flowchart
from .draft import build, tool_schema
from .evidence import Evidence
from .ingest import read_source
from .issues import ERROR, WARNING, Issue, errors, sort_issues
from .llm import Provider
from .schema import Flowchart

PASS, NEEDS_REVIEW, FAILED = "PASS", "NEEDS_REVIEW", "FAILED"


@dataclass
class RunResult:
    status: str
    chart: Flowchart
    evidence: Evidence
    issues: list[Issue]
    rounds: int
    out_dir: Path
    question_count: int = 0
    history: list[dict] = field(default_factory=list)


def assess(draft: dict, name: str, prefix: str, branch: str, source_text: str, source_kind: str,
           challenged: frozenset = frozenset()):
    chart, evidence, shape, review = build(draft, name, prefix, branch)
    evidence.source_text, evidence.source_kind = source_text, source_kind
    issues = shape + check_flowchart(chart, evidence, require_evidence=True)
    return chart, evidence, sort_issues([_soften(i, challenged) for i in issues]), review


def _soften(issue: Issue, challenged: frozenset) -> Issue:
    """A quote the text search cannot find is sent back to the model once. If the model
    looks again and keeps it, the search may be what is wrong (text extraction and OCR both
    miss light text on a dark box), so it becomes a warning for a person to settle by eye."""
    if issue.code == "G02" and issue.severity == ERROR and (issue.step_id, issue.message) in challenged:
        return replace(issue, severity=WARNING, message=issue.message +
                       " The model kept this quote after being asked to re-check; compare it with the page by eye")
    return issue


def run_agent(pdf: Path, provider: Provider, out_root: Path, prefix: str, name: str | None = None,
              max_rounds: int = 3, branch: str = "") -> RunResult:
    name = name or pdf.stem.lower().replace(" ", "-")
    source = read_source(pdf)
    out_dir = out_root / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}"
    (out_dir / "llm").mkdir(parents=True, exist_ok=True)
    tool = tool_schema()
    history: list[dict] = []

    def call(text: str, n: int) -> dict:
        draft = provider.call_tool(prompts.SYSTEM, text, tool, pdf=source.pdf_bytes)
        (out_dir / "llm" / f"{n:02d}.json").write_text(json.dumps(draft, indent=1, ensure_ascii=False), encoding="utf-8")
        return draft

    # Round 0: first draft
    draft = call(prompts.extract_text(pdf.name, source.text, source.kind), 1)
    chart, evidence, issues, review = assess(draft, name, prefix, branch, source.text, source.kind)
    history.append(_round(0, issues))

    # Repair rounds: only errors go back; warnings become questions for the lawyers
    rounds, seen = 0, {_signature(issues)}
    while errors(issues) and rounds < max_rounds:
        rounds += 1
        challenged = frozenset((i.step_id, i.message) for i in errors(issues) if i.code == "G02")
        draft = call(prompts.repair_text(pdf.name, source.text, source.kind, draft, errors(issues)), rounds + 1)
        chart, evidence, issues, review = assess(draft, name, prefix, branch, source.text, source.kind, challenged)
        history.append(_round(rounds, issues))
        sig = _signature(issues)
        if sig in seen:   # the model is going in circles: stop and hand over to a person
            break
        seen.add(sig)

    questions = report.open_questions(chart, issues, review)
    status = FAILED if errors(issues) else (NEEDS_REVIEW if questions else PASS)
    result = RunResult(status, chart, evidence, issues, rounds, out_dir, len(questions), history)
    report.write_run(result, source, provider, review, questions, prefix)
    return result


def _round(n: int, issues: list[Issue]) -> dict:
    return {"round": n, "errors": len(errors(issues)), "issues": [i.to_dict() for i in issues]}


def _signature(issues: list[Issue]) -> frozenset:
    return frozenset((i.code, i.step_id, i.message) for i in errors(issues))
