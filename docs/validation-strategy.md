# Validation strategy

AI-generated questions are treated as untrusted input. Two layers decide what
happens to them, and the split between the layers is the point of the design.

```
question bank JSON
        │
        ▼
┌───────────────────┐   violation ──▶ pipeline FAILS, no artifacts written
│  Hard contract    │
│  deterministic    │
└───────────────────┘
        │ pass
        ▼
┌───────────────────┐   finding ────▶ recorded as a review candidate
│  Quality audit    │                 pipeline still PASSES
│  heuristic        │
└───────────────────┘
        │
        ▼
  backend JSON + seed SQL
        │
        ▼
  PostgreSQL load + read-back verification
```

## Hard contract — deterministic, blocking

A hard contract violation means the data cannot be trusted as backend data: a
required field is missing, an enum value is unknown, an identifier collides, an
answer points outside its options, or a declared quota does not hold.

These are all decidable by inspection. There is no judgement involved, so
failing the build on them costs nothing in false positives.

Implemented in [`pipeline/src/aimong_qbank/contract.py`](../pipeline/src/aimong_qbank/contract.py).
Rules are listed in [data-contract.md](data-contract.md).

## Quality audit — heuristic, advisory

| Check | What it looks for |
|---|---|
| `duplicatePrompt` | identical prompts after normalization |
| `similarPrompt` | prompts ≥ 0.94 similar within the same mission |
| `absoluteWording` | distractors using 항상 / 절대 / 무조건 / 모든 / 반드시 |
| `answerLengthBias` | correct option far longer than every distractor |
| `duplicateOption` | the same option repeated inside one question |
| `contentTagCount` | more than three tags on one question |

Current run: **95 warnings** (82 absolute wording, 5 answer-length bias, 8 tag
count), 0 duplicate or near-duplicate prompts.

Every one of these can be wrong. "모든" in a distractor is often a giveaway, but
sometimes it is simply the correct phrasing. A long correct answer is sometimes
just a longer correct answer. Blocking on them would train whoever runs the
pipeline to bypass it.

Implemented in [`pipeline/src/aimong_qbank/quality.py`](../pipeline/src/aimong_qbank/quality.py).

## Why the layers are not merged

Two failure modes motivate the split, and both are easy to fall into:

- **Promoting heuristics to blocking.** The pipeline fails on judgement calls,
  so whoever runs it starts passing a bypass flag, and the deterministic checks
  stop being enforced along with the heuristic ones.
- **Demoting contract rules to warnings.** A run that is failing for a real
  reason is made to pass by moving the rule that caught it. This is the more
  dangerous direction because the output still looks green.

The second is what the previous exporter effectively did by accident: its total
question-count check read `globalPlan["totalQuestions"]` while the config key was
`totalQuestionCount`, so the check silently evaluated `None` and never ran. The
config claimed 960 and the data held 1,056 for as long as that went unnoticed.
The current implementation fails when a contract value is absent rather than
skipping the check.

## Why similarity does not delete anything

The similarity check reports pairs. It does not remove a question, and it does
not pick which of a pair to keep. Two questions can be lexically close and still
test different things, and the reverse is also true — two questions can share
almost no wording and test exactly the same fact. A similarity score is evidence
for a human decision, not the decision.

## Where an LLM judge would sit

Not implemented. If it is added, the intended shape is:

```
deterministic rule ──▶ PASS / FAIL          (authoritative)
heuristic          ──▶ review candidate     (advisory)
LLM judge          ──▶ review assistance    (advisory)
human              ──▶ semantic decision    (authoritative)
```

An LLM judge would rank and explain review candidates. It would not be given
authority to delete a question or change an answer key, for the same reason the
similarity check is not: a model's judgement on a single question is not
reproducible, and a wrong answer key that a model introduced is indistinguishable
from a correct one downstream.

## What is deliberately not covered

- **Semantic correctness.** Nothing here checks that an answer is factually
  right or age-appropriate. That is a human review task and the pipeline does
  not claim otherwise.
- **Cross-mission pedagogical coherence.** Whether the 16 missions build on each
  other sensibly is out of scope.
- **Embedding-based similarity.** Only lexical similarity is implemented; see
  [Limitations in the README](../README.md#limitations).
