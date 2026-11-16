# Checks

Every finding has a code. **Errors** block a chart and are sent back to the model.
**Warnings** go to the lawyers as open questions. **Info** is context (`--info` shows it).

## Structure (`checks/structure.py`)

| Code | Severity | Finds |
|---|---|---|
| S01 | error | File has no rows |
| S02 | error / warning | Missing column; unknown or legacy column |
| S03 | error | Row has the wrong number of columns |
| S04 | error | Empty, duplicate, reserved or malformed `step_id` |
| S05 | error | Unknown `step_type` |
| S06 | warning | Actor not in the app's list |
| S07 | error | Dead end: `next_steps` empty |
| S08 | error | `END` mixed with other targets |
| S09 | error | Arrow to an unknown step, to itself, or listed twice |
| S10 | error / warning / info | Condition count differs from path count; half-labelled choice; unlabelled DECISION; parallel paths |
| S11 | error / warning | Malformed `deadline_rule`; rule without question or timeframe |
| S12 | warning | Deadline or form on a DECISION or CONDITION step (no dates tab) |
| S13 | error | Not exactly one start |
| S14 | error | Step unreachable from the start |
| S15 | error | Steps that cannot reach END (dead end ahead, or a loop with no exit) |
| S16 | info | Loops |

## Deadlines (`checks/deadlines.py`)

| Code | Severity | Finds |
|---|---|---|
| D01 | warning | Basis not in `bases.json` |
| D02 | error / warning | Wording counts back ("before") but the rule counts forward, or the reverse; counting back from a past event |
| D03 | error | An amount in the rule is not in the timeframe wording (rule 90 days, chart 60 days) |
| D04 | warning / info | The event counted from is on the chart but does not come before this step (or after it, for a rule that counts back); or is not on the chart at all |

## Grounding (`checks/grounding.py`)

Needs evidence: `<chart>.evidence.json` (written by the agent) or `<chart>.verify.md`
(a hand-made sheet with an "exact source text" column).

| Code | Severity | Finds |
|---|---|---|
| G01 | error for model drafts, warning otherwise | Step has no source text |
| G02 | error under 50% of words found, warning under 80% | Quote not found in the source document's text |
| G03 | error | `rule_ref` cites a rule that is not printed for the step or in the chart title |
| G04 | warning | Form not printed for the step |
| G05 | error | A period in `deadline_rule` is not in the step's source text |

G02 depends on text extraction. It misses light text on a dark box and OCR misreads
words, so a G02 on a hand-checked chart means "look at the page", not "the chart is
wrong". In a run, a G02 error is sent back once; if the model keeps the quote it
becomes a warning for a person.

G03 matches whole rule numbers: `12.04` counts as printed where `12.04(1)` is, but
`12.04(2)` does not where only `12.04(2.2)` is.

## Draft shape (`draft.py`)

| Code | Severity | Finds |
|---|---|---|
| X01 | error | Draft has no steps, or a step has no key |
| X02 | error | Arrow to a key that no step has |
| X03 | error | Deadline without basis or offsets |
