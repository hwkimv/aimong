# Question set binding

## Context

The backend serves a fixed set of 10 questions per mission attempt. Each mission
has 6 sets (`S0101-L1` … `S0101-L6`) held in `public.mission_sets`, and questions
are attached to a set through `question_bank.set_id`.

The question bank is generated offline and loaded with a seed SQL file produced
by the pipeline.

## Problem

The exporter wrote `set_id` as a literal `NULL` for every question row, while
still creating all 96 `mission_sets` rows. The generated SQL applied cleanly and
the row counts were right, so nothing about the export looked wrong.

`QuestionBankRepository.findAllFromSafeViewBySetIdAndMissionId` selects
`WHERE set_id = :setId AND mission_id = :missionId`. With every `set_id` null,
that query returns nothing for all 96 sets.

## Reproduction

Loaded the seed into PostgreSQL 18.6 with the backend's own migrations applied,
then reproduced the old state in place:

```sql
BEGIN;
UPDATE public.question_bank SET set_id = NULL;
SELECT count(*) FROM public.mission_sets s
WHERE (SELECT count(*) FROM public.question_bank q
       WHERE q.set_id = s.set_id AND q.is_active) = 0;
ROLLBACK;
```

```
sets returning 0 questions: 96
```

96 of 96.

## Root cause

`MissionQuestionSetFactory.create` has a three-step fallback:

```java
List<QuestionBank> setPool = findActiveQuestionsBySetIdAndMissionId(setId, missionId);
if (!setPool.isEmpty()) return selectFixedQuestionSet(setPool);

Short packNo = packNoFromSetId(setId);
if (packNo != null && packNo == starLevel) { … }        // pack fallback

return create(missionId, childId, starLevel, isReview);  // difficulty fallback
```

Set ids encode the pack (`-L1` … `-L6`), but star level runs 1–3. The pack
fallback only fires when `packNo == starLevel`, so it is reachable for `L1`
alone. Sets `L2`–`L6` fall through to difficulty-based selection:

| Set | star | pack | reached by |
|---|---|---|---|
| `S0101-L1` | 1 | 1 | pack fallback |
| `S0101-L2` | 1 | 2 | difficulty pool |
| `S0101-L3` | 2 | 3 | difficulty pool |
| `S0101-L4` | 2 | 4 | difficulty pool |
| `S0101-L5` | 3 | 5 | difficulty pool |
| `S0101-L6` | 3 | 6 | difficulty pool |

The difficulty pool query is deterministic (`ORDER BY pack_no, created_at, id`)
and `selectFixedQuestionSet` takes the first 10. Two sets at the same star level
therefore resolve to the **same ten questions**: `L3` and `L4` both draw the
star-2 MEDIUM pool, `L5` and `L6` both draw the star-3 HIGH pool.

So the visible symptom is not an error. It is a child replaying identical
questions across sets that are supposed to be different, with 640 of the 1,056
questions unreachable.

## Alternatives considered

| Option | Assessment |
|---|---|
| Populate `set_id` in the export | Matches the schema's intent, fixes all 96 sets, no backend change. **Chosen.** |
| Change the pack fallback to compare pack instead of star | Leaves `set_id` null and keeps the real binding unused; papers over the data defect in serving code. |
| Drop `mission_sets` and serve purely by difficulty | Discards the fixed-set design the team had just moved to. |

## Decision

Populate `set_id` during export as `{missionCode}-L{packNo}`, the same key the
exporter already used when generating `mission_sets` rows. The mapping already
existed on one side of the relationship and simply was not written to the other.

`mission_sets.question_count` stays at 10 because the schema pins it
(`CHECK (question_count = 10)`) and 10 is the number served per attempt. Pack 6
holds 16 candidates and the backend selects 10 of them — pool size and served
size are intentionally different.

## Implementation

`pipeline/src/aimong_qbank/adapter.py`:

```python
def set_id(mission_code: str, pack_no: int) -> str:
    """mission_sets.set_id for a pack, e.g. S0101 pack 3 -> 'S0101-L3'."""
    return f"{mission_code}-L{pack_no}"
```

## Verification

Unit tests in `pipeline/tests/test_export.py`:

- every question carries a `setId` that exists in `missionSets`
- every set has at least `questionCount` candidates
- no `(missionCode, starLevel, variantNo)` collision, which `uq_mission_sets_mission_star_variant` would reject
- the rendered SQL contains no null `set_id` in the question block

Removing the fix fails exactly these three tests and no others.

Against PostgreSQL (`pipeline/tests/test_postgres_integration.py` and
`tools/verify_postgres.py`):

```
OK  questions with NULL set_id: 0
OK  orphan set_id references: 0
OK  sets with fewer active questions than question_count: 0
```

## Results

| | Sets serving from their own pool | Questions reachable by set |
|---|---|---|
| Before | 0 of 96 | 0 of 1,056 |
| After | 96 of 96 | 1,056 of 1,056 |

Overlap between `S0101-L3` and `S0101-L4` after the fix: 0 shared questions
(previously the same 10).

## Trade-offs

- `mission_sets.question_count` now under-reports pack 6's pool (10 declared, 16
  held). The schema's `CHECK` constraint does not allow recording 16, and the
  column means "served per attempt", so this is accepted and documented rather
  than worked around.
- The pack fallback in `MissionQuestionSetFactory` is left untouched. It is now
  unreachable in normal operation, but it is harmless and removing it is a
  backend change this data fix does not require.

## Limitations

- Verified at the data layer. No test drives an actual mission attempt through
  the HTTP API end to end, so this shows the correct rows are reachable rather
  than that a child sees the right quiz.
- The duplicate-serving consequence is derived from reading
  `MissionQuestionSetFactory` and confirming the query ordering in SQL, not from
  observing two attempts in a running application.
