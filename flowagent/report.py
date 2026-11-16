"""What a run leaves behind for the lawyers and for the record."""
from __future__ import annotations

import json
import time

from . import __version__, prompts
from .issues import ERROR, INFO, Issue
from .schema import Flowchart


def open_questions(chart: Flowchart, issues: list[Issue], review: dict) -> list[dict]:
    """Everything a person has to decide: the model's own doubts, plus every
    checker finding the loop could not clear."""
    out = []
    for s in chart.steps:
        r = review.get(s.id, {})
        if r.get("question") or r.get("confidence") in ("medium", "low"):
            out.append({"step_id": s.id, "step_name": s.get("step_name"), "source": "model",
                        "confidence": r.get("confidence", ""),
                        "question": r.get("question") or "Marked uncertain by the model; check this box against the chart."})
    for i in issues:
        if i.severity == INFO:
            continue
        step = chart.by_id.get(i.step_id)
        out.append({"step_id": i.step_id, "step_name": step.get("step_name") if step else "",
                    "source": f"checker {i.code}", "confidence": "",
                    "question": ("UNRESOLVED ERROR: " if i.severity == ERROR else "") + i.message})
    return out


def write_run(result, source, provider, review: dict, questions: list[dict], prefix: str) -> None:
    out, chart, ev = result.out_dir, result.chart, result.evidence
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{chart.name}.csv").write_text(chart.to_csv(), encoding="utf-8")
    (out / f"{chart.name}.evidence.json").write_text(ev.to_json(), encoding="utf-8")
    (out / f"{chart.name}.verify.md").write_text(verify_sheet(result, source, review), encoding="utf-8")
    (out / "OPEN-QUESTIONS.md").write_text(questions_sheet(result, source, questions), encoding="utf-8")
    (out / "run.json").write_text(json.dumps({
        "status": result.status, "chart": chart.name, "prefix": prefix,
        "source": {"file": source.path.name, "text_kind": source.kind or "none", "words": len(source.text.split())},
        "agent_version": __version__, "prompt_version": prompts.PROMPT_VERSION,
        "provider": provider.name, "model": provider.model,
        "finished": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "repair_rounds": result.rounds, "steps": len(chart.steps), "open_questions": len(questions),
        "llm_calls": provider.calls, "rounds": result.history,
    }, indent=2), encoding="utf-8")


def _cell(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")


STATUS_LINE = {
    "PASS": "PASS: the checker found no errors and nothing was flagged. It still needs a lawyer's sign-off.",
    "NEEDS_REVIEW": "NEEDS REVIEW: the checker found no errors; the questions below need a lawyer.",
    "FAILED": "FAILED: errors remain after the repair rounds. Do not import this draft.",
}
GROUNDING = {
    "text_layer": "Quotes were checked against the PDF's embedded text.",
    "ocr": "Quotes were checked against OCR of the page (the PDF has no embedded text). OCR misreads some words.",
    "": "Quotes were NOT checked against the source: no text could be read from the PDF. Compare every quote by eye.",
}


def verify_sheet(result, source, review: dict) -> str:
    chart, ev = result.chart, result.evidence
    deadlines = [s for s in chart.steps if s.get("deadline_rule")]
    lines = [
        f"# Verification sheet: {chart.name}", "",
        f"- Source: `{source.path.name}`",
        *[f'- Chart text: "{q}"' for q in ev.chart_level()],
        f"- CSV: `{chart.name}.csv` - {len(chart.steps)} steps, {len(deadlines)} computed deadlines.",
        f"- Drafted by the agent ({result.rounds} repair round(s)). {STATUS_LINE[result.status]}",
        f"- {GROUNDING.get(source.kind, GROUNDING[''])}", "",
        'Check each row against the PDF. "Exact source text" is what the agent says is printed in or '
        "beside the box; ` / ` separates the box text from arrow labels.", "",
        "## Steps", "",
        "| step_id | step name | exact source text | rule_ref | deadline_rule | confidence | question for the lawyer |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in chart.steps:
        r = review.get(s.id, {})
        lines.append("| " + " | ".join(_cell(x) for x in (
            s.id, s.get("step_name"), " / ".join(ev.for_step(s.id)), s.get("rule_ref"),
            s.get("deadline_rule"), r.get("confidence", ""), r.get("question", ""))) + " |")
    lines += ["", "## Arrows", "", "| from | to | label |", "|---|---|---|"]
    for s in chart.steps:
        conds = s.conditions + [""] * len(s.next)
        for t, c in zip(s.next, conds):
            to = chart.by_id.get(t)
            lines.append(f"| {s.id} {_cell(s.get('step_name'))} | {t} {_cell(to.get('step_name')) if to else ''} | {_cell(c)} |")
    lines += ["", "## Deadlines", "", "| step_id | question the app asks | text shown | rule computed |", "|---|---|---|---|"]
    for s in deadlines:
        lines.append(f"| {s.id} | {_cell(s.get('deadline_question'))} | {_cell(s.get('timeframe'))} | {s.get('deadline_rule')} |")
    lines += ["", "## Not printed on the chart", "",
              "- `actor`, `step_type`, `phase` and `deadline_question` on every row are the agent's classification and wording.",
              "", "## Sign-off", "",
              "- [ ] Every box on the PDF has a row, and every row is a box on the PDF",
              "- [ ] Every arrow matches", "- [ ] Rule references and forms match", "- [ ] Deadlines match", "",
              "Reviewed by: ____________________  Date: ____________", ""]
    return "\n".join(lines)


def questions_sheet(result, source, questions: list[dict]) -> str:
    lines = [f"# Open questions: {result.chart.name}", "",
             f"Source: `{source.path.name}`. {STATUS_LINE[result.status]}", ""]
    if not questions:
        lines.append("None.")
    for q in questions:
        who = f"**{q['step_id']}** {q['step_name']}".strip() if q["step_id"] else "**Whole chart**"
        conf = f", {q['confidence']} confidence" if q["confidence"] else ""
        lines.append(f"- {who} ({q['source']}{conf}): {q['question']}")
    return "\n".join(lines) + "\n"
