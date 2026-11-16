"""Prompts. Kept in one place so they can be reviewed and versioned."""
from __future__ import annotations

import json

from .checks.deadlines import bases
from .issues import Issue

PROMPT_VERSION = "2026-11-16"

SYSTEM = """You transcribe court-procedure flowcharts into structured data for an app \
that lawyers use to track the steps and deadlines of a proceeding. Lawyers \
review and sign off everything you produce, and an automated checker tests it first.

Transcribe; do not practise law.
- Record what is printed on the chart. One step per box. Do not add steps, rules, \
forms or time limits from your own knowledge of the Rules, even if you believe the chart is \
incomplete or out of date. Put that belief in the step's `question` instead.
- `quotes` must be the chart's words, copied exactly, including the label on any arrow \
or bracket that belongs to the box. The checker searches the source for each quote.
- `rule_ref` is the rule exactly as printed for that box. If the box prints none, use the \
chart-level rule from the title. Never cite a rule the chart does not print.
- Arrows: list every box an arrow leads to. If the paths are alternatives, give each a short \
`condition` label; if they all proceed together, leave every condition empty. A box the chart \
ends on has next = END. Every box must be reachable from the first box and must lead to END.
- Deadlines: fill `deadline` only when the chart prints a period for that box. Choose the \
`basis` by which box the line or arrow carrying the period is drawn from. Give the period as \
offsets (sign, amount, unit); "+" for within/after, "-" for before. Do not calculate dates \
and do not write rule strings: the software does both.
- A dashed box is `optional: true`.
- The chart names no actors or step types: choose the closest from the lists, and that is \
expected. If you are unsure of anything else (which box an arrow comes from, what a period \
is measured from), set confidence to medium or low and ask a `question`. A flagged doubt is \
worth more than a confident guess: a wrong deadline can cost a client their claim."""


def extract_text(source_name: str, source_text: str, source_kind: str) -> str:
    parts = [f"Source document: {source_name}.",
             "Deadline bases you may use, and what each means:",
             json.dumps({k: v["label"] for k, v in bases().items()}, indent=2)]
    if source_text.strip():
        label = {"text_layer": "the document's embedded text", "ocr": "OCR of the page (may contain errors)"}.get(
            source_kind, "text of the document")
        parts += [f"Below is {label}. Layout is lost and lines may be out of order; use the page itself for "
                  "which box is which and where arrows go, and this text for exact wording.",
                  "<source_text>", source_text.strip(), "</source_text>"]
    parts.append("Transcribe the flowchart and submit it with the submit_flowchart tool.")
    return "\n\n".join(parts)


def repair_text(source_name: str, source_text: str, source_kind: str, draft: dict, problems: list[Issue]) -> str:
    lines = []
    for i in problems:
        where = f"[{i.step_id}] " if i.step_id else ""
        hint = f" Fix: {i.hint}." if i.hint else ""
        lines.append(f"- {i.code} {where}{i.message}.{hint}")
    return "\n\n".join([
        extract_text(source_name, source_text, source_kind).rsplit("\n\n", 1)[0],
        "This is your previous draft:",
        "<draft>", json.dumps(draft, indent=1, ensure_ascii=False), "</draft>",
        "The checker found these problems. Step ids in brackets are your keys with the chart prefix added.",
        "\n".join(lines),
        "Look at the source again and submit a corrected, complete flowchart with submit_flowchart. "
        "Change only what the problems require. If the source really does not support a fix (for "
        "example the chart itself has a box with no way out), keep the transcription faithful and "
        "explain it in that step's `question`.",
    ])
