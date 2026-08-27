# Evidence — query counts on the recommended-mission lookup

## Question

`HomeService.legacyRecommendedMission` contains a repository call inside a
stream filter:

```java
.filter(mission -> missionAttemptRepository.findLatestCompletedAt(childId, mission.getId()).isPresent())
```

That is the shape of an N+1. This measures whether it is one in practice.

## Conditions

| | |
|---|---|
| Commit | `c57c3a3` |
| Test | `backend/src/test/java/.../MissionSetAvailabilityQueryCountTest.java` |
| Database | PostgreSQL 18.6, empty schema built by Flyway V1–V16 |
| Instrument | Hibernate `Statistics.getPrepareStatementCount()`, cleared before each measurement |
| Fixture | 16 missions × 6 sets = 96 mission sets, one child |

```bash
cd backend
TEST_DB_URL=jdbc:postgresql://localhost:5432/aimong_qc \
TEST_DB_USERNAME=postgres TEST_DB_PASSWORD=postgres \
JWT_SECRET=… ./gradlew test --tests '*MissionSetAvailabilityQueryCountTest'
```

## Result: not reproduced

```
[query-count] 96 sets, cold lookup: 2 statements
[query-count] 96 sets: 1 statements, 12 sets: 1 statements
[query-count] 0 progress rows: 1 statements, 96 progress rows: 1 statements
[query-count] control, one query per set over 96 sets: 96 statements

4 tests, 0 failures
```

| Scenario | Statements |
|---|---:|
| Cold lookup, 96 sets | 2 |
| Warm lookup, 96 sets | 1 |
| Warm lookup, 12 sets | 1 |
| Warm lookup, 96 progress rows | 1 |
| **Control: deliberate query per set** | **96** |

## Why it is not a problem

**The method is unreachable.** `legacyRecommendedMission` is `private`, and the
repository contains exactly one occurrence of the name — its own declaration:

```
$ grep -rn "legacyRecommendedMission" --include=*.java src/
src/main/java/com/aimong/backend/domain/home/service/HomeService.java:237:    private HomeResponse.RecommendedMissionResponse legacyRecommendedMission(…)
```

`HomeService` line 78 calls `recommendedMission(childId)`, not the legacy
variant. The N+1 cannot be triggered because the code never executes.

**The live path is already batched.** `recommendedMission` delegates to
`MissionService.missionSetAvailability`, which issues:

1. `findAllByActiveTrueOrderBy…` for the active sets, behind a 30-second cache;
2. `findAllByChildIdAndSetIdIn(childId, setIds)` — a single `IN` query for the
   child's progress.

Everything after that is in-memory grouping and filtering. Nothing in that path
queries per mission or per set, which the measurements confirm: the count does
not move when the number of sets goes from 96 to 12, nor when 96 progress rows
are added.

## Why the control test exists

A statement counter that cannot see an N+1 would make every number above
meaningless. The control issues one `findBySetIdAndActiveTrue` per set and
registers **96 statements**, so the instrument demonstrably detects the pattern
it is being used to rule out.

## No change made

The production code is unchanged. The finding was a false positive: real code
shape, unreachable location, and a live path that is already batched.

## Limitations

- `getPrepareStatementCount()` counts statement *preparations*. A repeated
  identical statement can be served from the driver's cache and not counted
  again, which is why the warm figure is 1 rather than 2. The absolute numbers
  are therefore lower bounds; the meaningful results are the control (96) and
  the invariance to set count.
- Measured on a single connection with no concurrent load.
- `legacyRecommendedMission` was left in place. Removing dead code is outside
  what this verification was asked to change.
