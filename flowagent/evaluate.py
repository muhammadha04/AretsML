"""Score a draft against a signed-off chart, and diff two versions of a chart.

Steps are matched by name, not id, so a draft is not punished for choosing
different ids from the lawyers' version.
"""
from __future__ import annotations

import re

from .schema import Flowchart


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def match_steps(draft: Flowchart, gold: Flowchart) -> dict[str, str]:
    """gold step_id -> draft step_id, by normalised step name (first unused match)."""
    pool: dict[str, list[str]] = {}
    for s in draft.steps:
        pool.setdefault(_norm(s.get("step_name")), []).append(s.id)
    return {g.id: pool[_norm(g.get("step_name"))].pop(0) for g in gold.steps
            if pool.get(_norm(g.get("step_name")))}


def _prf(hit: int, n_draft: int, n_gold: int) -> dict:
    p = hit / n_draft if n_draft else 0.0
    r = hit / n_gold if n_gold else 0.0
    return {"precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0, "hit": hit,
            "draft": n_draft, "gold": n_gold}


def evaluate(draft: Flowchart, gold: Flowchart) -> dict:
    m = match_steps(draft, gold)
    back = {v: k for k, v in m.items()}
    gold_edges = {(s.id, t) for s in gold.steps for t in s.next}
    draft_edges = {(back.get(s.id, f"?{s.id}"), t if t == "END" else back.get(t, f"?{t}"))
                   for s in draft.steps for t in s.next}

    def field_accuracy(col: str, only_filled: bool) -> dict:
        rows = [g for g in gold.steps if (g.get(col) or not only_filled)]
        ok = sum(1 for g in rows if g.id in m and draft.by_id[m[g.id]].get(col).replace(" ", "") == g.get(col).replace(" ", ""))
        return {"correct": ok, "of": len(rows), "accuracy": ok / len(rows) if rows else 1.0}

    return {
        "steps": _prf(len(m), len(draft.steps), len(gold.steps)),
        "arrows": _prf(len(gold_edges & draft_edges), len(draft_edges), len(gold_edges)),
        "deadline_rule": field_accuracy("deadline_rule", only_filled=True),
        "rule_ref": field_accuracy("rule_ref", only_filled=True),
        "extra_deadlines": sum(1 for s in draft.steps if s.get("deadline_rule") and
                               not (s.id in back and gold.by_id[back[s.id]].get("deadline_rule"))),
        "missing_steps": [g.id for g in gold.steps if g.id not in m],
        "extra_steps": [s.id for s in draft.steps if s.id not in back],
    }


def format_scores(sc: dict) -> str:
    def prf(k):
        v = sc[k]
        return f"{k:14} P={v['precision']:.2f} R={v['recall']:.2f} F1={v['f1']:.2f}  ({v['hit']} matched; draft {v['draft']}, gold {v['gold']})"

    def acc(k):
        v = sc[k]
        return f"{k:14} {v['correct']}/{v['of']} correct ({v['accuracy']:.0%})"

    lines = [prf("steps"), prf("arrows"), acc("deadline_rule"), acc("rule_ref"),
             f"{'extra_deadlines':14} {sc['extra_deadlines']} (deadlines the gold chart does not have)"]
    if sc["missing_steps"]:
        lines.append("missing steps:  " + ", ".join(sc["missing_steps"]))
    if sc["extra_steps"]:
        lines.append("extra steps:    " + ", ".join(sc["extra_steps"]))
    return "\n".join(lines)


DIFF_COLUMNS = ["step_name", "step_type", "actor", "form_required", "rule_ref", "timeframe",
                "deadline_rule", "next_steps", "next_step_conditions"]


def diff_charts(old: Flowchart, new: Flowchart) -> list[str]:
    """Changes between two versions that share step ids: what a lawyer approves."""
    lines = []
    for sid in [s.id for s in old.steps if s.id not in new.by_id]:
        lines.append(f"- REMOVED {sid} {old.by_id[sid].get('step_name')}")
    for s in new.steps:
        if s.id not in old.by_id:
            lines.append(f"- ADDED   {s.id} {s.get('step_name')}")
            continue
        o = old.by_id[s.id]
        for col in DIFF_COLUMNS:
            if o.get(col) != s.get(col):
                lines.append(f"- CHANGED {s.id} {col}: \"{o.get(col)}\" -> \"{s.get(col)}\"")
    return lines or ["No differences in " + ", ".join(DIFF_COLUMNS)]
