"""Rebuild fixtures/demo from the reference sample chart.

02.json is the correct draft, derived from tests/data/sample-procedure.csv and
its verification sheet. 01.json is the same draft with five faults seeded, of
kinds found in real hand-made charts. They are scripted, not model output:
they exist to exercise the loop without a key.

    python tests/make_fixture.py
"""
import copy
import json
from pathlib import Path

from flowagent.evidence import CHART, load_evidence
from flowagent.schema import read_flowchart

ROOT = Path(__file__).parent
QUESTIONS = {"pretrial": "What is the pre-trial date?", "trial": "What is the trial date?",
             "set_down": "When was the action set down for trial?"}


def main() -> None:
    chart = read_flowchart(ROOT / "data" / "sample-procedure.csv")
    ev = load_evidence(ROOT / "data" / "sample-procedure.verify.md")
    key = lambda sid: sid.split("_", 1)[1] if sid != "END" else "END"
    steps = []
    for s in chart.steps:
        step = {"key": key(s.id), "step_name": s.get("step_name"), "step_type": s.type, "actor": s.get("actor"),
                "phase": s.get("phase"), "description": s.get("description"), "form_required": "",
                "rule_ref": s.get("rule_ref"), "quotes": ev.for_step(s.id), "optional": False,
                "next": [{"to": key(t), "condition": ""} for t in s.next], "confidence": "high", "question": ""}
        if s.rule:
            step["deadline"] = {"basis": s.rule.basis, "timeframe": s.get("timeframe"),
                                "question": s.get("deadline_question"),
                                "offsets": [{"sign": o.sign, "amount": o.amount, "unit": o.unit} for o in s.rule.offsets]}
        steps.append(step)
    good = {"title": "Expert Evidence (r. 12.04)", "chart_quotes": ev.quotes[CHART], "steps": steps}

    bad = copy.deepcopy(good)
    by = {s["key"]: s for s in bad["steps"]}
    by["AFFIDAVITS"]["rule_ref"] = "r. 12.04(2)"                 # wrong citation (chart prints 12.04(1))
    by["PRETRIAL"]["next"] = []                                   # dead end; cuts off the last two steps
    by["SUPP"]["deadline"]["offsets"][0]["sign"] = "+"            # counts forward from a trial date
    by["SCHEDULE"]["quotes"] = ["Expert schedule must be fixed by the case management judge"]  # not on the chart
    by["SCHEDULE"]["deadline"]["offsets"][0]["amount"] = 90       # chart says 60

    out = ROOT.parent / "fixtures" / "demo"
    out.mkdir(parents=True, exist_ok=True)
    (out / "01.json").write_text(json.dumps(bad, indent=1) + "\n", encoding="utf-8")
    (out / "02.json").write_text(json.dumps(good, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
