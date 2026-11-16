# Verification sheet: Sample chart - Expert Evidence (r. 12.04)

- Source: `sample-chart.txt`, 1 page. Synthetic sample: the rule numbers are invented.
- CSV: `sample-procedure.csv` - 9 steps, 4 computed deadlines.
- Chart caption: "Figure 1: This flowchart shows the procedure, timelines and responsibilities when calling expert evidence at trial pursuant to Rule 12.04 of the Sample Rules of Civil Procedure."

Check each row against the PDF. "Exact source text" is what is printed in or beside the box; text after `|` is a label printed on an arrow, line or bracket. Anything in the CSV that is not printed on the chart is listed under "Added by us".

## Steps

| step_id | step name | PDF page | exact source text | rule_ref | deadline_rule | confidence | question for the lawyer |
|---|---|---|---|---|---|---|---|
| EXP_CLAIM | Claim | 1 | Claim | r. 12.04 |  | high |  |
| EXP_DEFENCE | Defence | 1 | Defence | r. 12.04 |  | high |  |
| EXP_SETDOWN | Set Down for Trial | 1 | Set Down for Trial (file trial record) | r. 12.04 |  | high |  |
| EXP_SCHEDULE | Schedule for service of expert reports | 1 | Schedule for service of expert reports (parties to agree upon) / arrow from Set Down for Trial: within 60 days (r. 12.04(2.2)) | r. 12.04(2.2) | set_down+60d | high |  |
| EXP_AFFIDAVITS | Expert affidavits | 1 | Expert affidavits (served no later than 90 days before pre-trial r. 12.04(1)) | r. 12.04(1) | pretrial-90d | high | Chart says "affidavits" here and "reports" elsewhere; keep as printed? |
| EXP_RESPONDING | Responding expert reports | 1 | Responding expert reports (served no later than 60 days before pre-trial (r. 12.04(2)) | r. 12.04(2) | pretrial-60d | high |  |
| EXP_PRETRIAL | Pre-Trial | 1 | Pre-Trial (provide Court with copy of expert affidavits if used at trial and may be of assistance in achieving purposes of pretrial) | r. 12.04 |  | high |  |
| EXP_SUPP | Supplementary expert reports | 1 | Supplementary expert reports (served no later than 30 days before trial (r. 12.04(3) (b)) | r. 12.04(3)(b) | trial-30d | high |  |
| EXP_TRIAL | Trial | 1 | Trial (Expert Testifies) | r. 12.04 |  | high |  |

## Arrows

| from | to | label in the CSV | how the app treats it |
|---|---|---|---|
| EXP_CLAIM Claim | EXP_DEFENCE Defence |  | single path |
| EXP_DEFENCE Defence | EXP_SETDOWN Set Down for Trial |  | single path |
| EXP_SETDOWN Set Down for Trial | EXP_SCHEDULE Schedule for service of expert reports |  | single path |
| EXP_SCHEDULE Schedule for service of expert reports | EXP_AFFIDAVITS Expert affidavits |  | single path |
| EXP_AFFIDAVITS Expert affidavits | EXP_RESPONDING Responding expert reports |  | single path |
| EXP_RESPONDING Responding expert reports | EXP_PRETRIAL Pre-Trial |  | single path |
| EXP_PRETRIAL Pre-Trial | EXP_SUPP Supplementary expert reports |  | single path |
| EXP_SUPP Supplementary expert reports | EXP_TRIAL Trial |  | single path |
| EXP_TRIAL Trial | END |  | chart ends |

## Deadlines

| step_id | question the app asks | text shown | rule computed |
|---|---|---|---|
| EXP_SCHEDULE | When was the action set down for trial? | within 60 days | set_down+60d |
| EXP_AFFIDAVITS | What is the pre-trial date? | served no later than 90 days before pre-trial | pretrial-90d |
| EXP_RESPONDING | What is the pre-trial date? | served no later than 60 days before pre-trial | pretrial-60d |
| EXP_SUPP | What is the trial date? | served no later than 30 days before trial | trial-30d |

## Added by us (not printed on the chart)

- `actor` on every row: the chart names no actors. Values are inferred from ordinary practice.
- `step_type` and `phase` on every row: our classification.
- `deadline_question` on every row that has one: our wording.
- `rule_ref`: where a box prints no rule, the chart-level citation from the title (`r. 12.04`) is repeated.

## Flagged items (1)

1. **EXP_AFFIDAVITS Expert affidavits** (high confidence). Chart says "affidavits" here and "reports" elsewhere; keep as printed?

## Sign-off

- [ ] Every box on the PDF has a row, and every row is a box on the PDF
- [ ] Every arrow matches
- [ ] Rule references and forms match
- [ ] Deadlines match

Reviewed by: ____________________  Date: ____________
