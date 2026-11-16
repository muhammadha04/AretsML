"""The draft: what the model fills in, and how code turns it into CSV rows.

The model never writes a step_id, a deadline_rule string or a date. It gives
short keys and structured deadline fields; this module builds the rest.
"""
from __future__ import annotations

import re

from .checks.deadlines import bases
from .evidence import CHART, Evidence
from .issues import ERROR, Issue
from .schema import ACTORS, HEADER, STEP_TYPES, Flowchart, Step

TOOL_NAME = "submit_flowchart"


def tool_schema() -> dict:
    text = {"type": "string"}
    deadline = {
        "type": "object",
        "description": "Only when the chart prints a time limit for this step.",
        "properties": {
            "basis": {"type": "string", "enum": list(bases()),
                      "description": "The event the period is measured from, as drawn on the chart."},
            "offsets": {"type": "array", "minItems": 1, "items": {
                "type": "object",
                "properties": {"sign": {"type": "string", "enum": ["+", "-"],
                                        "description": "+ after the basis event, - before it"},
                               "amount": {"type": "integer", "minimum": 1},
                               "unit": {"type": "string", "enum": ["d", "w", "m", "y"]}},
                "required": ["sign", "amount", "unit"]}},
            "timeframe": {**text, "description": "The time limit in the chart's own words."},
            "question": {**text, "description": "The date the app must ask for, as a question."},
        },
        "required": ["basis", "offsets", "timeframe", "question"],
    }
    step = {
        "type": "object",
        "properties": {
            "key": {**text, "description": "Short unique id for this box: capitals, digits, underscore. E.g. SETDOWN."},
            "step_name": {**text, "description": "The box title as printed."},
            "step_type": {"type": "string", "enum": STEP_TYPES},
            "actor": {"type": "string", "enum": ACTORS},
            "phase": text,
            "description": {**text, "description": "The rest of the box text."},
            "form_required": {**text, "description": "Form number, only if printed for this box. Else empty."},
            "rule_ref": {**text, "description": "Rule exactly as printed for this box; if none, the chart-level rule. Else empty."},
            "quotes": {"type": "array", "minItems": 1, "items": text,
                       "description": "Exact words printed in or beside this box, including arrow labels. Word for word."},
            "optional": {"type": "boolean", "description": "True for a dashed box."},
            "deadline": deadline,
            "next": {"type": "array", "minItems": 1, "items": {
                "type": "object",
                "properties": {"to": {**text, "description": "key of the next box, or END"},
                               "condition": {**text, "description": "Label of this option when the paths are alternatives; empty when all paths proceed."}},
                "required": ["to"]}},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "question": {**text, "description": "A question for the reviewing lawyer when anything is unclear. Else empty."},
        },
        "required": ["key", "step_name", "step_type", "actor", "phase", "quotes", "next", "confidence"],
    }
    return {
        "name": TOOL_NAME,
        "description": "Submit the flowchart transcribed from the source document.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {**text, "description": "Chart title as printed."},
                "chart_quotes": {"type": "array", "items": text,
                                 "description": "Exact chart-level text: title, caption, notes."},
                "steps": {"type": "array", "minItems": 1, "items": step},
            },
            "required": ["title", "chart_quotes", "steps"],
        },
    }


def step_id(prefix: str, key: str) -> str:
    key = re.sub(r"[^A-Z0-9_]", "_", str(key).upper()).strip("_")
    return f"{prefix}_{key}" if prefix else key


def build(draft: dict, name: str, prefix: str, branch: str = "") -> tuple[Flowchart, Evidence, list[Issue], dict]:
    """Draft -> (chart, evidence, shape problems, per-step review notes)."""
    problems: list[Issue] = []
    quotes: dict[str, list[str]] = {CHART: [q for q in draft.get("chart_quotes", []) if isinstance(q, str) and q.strip()]}
    review: dict[str, dict] = {}
    steps: list[Step] = []
    raw_steps = draft.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        return Flowchart(name, list(HEADER), []), Evidence(quotes), [Issue("X01", ERROR, "The draft has no steps")], review

    keys = {str(s.get("key", "")) for s in raw_steps if isinstance(s, dict)}
    for n, s in enumerate(raw_steps, start=2):
        if not isinstance(s, dict) or not s.get("key"):
            problems.append(Issue("X01", ERROR, f"Step {n - 1} has no key"))
            continue
        sid = step_id(prefix, s["key"])
        row = {h: "" for h in HEADER}
        row.update(step_id=sid, branch=branch)
        for col in ("step_name", "step_type", "actor", "phase", "description", "form_required", "rule_ref"):
            row[col] = str(s.get(col) or "").strip()

        nxt = [e for e in s.get("next") or [] if isinstance(e, dict) and e.get("to")]
        targets = []
        for e in nxt:
            to = str(e["to"])
            if to != "END" and to not in keys:
                problems.append(Issue("X02", ERROR, f'next points at "{to}", which is not the key of any step', sid,
                                      hint="Use the key of an existing step, or END"))
            targets.append("END" if to == "END" else step_id(prefix, to))
        conds = [str(e.get("condition") or "").strip() for e in nxt]
        row["next_steps"] = ";".join(targets)
        row["next_step_conditions"] = ";".join(conds) if any(conds) else ""

        d = s.get("deadline")
        if isinstance(d, dict):
            try:
                offsets = "".join(f"{o['sign']}{int(o['amount'])}{o['unit']}" for o in d["offsets"])
                row["deadline_rule"] = f"{d['basis']}{offsets}"   # composed here, never by the model
                row["timeframe"] = str(d.get("timeframe") or "").strip()
                row["deadline_question"] = str(d.get("question") or "").strip()
            except (KeyError, TypeError, ValueError):
                problems.append(Issue("X03", ERROR, "deadline is missing basis or offsets", sid))

        notes = []
        if s.get("optional"):
            notes.append("Dashed box on the chart (optional or location-dependent).")
        row["notes"] = " ".join(notes)
        steps.append(Step(row, line=n))
        quotes[sid] = [q.strip() for q in s.get("quotes") or [] if isinstance(q, str) and q.strip()]
        review[sid] = {"confidence": s.get("confidence") or "low", "question": str(s.get("question") or "").strip()}
    return Flowchart(name, list(HEADER), steps), Evidence(quotes), problems, review
