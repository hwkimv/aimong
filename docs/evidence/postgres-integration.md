# Evidence — PostgreSQL seed load

Generating a `.sql` file only proves the file was written. This run applies the
backend's own Flyway migrations to an empty database, loads the generated seed,
and reads the rows back.

## Conditions

| | |
|---|---|
| Commit | `54d8a5b` (before the commit that adds this file) |
| Dataset | `pipeline/data/question-bank-1056.json` |
| Contract | `pipeline/contracts/dataset-contract.json` v1.0 |
| Schema | `backend/src/main/resources/db/migration`, V1–V16 applied in version order |
| PostgreSQL | 18.6 (local instance, trust auth, empty database) |
| Platform | Linux 6.6.87.2-microsoft-standard-WSL2, Python 3.13.9 |

## Commands

```bash
make export
AIMONG_TEST_DB_URL="postgresql://postgres@127.0.0.1:55432/aimong_test" make db-verify
AIMONG_TEST_DB_URL="postgresql://postgres@127.0.0.1:55432/aimong_test" make test
```

## Result

```
==> applying backend migrations      V1 … V16, 16 files
==> applying seed SQL
==> verifying loaded data

  OK  missions rows: 16
  OK  mission_sets rows: 96
  OK  question_bank rows: 1056
  OK  question_answer_keys rows: 1056
  OK  distinct question ids: 1056
  OK  questions with NULL set_id: 0
  OK  orphan set_id references: 0
  OK  sets with fewer active questions than question_count: 0
  OK  questions whose mission is missing: 0
  OK  answer keys without a question: 0
  OK  missions not holding 66 questions: 0
  OK  duplicate question id rejected by primary key
  OK  duplicate mission set star/variant rejected by unique constraint
  OK  mission_sets.question_count CHECK rejected a non-10 set
  OK  question_bank.mission_id foreign key rejected an unknown mission
  OK  7 sample rows read back match the source JSON
  OK  question_bank rows after reseed: 1056

PostgreSQL verification PASS
```

Test suite against the same database: **78 passed**. Without
`AIMONG_TEST_DB_URL` the seven database tests skip and the suite reports
**71 passed, 7 skipped**, so the default run needs no database.

## Identifier uniqueness

`public.question_bank` has no `external_id` column. Uniqueness is carried by
the primary key, derived as `UUID.nameUUIDFromBytes("question:" + externalId)`
so that reseeding updates a row instead of inserting a second one. Two distinct
`externalId` values collapsing into one row would therefore be silent, which is
why the row count is asserted after the load: 1056 external ids produced 1056
distinct ids.

## set_id reproduction

The previous exporter wrote `set_id` as `NULL`. Measured against the loaded
database:

```sql
BEGIN;
UPDATE public.question_bank SET set_id = NULL;
SELECT count(*) FROM public.mission_sets s
WHERE (SELECT count(*) FROM public.question_bank q
       WHERE q.set_id = s.set_id AND q.is_active) = 0;
ROLLBACK;
```

| | sets returning no questions |
|---|---|
| Before (`set_id` NULL) | 96 of 96 |
| After | 0 of 96 |

## Limitations

- The migrations are applied directly rather than through the Flyway runner, so
  Flyway's own checksum and ordering behaviour is not covered here.
- Migrations V17 and above are not present on `main`; only V1–V16 were applied.
- The instance is single-node with default settings. Nothing here measures
  behaviour under concurrency or production configuration.
