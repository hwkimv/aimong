# A contract check that never ran

## Context

The exporter validated the question bank against `config/mission-config.json`
before producing backend artifacts. Its report ended in a `verdict` of `PASS` or
`FAIL`, and the total question count was one of the things it claimed to check.

## Problem

Running the exporter on the current data produced `verdict=FAIL` with 99 issues.
Four distinct defects were behind them, but the interesting one is the defect
that produced **no** issue.

The config described 960 questions. The data held 1,056. The count check never
fired.

## Reproduction

```bash
python3 scripts/export_question_bank.py \
  --input data/question-bank-1056.json \
  --config config/mission-config.json --out-dir out
```

```
verdict=FAIL
questionBankRows=1056
issues:
- S0101-P2-06: unsupported contentTag AUTOMATION
- ... 94 more tag issues
- typeCounts: expected {'OX': 208, ...}, got {'FILL': 186, ...}
- difficultyCounts: expected {'LOW': 432, ...}, got {'HIGH': 256, ...}
- packCounts: expected {'PP1': 160, ...}, got {'P1': 160, ...}
- questionsPerMission: expected 60 each, got {'S0101': 66, ...}
```

99 issues, and not one of them is `questionCount: expected 960, got 1056`.

## Root cause

```python
expected = {
    "questionCount": global_plan.get("totalQuestions"),   # config key: totalQuestionCount
    "missionCount":  global_plan.get("missions"),         # config key: totalMissionCount
    ...
}
```

Both lookups miss. Both return `None`. And the comparison helper treats absence
as "nothing to check":

```python
def compare_count(label, actual, expected, ...):
    if expected in (None, {}, []):
        return
```

So a typo in a key name silently disabled two whole-dataset checks. The
per-mission check still fired — which is why the mismatch was visible at all,
as `questionsPerMission` rather than as a total.

The same run also showed a second defect of the same shape:

```python
pack_counts.update({f"P{k}": v for k, v in mission.get("packPlan", {}).items()})
```

The config's `packPlan` keys are already `"P1"`…`"P6"`, so this produced
`PP1`…`PP6` and compared them against `P1`…`P6`. Every pack always mismatched,
which made the pack check permanently noisy and therefore easy to ignore.

## Alternatives considered

| Option | Assessment |
|---|---|
| Fix the two key names | Fixes today's bug, leaves the pattern that produced it. |
| Fail when an expected value is missing | Turns a silent skip into a loud error. **Chosen**, together with the below. |
| Derive the contract from the dataset, cross-checked against its declarations | Removes the duplicated numbers that drifted in the first place. **Chosen.** |
| Keep `--allow-sample` to downgrade issues to warnings | Removed. A flag that turns contract failures into warnings is the mechanism this case study is about. |

## Decision

Two changes, addressing the bug and the shape of it.

The contract moved out of the generation config into
`contracts/dataset-contract.json`, derived by `tools/derive_contract.py`. Nothing
else holds a count or a quota, so there is no second copy to drift.

Derivation refuses to invent a contract. Each quota must be declared by the
dataset *and* hold across the data; disagreement fails:

```
contract derivation failed: totalQuestionCount: dataset declares 1056 but data contains 1055
```

That guard is what makes "derive the contract from the data" safe rather than
circular — it blocks the shortcut of deleting rows until validation passes.

`make verify` runs `derive_contract.py --check`, so a hand-edited contract is
caught too.

## Why 1,056 and not 960

The dataset records the expansion:

```json
"highExpansion": {
  "previousQuestionCount": 960,
  "addedHighQuestionCount": 96,
  "addedPerMission": 6,
  "externalIdRangePerMission": "P6-11..P6-16"
}
```

960 + 96 = 1,056, six HIGH questions added per mission at known ids. The config
is the stale side. Reducing the data to 960 would have destroyed 96 questions to
satisfy an outdated plan.

## Implementation

- `pipeline/contracts/dataset-contract.json` — the contract
- `pipeline/tools/derive_contract.py` — derivation with the agreement guard
- `pipeline/src/aimong_qbank/contract.py` — hard rules, no skip-on-missing
- `pipeline/src/aimong_qbank/quality.py` — advisory checks, separated out
- `config/mission-config.json` left untouched as the historical generation plan
- `scripts/export_question_bank.py` retained and annotated as superseded

## Verification

```
$ make verify
PASS

Dataset
- Questions: 1,056
- Hard contract errors: 0
- Quality warnings: 95
```

23 failure-case tests assert that each rule rejects what it claims to reject —
duplicate ids, out-of-range answers, unknown enums, quota violations, type drift.
A validator with no failing tests is indistinguishable from no validator.

## Results

| | Before | After |
|---|---|---|
| Export verdict | FAIL | PASS |
| Hard contract errors | 99 | 0 |
| Checks silently skipped | 2 (`questionCount`, `missionCount`) | 0 |
| Quality findings blocking the export | yes | no, 95 recorded as review candidates |
| Places holding the expected counts | config + script constants | one contract file |

## Trade-offs

- The contract is generated, so it must be regenerated when the dataset legitimately
  changes. `--check` in `make verify` makes forgetting a build failure rather
  than silent drift.
- The type fingerprint is strict: any deliberate change to the type mix requires
  regenerating the contract. That is the intent — it should be a visible edit.

## Limitations

- The agreement guard only covers quotas the dataset declares. A field the
  dataset does not declare at all cannot be cross-checked this way, and the type
  counts are recorded as an observed fingerprint for exactly that reason.
- Nothing here validates that a question is factually correct. See
  [validation-strategy.md](../validation-strategy.md).
