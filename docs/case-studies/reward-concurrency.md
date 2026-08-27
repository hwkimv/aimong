# Reward concurrency: verifying rather than changing

## Context

The backend applies `PESSIMISTIC_WRITE` widely — 21 repository methods across
tickets, child profiles, fragments, quests, streaks, quiz attempts and stage
rewards. Locks being present is not the same as locks being correct, and none of
them had a concurrency test.

## Problem

The gacha pull is the flow where a mistake would cost the most: it spends a
ticket, increments a per-child counter, and grants a pet or fragments.
`GachaPullService.pull` has the classic racing shape:

```java
ChildProfile childProfile = childProfileRepository.findWithLockById(childId)…
Ticket ticket = ticketRepository.findFirstByChildIdAndTicketTypeAndUsedAtIsNullOrderByCreatedAtAsc(childId, ticketType)
        .orElseThrow(() -> new AimongException(ErrorCode.BAD_REQUEST, "티켓이 부족해요!"));
…
ticket.markUsed();
childProfile.recordGachaPull(drawResult.grade());
```

Read an unused ticket, check it exists, then mark it used. Two requests arriving
together — a double tap, or a client retry after a timeout — could both read the
same ticket.

## Reproduction attempt

Ran `GachaPullService.pull` unmodified from 4–20 threads released simultaneously
against real PostgreSQL, with a known number of tickets seeded.

```
[concurrency] 1 ticket,  8 threads -> 1 succeeded, 7 rejected
[concurrency] 3 tickets, 12 threads -> 3 succeeded, 9 rejected, 3 used
[concurrency] 5 tickets, 20 threads -> 5 succeeded, 15 rejected, 5 used
```

**Not reproduced.** Successes exactly equal tickets in every configuration.
Fragments stored equal fragments granted, and no pet type is granted twice.

## Is the test actually capable of failing?

This is the part that matters. A concurrency test that passes against correct
code and would also pass against broken code is worse than no test, because it
converts an untested assumption into a documented one.

Both locks on this path were removed temporarily and the same tests rerun:

| Tickets | Threads | Succeeded with locks | Succeeded without locks | Tickets actually spent |
|---:|---:|---:|---:|---:|
| 1 | 8 | 1 | **6** | 1 |
| 1 | 4 | 1 | **4** | 1 |
| 3 | 12 | 3 | **10** | 2 |
| 5 | 20 | 5 | **14** | 3 |

One ticket produced six rewards. The test detects the race, so its passing
against the real implementation is evidence.

The locks were restored and `git diff` confirmed the production files matched
`HEAD` exactly before the final run.

## Root cause of the safety

Two things combine:

1. `findWithLockById` takes a row lock on the child profile at the start of the
   transaction, so concurrent pulls for the same child serialize on that row
   before they ever reach the ticket.
2. `findFirst…UsedAtIsNull…` takes a row lock on the ticket itself, so a second
   transaction that somehow reached it would block and then re-evaluate.

The lock is held in the database, not in application memory, so it holds across
multiple application instances.

`pet_fragments` additionally carries `UNIQUE (child_id)` from V16, which means
even a failure of the locking would surface as a constraint violation rather
than as two fragment rows.

## Decision

**No change.** The implementation is correct for this flow, and the least
invasive useful action was to pin the behaviour with a test.

The alternatives were all worse:

| Option | Assessment |
|---|---|
| Leave it untested | The existing locks are load-bearing and nothing would catch their removal. |
| Add a concurrency test, change nothing else | **Chosen.** |
| Replace pessimistic with optimistic locking | Would trade a blocking wait for retry handling that does not exist, to solve a problem that is not occurring. |
| Add an idempotency key | Nothing here needs one; the ticket row already is the idempotency token. |

## Verification

`GachaPullConcurrencyTest`, 6 cases, requires `TEST_DB_URL` and runs in CI where
PostgreSQL is always provided. Full backend suite: 161 tests, 0 failures with a
database; 159 tests, 0 failures, 9 skipped without one.

Numbers and the without-locks run are recorded in
[evidence/concurrency-gacha-pull.md](../evidence/concurrency-gacha-pull.md).

## Limitations

- Single JVM against a single PostgreSQL node.
- 4–20 threads; no sustained load, no lock-wait or throughput measurement.
- Only this flow is covered. Mission submission, quest claims, stage completion
  rewards and return rewards use similar locking and remain untested here.
- The test asserts outcomes, not mechanism: it would also pass if serialization
  came from somewhere other than the intended locks.
