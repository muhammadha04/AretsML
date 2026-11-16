"""Graph and format checks: a chart that passes here is well-formed enough to import."""
from __future__ import annotations

from ..issues import ERROR, INFO, WARNING, Issue
from ..schema import (ACTORS, DEADLINE_RULE, END, HEADER, LAYOUT_COLUMNS, NO_DATES_TYPES,
                      OPTIONAL_COLUMNS, STEP_TYPES, Flowchart, split_list)


def check(chart: Flowchart) -> list[Issue]:
    out: list[Issue] = []

    def add(code, sev, msg, step="", hint=""):
        out.append(Issue(code, sev, msg, step, hint=hint))

    if not chart.steps:
        return [Issue("S01", ERROR, "File has no data rows")]

    # Header
    for h in HEADER:
        if h in chart.header:
            continue
        if h == "step_type" and "blob_type" in chart.header:
            add("S02", WARNING, 'Column "blob_type" should be named "step_type"')
        elif h in LAYOUT_COLUMNS:
            add("S02", WARNING, f'Missing optional layout column "{h}"')
        else:
            add("S02", ERROR, f'Missing column "{h}"')
    for h in chart.header:
        if h not in HEADER and h not in OPTIONAL_COLUMNS and h != "blob_type":
            add("S02", WARNING, f'Unknown column "{h}" (the app ignores it)')
    for line, first, n in chart.ragged_rows:
        add("S03", ERROR, f"Row {line} has {n} columns, expected {len(chart.header)}", first)

    # Ids
    ids: set[str] = set()
    for s in chart.steps:
        if not s.id:
            add("S04", ERROR, f"Row {s.line} has an empty step_id")
            continue
        if s.id == END:
            add("S04", ERROR, 'step_id "END" is reserved', s.id)
        if any(c in s.id for c in ";, \t"):
            add("S04", ERROR, "step_id must not contain spaces, commas or semicolons", s.id)
        if s.id in ids:
            add("S04", ERROR, "Duplicate step_id", s.id)
        ids.add(s.id)

    # Rows and edges
    incoming: dict[str, list[str]] = {}
    for s in chart.steps:
        if not s.id:
            continue
        nxt, real, conds = s.next, s.targets, s.conditions
        if s.type not in STEP_TYPES:
            add("S05", ERROR, f'Unknown step_type "{s.type}"', s.id, f"Use one of: {', '.join(STEP_TYPES)}")
        actor = s.get("actor")
        if actor and actor not in ACTORS:
            add("S06", WARNING, f'Actor "{actor}" is not in the app\'s actor list', s.id,
                f"Use one of: {', '.join(ACTORS)}")
        if not nxt:
            add("S07", ERROR, "Dead end: next_steps is empty", s.id,
                "Point it at the next step, or at END if the chart really stops here")
        if END in nxt and len(nxt) > 1:
            add("S08", ERROR, "END cannot be combined with other next_steps", s.id)
        for t in real:
            if t not in ids:
                add("S09", ERROR, f'next_steps points at unknown step_id "{t}"', s.id)
            if t == s.id:
                add("S09", ERROR, "next_steps points at itself", s.id)
            incoming.setdefault(t, []).append(s.id)
        if len(set(real)) != len(real):
            add("S09", ERROR, "next_steps lists the same target twice", s.id)
        for col in ("reverse_steps", "required_completed"):
            for t in filter(None, split_list(s.get(col))):
                if t not in ids:
                    add("S09", ERROR, f'{col} points at unknown step_id "{t}"', s.id)

        # Choice (every path labelled) or parallel (no labels)
        labelled = sum(1 for c in conds if c)
        if conds and len(conds) != len(nxt):
            add("S10", ERROR, f"{len(nxt)} next_steps but {len(conds)} next_step_conditions", s.id)
        if len(real) > 1:
            if 0 < labelled < len(real):
                add("S10", ERROR, "Some but not all outgoing paths are labelled", s.id,
                    "Label every option of a choice, or none if all paths proceed together")
            elif labelled == 0 and s.type == "DECISION":
                add("S10", WARNING, "DECISION with unlabelled options", s.id)
            elif labelled == 0:
                add("S10", INFO, f"{len(real)} unlabelled paths: treated as parallel (all proceed)", s.id)
        elif len(real) == 1 and labelled:
            add("S10", WARNING, "Single outgoing path has a condition label", s.id)

        # Deadline fields
        rule, question, timeframe = s.get("deadline_rule"), s.get("deadline_question"), s.get("timeframe")
        if rule:
            if not DEADLINE_RULE.match(rule):
                add("S11", ERROR, f'deadline_rule "{rule}" is not <basis><+|-><N><d|w|m|y>', s.id)
            if not question:
                add("S11", WARNING, "deadline_rule without a deadline_question", s.id)
            if not timeframe:
                add("S11", WARNING, "deadline_rule without a timeframe", s.id)
        elif question:
            add("S11", WARNING, "deadline_question without a deadline_rule", s.id)
        if s.type in NO_DATES_TYPES and (rule or timeframe or s.get("form_required")):
            add("S12", WARNING, f"{s.type} steps have no dates/upload tab, so form_required, "
                "timeframe and deadline_rule cannot be satisfied there", s.id,
                "Move the deadline or form to the ACTION step it governs")

    # One start, everything reachable from it
    edges = chart.out_edges()
    starts = [i for i in edges if i not in incoming]
    start_typed = [s.id for s in chart.steps if s.type == "START"]
    if len(starts) != 1:
        add("S13", ERROR, f"Expected exactly one entry step (no incoming path), found {len(starts)}: "
            f"{', '.join(starts) or 'none'}")
    if len(start_typed) != 1:
        add("S13", ERROR, f"Expected exactly one START-type step, found {len(start_typed)}")
    elif len(starts) == 1 and starts[0] != start_typed[0]:
        add("S13", ERROR, f"START step {start_typed[0]} is not the entry point ({starts[0]} has no incoming path)")
    root = starts[0] if starts else (start_typed[0] if start_typed else "")
    seen = reachable(edges, root) if root else set()
    for i in [i for i in edges if root and i not in seen]:
        add("S14", ERROR, f"Unreachable from {root}", i, "Add the missing arrow into this step")

    # Everything can reach END (this is also the 'every loop has an exit' check)
    ends = [s.id for s in chart.steps if END in s.next]
    if not ends:
        add("S15", ERROR, "No step ends the flowchart (no next_steps = END)")
    else:
        can_end = set(ends)
        changed = True
        while changed:
            changed = False
            for i, targets in edges.items():
                if i not in can_end and any(t in can_end for t in targets):
                    can_end.add(i)
                    changed = True
        trapped = [i for i in edges if i not in can_end]
        if trapped:
            add("S15", ERROR, "Cannot reach END (a dead end or a loop with no exit lies ahead) from: "
                + ", ".join(trapped))

    back = back_edges(edges, root)
    if back:
        add("S16", INFO, "Loops (a path returns to an earlier step; the app cannot re-enter a "
            "completed step): " + "; ".join(f"{a} -> {b}" for a, b in back))
    return out


def reachable(edges: dict[str, list[str]], root: str) -> set[str]:
    seen, stack = set(), [root]
    while stack:
        at = stack.pop()
        if at in seen:
            continue
        seen.add(at)
        stack.extend(edges.get(at, []))
    return seen


def back_edges(edges: dict[str, list[str]], root: str) -> list[tuple[str, str]]:
    found, state = [], {}
    stack = [(root, iter(edges.get(root, [])))] if root else []
    if root:
        state[root] = 1
    while stack:
        node, it = stack[-1]
        for t in it:
            if state.get(t) == 1:
                found.append((node, t))
            elif t not in state and t in edges:
                state[t] = 1
                stack.append((t, iter(edges[t])))
                break
        else:
            state[node] = 2
            stack.pop()
    return found
