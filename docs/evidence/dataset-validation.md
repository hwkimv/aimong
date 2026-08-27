# Evidence — dataset validation

## Conditions

| | |
|---|---|
| Commit | `398b528` |
| Dataset | `pipeline/data/question-bank-1056.json` (1,489,429 bytes) |
| Contract | `pipeline/contracts/dataset-contract.json` v1.0 |
| Python | 3.13.9 |
| Platform | Linux 6.6.87.2-microsoft-standard-WSL2 |

## Command

```bash
make verify
```

## Result

```
==> contract is current
contract up to date: contracts/dataset-contract.json

==> hard contract + quality audit + export
PASS

Dataset
- Questions: 1,056
- Missions: 16
- Hard contract errors: 0
- Quality warnings: 95
    absoluteWording: 82
    answerLengthBias: 5
    contentTagCount: 8

Artifacts
- Backend JSON: pipeline/out/backend-compatible-question-bank.json
- Seed SQL: pipeline/out/question-bank-seed.sql
- question_bank rows: 1,056
- question_answer_keys rows: 1,056
- mission_sets rows: 96

==> tests
71 passed
```

## Before

Same dataset through the previous exporter,
`pipeline/scripts/export_question_bank.py`:

```bash
python3 scripts/export_question_bank.py \
  --input data/question-bank-1056.json \
  --config config/mission-config.json --out-dir out
```

```
verdict=FAIL
questionBankRows=1056
```

99 issues, in four groups:

| Count | Issue |
|---:|---|
| 95 | `unsupported contentTag` — config allowed 5 tags, the data uses 11 |
| 1 | `typeCounts` — 960-scale expectation vs 1,056-scale data |
| 1 | `difficultyCounts` — same cause |
| 1 | `packCounts: expected {'PP1': 160, …}, got {'P1': 160, …}` — double `P` prefix |
| 1 | `questionsPerMission: expected 60 each, got 66` |

Plus two checks that produced no issue because they never executed:
`questionCount` and `missionCount` read `globalPlan["totalQuestions"]` and
`globalPlan["missions"]` while the config keys are `totalQuestionCount` and
`totalMissionCount`.

## Observed dataset shape

Derived and cross-checked against the dataset's own declarations:

| Property | Value | Holds for |
|---|---|---|
| Questions | 1,056 | — |
| Missions | 16 | — |
| Per mission | 66 | all 16 |
| Pack sizes per mission | P1–P5 10, P6 16 | all 16 |
| Difficulty per mission | LOW 30, MEDIUM 20, HIGH 16 | all 16 |
| Global type counts | OX 207, MULTIPLE 332, FILL 186, SITUATION 331 | fingerprint only |
| Distinct content tags | 11 | — |
| `externalId` uniqueness | 1,056 / 1,056 | — |
| `externalId` format violations | 0 | — |

The dataset's declared `actualPackTypeDistribution` was checked cell by cell:
pack **totals** match for all six packs, but **17 of 24** type cells do not.
Per-pack type is therefore not enforced. See
[data-contract.md](../data-contract.md).

## Contract guard

Deleting one question and re-deriving:

```
contract derivation failed: totalQuestionCount: dataset declares 1056 but data contains 1055
```

## Test suite

| Run | Result |
|---|---|
| `make test` (no database) | 71 passed, 7 skipped |
| `make test` with `AIMONG_TEST_DB_URL` | 78 passed |
| Backend `./gradlew test` (no database) | 151 tests, 0 failures, 1 skipped |
| Backend `./gradlew test` with `TEST_DB_URL` | 151 tests, 0 failures, 0 skipped |

`OpenAiClientTimeoutTest` accounts for two of the 151; the single skip is
`BackendApplicationTests.contextLoads`, which needs a database.

## Regression check

Reverting the `set_id` fix in `adapter.py` and rerunning:

```
FAILED tests/test_export.py::test_every_question_is_bound_to_a_mission_set
FAILED tests/test_export.py::test_every_mission_set_has_enough_questions_to_serve
FAILED tests/test_export.py::test_sql_contains_no_null_set_id_for_questions
3 failed, 68 passed
```

Exactly the three tests that assert that behaviour, and no others.

## Limitations

- The 95 quality warnings are unreviewed. They are review candidates, not
  defects, and no human pass over them has happened.
- No semantic or factual check exists. Nothing here says an answer is correct.
- Similarity is lexical only; no embedding-based comparison is implemented.
