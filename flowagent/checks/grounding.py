"""Grounding: nothing gets into a chart without printed words behind it.

Two layers. (1) Each quote must be found in the source document's text.
(2) Each rule, form and period on a step must be found in that step's quotes.
"""
from __future__ import annotations

import re

from ..evidence import Evidence
from ..issues import ERROR, WARNING, Issue
from ..schema import UNIT_WORDS, Flowchart

RULE_NUMBER = re.compile(r"\d+(?:\.\d+)*(?:\s*\(\s*\w+(?:\.\d+)?\s*\))*")
FORM = re.compile(r"\bForm\s+\d+(?:\.\d+)?[A-Z]?\b", re.I)


def squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower()) if len(t) >= 2]


def quote_support(quote: str, source: str) -> float:
    """1.0 when the quote is in the source ignoring spacing and punctuation;
    otherwise the share of its words that are (text layers of drawn charts come
    out in scrambled order, so word order is not required)."""
    if squash(quote) in squash(source):
        return 1.0
    words = tokens(quote)
    if not words:
        return 1.0
    have = set(tokens(source))
    return sum(1 for w in words if w in have) / len(words)


def compact(text: str) -> str:
    return re.sub(r"\s", "", text.lower())


def cites(num: str, printed: str) -> bool:
    """True when rule number `num` is printed in `printed` (already compacted).
    12.04 is printed where 12.04(1) is; 12.04(2) is not printed where only 12.04(2.2) is."""
    return re.search(rf"(?<!\d)(?<!\d\.){re.escape(num.lower())}(?!\d|\.\d)", printed) is not None


def rule_numbers(text: str) -> list[str]:
    return [re.sub(r"\s", "", m) for m in RULE_NUMBER.findall(text)]


def check(chart: Flowchart, ev: Evidence, require_evidence: bool = False) -> list[Issue]:
    out: list[Issue] = []
    chart_rules = compact(" ".join(ev.chart_level()))
    kind = ev.source_kind or "source"

    for q in ev.chart_level():
        _check_quote(out, q, ev, "", kind)

    for s in chart.steps:
        quotes = ev.for_step(s.id)
        if not quotes:
            out.append(Issue("G01", ERROR if require_evidence else WARNING,
                             "No source text recorded for this step", s.id,
                             hint="Quote the exact words printed in or beside the box"))
            continue
        for q in quotes:
            _check_quote(out, q, ev, s.id, kind)
        step_text = squash(" ".join(quotes))

        # G03 every rule number cited is printed for this step, or in the chart title
        printed_here = compact(" ".join(quotes))
        for num in rule_numbers(s.get("rule_ref")):
            if cites(num, printed_here) or cites(num, chart_rules):
                continue
            printed = [r for r in rule_numbers(" ".join(quotes)) if "." in r or "(" in r]
            saw = f"; the step's text prints {', '.join(printed)}" if printed else ""
            out.append(Issue("G03", ERROR, f"rule_ref cites {num}, which is not printed for this step "
                             f"or in the chart title{saw}", s.id,
                             hint="Cite the rule exactly as printed, or leave rule_ref empty"))

        # G04 forms
        for form in FORM.findall(s.get("form_required")):
            if squash(form) not in step_text:
                out.append(Issue("G04", WARNING, f"{form} is not printed on the chart for this step "
                                 "(added from practice?)", s.id))

        # G05 the period in the deadline rule is printed for this step
        rule = s.rule
        if rule:
            text = " ".join(quotes)
            for o in rule.offsets:
                if not re.search(rf"(?<!\d){o.amount}\s*-?\s*{UNIT_WORDS[o.unit]}s?\b", text, re.I):
                    out.append(Issue("G05", ERROR, f"Deadline {rule} uses {o.amount} {UNIT_WORDS[o.unit]}(s), "
                                     "which is not in this step's source text", s.id,
                                     hint="Take the period from the words on the chart"))
    return out


def _check_quote(out: list[Issue], quote: str, ev: Evidence, step_id: str, kind: str) -> None:
    if not ev.source_text:
        return
    support = quote_support(quote, ev.source_text)
    if support >= 0.8:
        return
    short = quote if len(quote) <= 90 else quote[:87] + "..."
    sev = WARNING if support >= 0.5 else ERROR
    out.append(Issue("G02", sev, f'Quote not found in the {kind} text ({support:.0%} of its words): "{short}"',
                     step_id, hint="Quote the chart word for word. If these exact words are printed on the page, keep the quote"))
