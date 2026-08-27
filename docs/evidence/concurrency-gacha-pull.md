# Evidence — concurrent gacha pulls

## Why this flow

A gacha pull is where a duplicate reward would be most visible. It spends a
ticket, increments a per-child pull counter, and grants a pet or fragments — all
in one transaction, in the shape that races:

```
find an unused ticket  ─▶  check it exists  ─▶  mark it used + grant reward
```

Two concurrent pulls that both read the same unused ticket would both grant a
reward from one ticket.

## Conditions

| | |
|---|---|
| Commit | `c57c3a3` |
| Test | `backend/src/test/java/.../GachaPullConcurrencyTest.java` |
| Database | PostgreSQL 18.6, schema built by Flyway V1–V16 |
| Under test | `GachaPullService.pull`, unmodified |
| Concurrency | fixed thread pool, all threads released by one latch |

```bash
cd backend
TEST_DB_URL=jdbc:postgresql://localhost:5432/aimong_cc \
TEST_DB_USERNAME=postgres TEST_DB_PASSWORD=postgres \
JWT_SECRET=… ./gradlew test --tests '*GachaPullConcurrencyTest'
```

PostgreSQL is required: row-level locking is the behaviour under test, so an
embedded database would not be evidence.

## Result: current implementation is safe

```
[concurrency] 1 ticket, 8 threads -> 1 succeeded, 7 rejected
[concurrency] 1 tickets, 4 threads -> 1 succeeded, 3 rejected, 1 used
[concurrency] 3 tickets, 12 threads -> 3 succeeded, 9 rejected, 3 used
[concurrency] 5 tickets, 20 threads -> 5 succeeded, 15 rejected, 5 used
[concurrency] 10 pulls -> 1 fragment rows, 2 duplicate grants, granted 2, stored 2
[concurrency] duplicate pet types after 10 pulls: 0

6 tests, 0 failures
```

| Tickets | Threads | Succeeded | Tickets spent | `gacha_pulls` rows | `gacha_pull_count` |
|---:|---:|---:|---:|---:|---:|
| 1 | 8 | 1 | 1 | 1 | 1 |
| 1 | 4 | 1 | 1 | 1 | 1 |
| 3 | 12 | 3 | 3 | 3 | 3 |
| 5 | 20 | 5 | 5 | 5 | 5 |

Fragments stored equal fragments granted. No child ends with two
`pet_fragments` rows. No pet type is granted twice.

## Proving the test can detect a race

A concurrency test that passes proves nothing unless it fails when the guard is
gone. The two pessimistic locks on this path were removed temporarily —
`ChildProfileRepository.findWithLockById` and
`TicketRepository.findFirstByChildIdAndTicketTypeAndUsedAtIsNullOrderByCreatedAtAsc`
— and the same tests were rerun:

```
[concurrency] 1 ticket, 8 threads -> 6 succeeded, 2 rejected
[concurrency] 1 tickets, 4 threads -> 4 succeeded, 0 rejected, 1 used
[concurrency] 3 tickets, 12 threads -> 10 succeeded, 2 rejected, 2 used
[concurrency] 5 tickets, 20 threads -> 14 succeeded, 6 rejected, 3 used

6 tests, 5 failed
```

| Tickets | Threads | Succeeded without locks | Tickets actually spent |
|---:|---:|---:|---:|
| 1 | 8 | **6** | 1 |
| 1 | 4 | **4** | 1 |
| 3 | 12 | **10** | 2 |
| 5 | 20 | **14** | 3 |

One ticket producing six rewards is the double-spend the locks prevent. The
locks were restored immediately and `git diff` confirmed the production files
were byte-identical to `HEAD` before the final run.

## What was changed

**Nothing in production code.** The existing pessimistic locking is correct for
this flow and was left exactly as it was. What is new is the test that holds it
in place, so removing the locks later fails the build instead of silently
reintroducing a double-spend.

## Limitations

- Single JVM, single database node. This shows row-level locking serializes
  concurrent transactions on one PostgreSQL instance; it says nothing about
  multiple application instances beyond the fact that the lock is held in the
  database rather than in application memory.
- Thread counts are 4–20. No sustained load, and no measurement of lock wait
  time or throughput under contention.
- Only the gacha pull flow is covered. Other reward paths — mission submission,
  quest claims, stage completion rewards, return rewards — use similar
  pessimistic locking but have no concurrency test here.
- The test asserts outcomes, not the mechanism. It would also pass if the
  serialization came from something other than the intended locks.
