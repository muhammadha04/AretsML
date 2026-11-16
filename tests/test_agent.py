"""Run with:  python -m unittest discover -s tests -v   (no network, no key)"""
import json
import tempfile
import unittest
from pathlib import Path

from flowagent.agent import run_agent
from flowagent.checks import check_flowchart
from flowagent.draft import build, tool_schema
from flowagent.evaluate import diff_charts, evaluate
from flowagent.evidence import load_evidence
from flowagent.issues import errors
from flowagent.llm import ReplayProvider
from flowagent.schema import parse_deadline_rule, parse_flowchart, read_flowchart

ROOT = Path(__file__).parent
DATA = ROOT / "data"
GOLD = DATA / "sample-procedure.csv"


def gold_with(step_id: str, **changes):
    """The reference sample chart with one row altered."""
    chart = read_flowchart(GOLD)
    chart.by_id[step_id].row.update(changes)
    return parse_flowchart(chart.to_csv(), name="mutant")


def evidence():
    ev = load_evidence(DATA / "sample-procedure.verify.md")
    ev.source_text, ev.source_kind = (DATA / "sample-chart.txt").read_text(encoding="utf-8"), "text_layer"
    return ev


def codes(issues, severity="error"):
    return {i.code for i in issues if i.severity == severity}


class GoldChart(unittest.TestCase):
    def test_signed_off_chart_is_clean(self):
        issues = check_flowchart(read_flowchart(GOLD), evidence())
        self.assertEqual([i.line() for i in issues if i.severity != "info"], [])

    def test_deadline_rule_parsing(self):
        r = parse_deadline_rule("struck_off+2y-30d")
        self.assertEqual((r.basis, len(r.offsets), r.direction, str(r)), ("struck_off", 2, "+", "struck_off+2y-30d"))
        self.assertIsNone(parse_deadline_rule("60 days"))


class SeededFaults(unittest.TestCase):
    """Each fault is a kind found by hand in real hand-made charts."""

    def check(self, **kw):
        return check_flowchart(gold_with(**kw), evidence())

    def test_dead_end(self):
        self.assertIn("S07", codes(self.check(step_id="EXP_PRETRIAL", next_steps="")))

    def test_unreachable_steps(self):
        self.assertIn("S14", codes(self.check(step_id="EXP_SETDOWN", next_steps="EXP_AFFIDAVITS")))

    def test_loop_without_exit(self):
        self.assertIn("S15", codes(self.check(step_id="EXP_TRIAL", next_steps="EXP_PRETRIAL")))

    def test_unknown_target(self):
        self.assertIn("S09", codes(self.check(step_id="EXP_CLAIM", next_steps="EXP_NOPE")))

    def test_half_labelled_choice(self):
        issues = self.check(step_id="EXP_CLAIM", next_steps="EXP_DEFENCE;EXP_SETDOWN", next_step_conditions="Defended;")
        self.assertIn("S10", codes(issues))

    def test_wrong_citation(self):   # cites (2) where the chart prints (1)
        issues = self.check(step_id="EXP_AFFIDAVITS", rule_ref="r. 12.04(2)")
        self.assertIn("G03", codes(issues))
        self.assertIn("12.04(1)", next(i.message for i in issues if i.code == "G03"))

    def test_subrule_is_not_confused_with_longer_one(self):   # (2) is not printed where only (2.2) is
        self.assertIn("G03", codes(self.check(step_id="EXP_SCHEDULE", rule_ref="r. 12.04(2)")))

    def test_deadline_direction(self):
        self.assertIn("D02", codes(self.check(step_id="EXP_SUPP", deadline_rule="trial+30d")))

    def test_deadline_amount(self):
        got = codes(self.check(step_id="EXP_SCHEDULE", deadline_rule="set_down+90d"))
        self.assertTrue({"D03", "G05"} <= got)

    def test_deadline_counted_from_wrong_event(self):
        issues = self.check(step_id="EXP_SCHEDULE", deadline_rule="trial+60d")
        self.assertIn("D04", codes(issues, "warning"))

    def test_unknown_basis(self):
        self.assertIn("D01", codes(self.check(step_id="EXP_SUPP", deadline_rule="verdict-30d"), "warning"))

    def test_deadline_on_condition_step(self):
        self.assertIn("S12", codes(self.check(step_id="EXP_SUPP", step_type="CONDITION"), "warning"))

    def test_form_not_on_chart(self):
        self.assertIn("G04", codes(self.check(step_id="EXP_CLAIM", form_required="Form 14A"), "warning"))

    def test_invented_quote(self):
        ev = evidence()
        ev.quotes["EXP_TRIAL"] = ["Judgment is delivered within six months"]
        self.assertIn("G02", codes(check_flowchart(read_flowchart(GOLD), ev)))

    def test_missing_evidence_is_an_error_for_model_drafts(self):
        ev = evidence()
        del ev.quotes["EXP_TRIAL"]
        self.assertIn("G01", codes(check_flowchart(read_flowchart(GOLD), ev), "warning"))
        self.assertIn("G01", codes(check_flowchart(read_flowchart(GOLD), ev, require_evidence=True)))


class Draft(unittest.TestCase):
    def setUp(self):
        self.draft = json.loads((ROOT.parent / "fixtures" / "demo" / "02.json").read_text())

    def test_code_composes_ids_and_rules(self):
        chart, ev, problems, _ = build(self.draft, "x", "EXP", "EXPERT")
        self.assertEqual(problems, [])
        self.assertEqual(chart.to_csv(), read_flowchart(GOLD).to_csv())
        self.assertEqual(len(ev.for_step("EXP_SCHEDULE")), 2)

    def test_bad_target_key(self):
        self.draft["steps"][0]["next"] = [{"to": "NOWHERE"}]
        self.assertIn("X02", {p.code for p in build(self.draft, "x", "EXP")[2]})

    def test_tool_schema_is_valid_json(self):
        schema = tool_schema()
        self.assertEqual(schema["name"], "submit_flowchart")
        json.dumps(schema)


class Loop(unittest.TestCase):
    def run_fixture(self, rounds):
        tmp = tempfile.mkdtemp()
        provider = ReplayProvider(ROOT.parent / "fixtures" / "demo")
        return run_agent(DATA / "sample-chart.txt", provider, Path(tmp), prefix="EXP", name="sample-procedure",
                         max_rounds=rounds, branch="EXPERT")

    def test_repair_loop_fixes_seeded_faults(self):
        r = self.run_fixture(rounds=3)
        self.assertEqual((r.status, r.rounds), ("PASS", 1))
        self.assertGreater(r.history[0]["errors"], 0)
        self.assertEqual(r.history[1]["errors"], 0)
        self.assertEqual(evaluate(r.chart, read_flowchart(GOLD))["arrows"]["f1"], 1.0)
        for name in ("sample-procedure.csv", "sample-procedure.evidence.json", "sample-procedure.verify.md",
                     "OPEN-QUESTIONS.md", "run.json", "llm/01.json", "llm/02.json"):
            self.assertTrue((r.out_dir / name).exists(), name)

    def test_errors_left_over_fail_the_run(self):
        r = self.run_fixture(rounds=0)
        self.assertEqual(r.status, "FAILED")
        self.assertTrue(errors(r.issues))
        self.assertIn("UNRESOLVED ERROR", (r.out_dir / "OPEN-QUESTIONS.md").read_text())

    def test_quote_the_model_stands_by_goes_to_a_person(self):
        # Text extraction and OCR both miss light text on a dark box, so the search can be wrong.
        draft = json.loads((ROOT.parent / "fixtures" / "demo" / "02.json").read_text())
        draft["steps"][-1]["quotes"].append("Costs submissions follow within thirty days")
        tmp = Path(tempfile.mkdtemp())
        for n in ("01", "02"):
            (tmp / f"{n}.json").write_text(json.dumps(draft))
        r = run_agent(DATA / "sample-chart.txt", ReplayProvider(tmp), tmp / "out", prefix="EXP", name="x")
        self.assertEqual((r.status, r.rounds, r.history[0]["errors"]), ("NEEDS_REVIEW", 1, 1))
        self.assertIn("by eye", (r.out_dir / "OPEN-QUESTIONS.md").read_text())

    def test_agent_verify_sheet_can_be_checked_again(self):
        r = self.run_fixture(rounds=3)
        ev = load_evidence(r.out_dir / "sample-procedure.verify.md")
        self.assertTrue(ev.for_step("EXP_TRIAL"))
        self.assertEqual(errors(check_flowchart(r.chart, ev)), [])


class AnthropicRequest(unittest.TestCase):
    """The request is built and the reply parsed as the Messages API documents; no network."""

    def test_request_shape_and_tool_reply(self):
        import io
        from unittest import mock
        from flowagent.llm import AnthropicProvider
        sent = {}

        def fake_urlopen(req, timeout=0):
            sent["headers"] = {k.lower(): v for k, v in req.header_items()}
            sent["body"] = json.loads(req.data)
            reply = {"stop_reason": "tool_use", "usage": {"input_tokens": 1, "output_tokens": 1},
                     "content": [{"type": "tool_use", "name": "submit_flowchart", "input": {"title": "t"}}]}
            return io.BytesIO(json.dumps(reply).encode())

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            out = AnthropicProvider("some-model", api_key="k").call_tool("sys", "text", tool_schema(), pdf=b"%PDF-1.4")
        body = sent["body"]
        self.assertEqual(out, {"title": "t"})
        self.assertEqual(sent["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(body["tool_choice"], {"type": "tool", "name": "submit_flowchart"})
        doc, text = body["messages"][0]["content"]
        self.assertEqual((doc["type"], doc["source"]["media_type"], text["type"]), ("document", "application/pdf", "text"))


class Compare(unittest.TestCase):
    def test_diff_reports_the_change(self):
        lines = diff_charts(read_flowchart(GOLD), gold_with("EXP_AFFIDAVITS", rule_ref="r. 12.04(2)"))
        self.assertEqual(len(lines), 1)
        self.assertIn("EXP_AFFIDAVITS rule_ref", lines[0])

    def test_eval_counts_a_missing_arrow(self):
        sc = evaluate(gold_with("EXP_PRETRIAL", next_steps="END"), read_flowchart(GOLD))
        self.assertEqual((sc["steps"]["f1"], sc["arrows"]["hit"]), (1.0, 8))


if __name__ == "__main__":
    unittest.main()
