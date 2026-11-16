"""Deadline checks. The model never writes or computes a date: it fills
(basis, sign, amount, unit) and these checks test them against the chart's
own wording and shape."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from ..issues import ERROR, INFO, WARNING, Issue
from ..schema import UNIT_WORDS, Flowchart
from .structure import reachable

BACK_WORDS = re.compile(r"\b(before|prior to|in advance of)\b", re.I)
FORWARD_WORDS = re.compile(r"\b(within|after|from|following)\b", re.I)


@lru_cache
def bases() -> dict:
    data = json.loads((Path(__file__).parent.parent / "bases.json").read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def amount_in_text(amount: int, unit: str, text: str) -> bool:
    word = UNIT_WORDS[unit]
    return re.search(rf"(?<!\d){amount}\s*-?\s*{word}s?\b", text, re.I) is not None


def check(chart: Flowchart) -> list[Issue]:
    out: list[Issue] = []
    edges = chart.out_edges()
    known = bases()
    for s in chart.steps:
        rule = s.rule
        if rule is None:
            continue  # absent, or malformed (structure.S11 reports that)
        timeframe = s.get("timeframe")

        # D01 basis is a named date the app knows
        spec = known.get(rule.basis)
        if spec is None:
            out.append(Issue("D01", WARNING, f'Basis "{rule.basis}" is not in bases.json', s.id,
                             hint=f"Use one of: {', '.join(known)}; or add the new basis to bases.json"))

        # D02 direction agrees with the wording
        back, fwd = bool(BACK_WORDS.search(timeframe)), bool(FORWARD_WORDS.search(timeframe))
        if back and not fwd and rule.direction == "+":
            out.append(Issue("D02", ERROR, f'Timeframe says "{timeframe}" (counts back) but the rule '
                             f"{rule} counts forward", s.id, hint="Use a minus offset"))
        elif fwd and not back and rule.direction == "-":
            out.append(Issue("D02", ERROR, f'Timeframe says "{timeframe}" (counts forward) but the rule '
                             f"{rule} counts back", s.id, hint="Use a plus offset"))
        if spec and spec["kind"] == "past" and rule.direction == "-":
            out.append(Issue("D02", WARNING, f"Rule {rule} counts back from a past event "
                             f'("{spec["label"]}")', s.id))

        # D03 every amount in the rule is in the wording
        if timeframe:
            for o in rule.offsets:
                if not amount_in_text(o.amount, o.unit, timeframe):
                    out.append(Issue("D03", ERROR, f"Rule {rule} uses {o.amount} {UNIT_WORDS[o.unit]}(s) "
                                     f'but the timeframe reads "{timeframe}"', s.id,
                                     hint="Make the offsets match the printed period"))

        # D04 the event counted from sits on the right side of this step
        if spec:
            anchors = [a.id for a in chart.steps if re.search(spec["anchor"], a.get("step_name").lower())]
            if anchors and s.id not in anchors:
                if rule.direction == "+":
                    ok = any(s.id in reachable(edges, a) for a in anchors)
                    side = "before"
                else:
                    down = reachable(edges, s.id)
                    ok = any(a in down for a in anchors)
                    side = "after"
                if not ok:
                    out.append(Issue("D04", WARNING, f'Rule {rule} counts from "{spec["label"]}", but no '
                                     f"such step ({', '.join(anchors)}) comes {side} this step on the chart",
                                     s.id, hint="Check which event the period is measured from"))
            elif not anchors:
                out.append(Issue("D04", INFO, f'"{spec["label"]}" is not a step on this chart; '
                                 "the app has to ask for that date", s.id))
    return out
