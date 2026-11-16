"""Command line: python -m flowagent <command>. See README.md."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .checks import check_flowchart
from .evidence import find_evidence_file, load_evidence
from .ingest import read_source
from .issues import ERROR, INFO, WARNING, Issue, errors
from .schema import read_flowchart


def _print(issues: list[Issue], quiet: bool, show_info: bool) -> None:
    for i in issues:
        if quiet or (i.severity == INFO and not show_info):
            continue
        print("  " + i.line())


def cmd_check(a) -> int:
    failed = 0
    report = []
    for f in a.csv:
        path = Path(f)
        chart = read_flowchart(path)
        ev_path = Path(a.evidence) if a.evidence else find_evidence_file(path)
        ev = load_evidence(ev_path) if ev_path and not a.no_evidence else None
        if ev is not None and not any(k for k in ev.quotes if k != "_chart"):
            ev = None  # e.g. the combined chart's sheet, which has no source-text column
        if ev is not None and a.source:
            src = read_source(a.source)
            ev.source_text, ev.source_kind = src.text, src.kind
        issues = check_flowchart(chart, ev)
        n = {s: sum(1 for i in issues if i.severity == s) for s in (ERROR, WARNING, INFO)}
        failed += bool(n[ERROR])
        grounded = "no evidence file" if ev is None else (
            f"evidence={ev_path.name}" + (f" source={ev.source_kind or 'unreadable'}" if a.source else ""))
        print(f"{'FAIL' if n[ERROR] else 'PASS'}  {path.name}  steps={len(chart.steps)} "
              f"errors={n[ERROR]} warnings={n[WARNING]} info={n[INFO]}  ({grounded})")
        _print(issues, a.quiet, a.info)
        report.append({"chart": chart.name, "issues": [i.to_dict() for i in issues]})
    if len(a.csv) > 1:
        print(f"\n{len(a.csv) - failed}/{len(a.csv)} charts pass")
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 1 if failed else 0


def cmd_extract(a) -> int:
    from .agent import run_agent
    from .llm import make_provider
    provider = make_provider(a.provider, model=a.model, replay=a.replay)
    result = run_agent(Path(a.pdf), provider, out_root=Path(a.out), prefix=a.prefix,
                       name=a.name, max_rounds=a.rounds, branch=a.branch)
    print(f"{result.status}  {result.out_dir}")
    print(f"  rounds={result.rounds} steps={len(result.chart.steps)} errors={len(errors(result.issues))} "
          f"open_questions={result.question_count}")
    _print(result.issues, a.quiet, a.info)
    return 0 if result.status != "FAILED" else 1


def cmd_eval(a) -> int:
    from .evaluate import evaluate, format_scores
    print(format_scores(evaluate(read_flowchart(a.draft), read_flowchart(a.gold))))
    return 0


def cmd_diff(a) -> int:
    from .evaluate import diff_charts
    for line in diff_charts(read_flowchart(a.old), read_flowchart(a.new)):
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="flowagent", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--quiet", action="store_true", help="one summary line per file")
        sp.add_argument("--info", action="store_true", help="also print info-level notes")

    c = sub.add_parser("check", help="run the deterministic checks on flowchart CSVs (no model)")
    c.add_argument("csv", nargs="+")
    c.add_argument("--evidence", help="evidence file (.evidence.json or .verify.md); default: next to the CSV")
    c.add_argument("--no-evidence", action="store_true", help="structure and deadline checks only")
    c.add_argument("--source", help="source PDF, to check quotes against its text (one CSV only)")
    c.add_argument("--json", help="write all issues to this JSON file")
    common(c); c.set_defaults(fn=cmd_check)

    e = sub.add_parser("extract", help="draft a flowchart from a source PDF, check it, repair it")
    e.add_argument("pdf")
    e.add_argument("--prefix", required=True, help="step_id prefix, e.g. EXP")
    e.add_argument("--name", help="chart name (default: PDF file name)")
    e.add_argument("--branch", default="", help="value for the branch column")
    e.add_argument("--out", default="runs", help="output root (default: runs/)")
    e.add_argument("--rounds", type=int, default=3, help="maximum repair rounds (default 3)")
    e.add_argument("--provider", default=os.environ.get("FLOWAGENT_PROVIDER", "anthropic"),
                   choices=["anthropic", "replay"])
    e.add_argument("--model", default=os.environ.get("FLOWAGENT_MODEL", "claude-sonnet-5-5"))
    e.add_argument("--replay", help="folder of recorded responses (with --provider replay)")
    common(e); e.set_defaults(fn=cmd_extract)

    v = sub.add_parser("eval", help="score a draft CSV against a signed-off CSV")
    v.add_argument("draft"); v.add_argument("gold"); v.set_defaults(fn=cmd_eval)

    d = sub.add_parser("diff", help="list what changed between two versions of a chart")
    d.add_argument("old"); d.add_argument("new"); d.set_defaults(fn=cmd_diff)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
