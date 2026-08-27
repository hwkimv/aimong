# Architecture

AImong is a children's AI-literacy app: a Spring Boot backend, an Android
client, and a question bank that is generated offline and loaded into the
backend database.

This repository holds the backend and the question-quality pipeline. The Android
client is present for context and is not modified here.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Android client                           │
└───────────────────────────────┬─────────────────────────────────┘
                                │ REST, /api
┌───────────────────────────────▼─────────────────────────────────┐
│                    Spring Boot backend                          │
│                                                                 │
│  auth ── chat ── mission ── quest ── gacha ── pet ── streak      │
│  home ── parent ── customquest ── privacy ── reward ── stagereward│
│                                                                 │
│  global/  security (JWT + Firebase filters), exception, config   │
│  infra/   openai, fcm, supabase                                  │
└───────┬───────────────────────────┬─────────────────────┬───────┘
        │                           │                     │
        ▼                           ▼                     ▼
┌───────────────┐          ┌────────────────┐    ┌────────────────┐
│  PostgreSQL   │          │  Firebase      │    │  OpenAI        │
│  Flyway V1–16 │          │  auth + FCM    │    │  chat + image  │
└───────▲───────┘          └────────────────┘    └────────────────┘
        │ seed SQL
┌───────┴─────────────────────────────────────────────────────────┐
│                  Question quality pipeline                      │
│                                                                 │
│  data/question-bank-1056.json                                   │
│           │                                                     │
│           ▼                                                     │
│  contracts/dataset-contract.json ──▶ hard contract (blocking)    │
│           │                          quality audit (advisory)    │
│           ▼                                                     │
│  adapter ──▶ backend JSON                                        │
│          └─▶ seed SQL ──▶ verified against a real PostgreSQL     │
└─────────────────────────────────────────────────────────────────┘
```

## Question serving

The backend serves a fixed set of 10 questions per attempt. Understanding this
path matters because it is what the pipeline's output has to satisfy.

```
GET mission set
      │
      ▼
MissionQuestionSetFactory.create(setId, missionId, starLevel, …)
      │
      ├─ 1. questions WHERE set_id = :setId        ◀── the intended path
      │
      ├─ 2. fallback: questions WHERE pack_no = starLevel
      │       reachable only when packNo == starLevel, so packs 4–6 never match
      │
      └─ 3. fallback: questions WHERE difficulty = difficultyFor(starLevel)
              ignores the set entirely
      │
      ▼
selectFixedQuestionSet — takes 10, deduplicating near-identical prompts
```

Each mission has 6 sets, `S0101-L1` … `S0101-L6`, mapped to star levels 1–3 with
two variants each. Packs 1–5 hold 10 questions and pack 6 holds 16, so every set
has at least the 10 the backend needs.

The exporter previously wrote `set_id` as `NULL`, which sent all 96 sets down
the fallback chain. See
[case-studies/question-set-binding.md](case-studies/question-set-binding.md).

## Database

Schema is owned by Flyway migrations in
`backend/src/main/resources/db/migration` (V1–V16 on `main`).

Question-bank tables:

| Table | Purpose |
|---|---|
| `public.missions` | 16 missions, unique `mission_code` |
| `public.mission_sets` | 96 sets, `CHECK (question_count = 10)`, unique `(mission_id, star_level, variant_no)` |
| `public.question_bank` | 1,056 questions, FK to missions and sets, `options`/`content_tags` JSONB |
| `private.question_answer_keys` | answer payload and explanation, FK to `question_bank` |

Answer keys live in a separate `private` schema so that the serving queries,
which select an explicit column list from `public.question_bank`, cannot return
an answer by accident.

The schema is PostgreSQL-specific: enum types (`question_type_enum`,
`question_difficulty_enum`, …), JSONB columns, and native queries that cast to
those enums. H2 would not exercise the same behaviour, which is why database
tests run against real PostgreSQL.

## External dependencies

| Dependency | Needed for | If it fails |
|---|---|---|
| PostgreSQL | every request that touches state | the API cannot serve |
| Firebase Auth | parent authentication | parent endpoints fail; child JWT paths keep working |
| Firebase FCM | push notifications | notifications are lost; core flows unaffected |
| OpenAI | chat replies and image generation | chat returns a timeout-shaped error; everything else unaffected |

OpenAI calls run on a dedicated bounded pool with a read timeout, so a slow
upstream degrades chat rather than the whole application. See
[case-studies/external-api-timeouts.md](case-studies/external-api-timeouts.md).
