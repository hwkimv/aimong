# Data contract

The contract lives in [`pipeline/contracts/dataset-contract.json`](../pipeline/contracts/dataset-contract.json)
and is the single source of truth for what a valid question bank looks like.
Nothing else in the pipeline hard-codes a count, an enum or a quota.

## Why the contract is derived, and why that is safe

Writing a contract by hand next to a dataset invites the contract to drift.
Deriving it from the dataset invites the opposite failure: the contract becomes
a restatement of whatever the data happens to contain, and any corruption is
adopted as the new normal.

[`pipeline/tools/derive_contract.py`](../pipeline/tools/derive_contract.py) takes a
middle path. Every structural quota it writes must be **declared by the dataset
itself** and must **hold across the data**. If the two disagree, derivation
fails rather than recording the observed value:

```
$ python3 tools/derive_contract.py     # after deleting one question
contract derivation failed: totalQuestionCount: dataset declares 1056 but data contains 1055
```

That closes the obvious shortcut of deleting awkward rows until validation
passes. `make verify` runs `derive_contract.py --check`, so a contract edited by
hand to accommodate broken data is also caught.

## Canonical dataset: 1,056

The dataset carries its own history:

```json
"highExpansion": {
  "previousQuestionCount": 960,
  "addedHighQuestionCount": 96,
  "addedPerMission": 6,
  "externalIdRangePerMission": "P6-11..P6-16"
}
```

960 + 96 = 1,056. The expansion is recorded as deliberate — six HIGH questions
added to every mission at `P6-11..P6-16`. `config/mission-config.json` still
describes the earlier 960 plan; it is the stale artifact, not the data.

## Structural quotas

| Property | Value | Declared by the dataset as |
|---|---|---|
| Total questions | 1,056 | `totalQuestionCount` |
| Missions | 16 | `totalMissionCount` |
| Questions per mission | 66 | `questionsPerMission` |
| Packs per mission | 6 | `packsPerMission` |
| Pack sizes per mission | P1–P5: 10, P6: 16 | `actualPackTypeDistribution` totals |
| Difficulty per mission | LOW 30, MEDIUM 20, HIGH 16 | `difficultyQuotaPerMission` |

Every one of these holds for all 16 missions.

## Type counts are a fingerprint, not a quota

The dataset declares a per-pack type split in `actualPackTypeDistribution`.
**17 of its 24 cells do not match the data.** For example it claims pack 1 holds
no SITUATION questions and 2 FILL questions per mission, while the data holds 1
SITUATION and 30 FILL across the 16 missions.

Because that declaration is contradicted, per-pack type is deliberately **not**
enforced. What is recorded instead is the observed global total:

```json
"fingerprint": { "typeCounts": { "OX": 207, "MULTIPLE": 332, "FILL": 186, "SITUATION": 331 } }
```

This is a drift guard: it catches a question whose type is silently rewritten,
without pretending to be a design quota it is not. The distinction is kept
explicit in the contract file so a future reader does not mistake one for the
other.

## Per-question rules

| Rule | Detail |
|---|---|
| Required non-empty strings | `externalId`, `missionCode`, `type`, `difficulty`, `question`, `explanation`, `curriculumRef` |
| `externalId` | matches `^S\d{4}-P([1-6])-\d{2}$`, unique across the bank, and its pack segment must equal `packNo` |
| `missionCode` | one of the 16 known codes |
| Enums | `type`, `difficulty`, `sourceType`, `generationPhase` |
| `contentTags` | non-empty, drawn from the 11 tags in the contract |

## Type shapes

The options/answer shape decides whether an answer can be graded at all, so it
is part of the hard contract.

| Type | `options` | `answer` |
|---|---|---|
| `OX` | `null` | boolean |
| `MULTIPLE` | 4 non-empty strings | 0-based index in `0..3` |
| `SITUATION` | 4 non-empty strings | 0-based index in `0..3` |
| `FILL` | 4 non-empty strings | non-empty list of 0-based indexes |

## Backend mapping

| Dataset | Database |
|---|---|
| `externalId` | no column; `question_bank.id` = `UUID.nameUUIDFromBytes("question:" + externalId)` |
| `missionCode` | `missions.mission_code`; `missions.id` derived the same way from `"mission:" + code` |
| `packNo` | `question_bank.pack_no`, and `question_bank.set_id` = `{missionCode}-L{packNo}` |
| `answer` (0-based) | `question_answer_keys.answer_payload` (**1-based**) |
| `options`, `contentTags` | JSONB |

Two consequences worth stating plainly:

- Because ids are derived rather than stored, reseeding updates rows instead of
  duplicating them — but a hash collision would silently merge two questions
  into one row. The PostgreSQL check asserts 1,056 distinct ids after the load.
- The 0-based to 1-based answer shift happens exactly once, in
  `adapter.answer_payload`, and is asserted both in unit tests and against the
  loaded database.
