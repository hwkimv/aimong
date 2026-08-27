# AImong

초등학생 대상 AI 리터러시 교육 앱입니다. 자녀는 미션·퀘스트·챗봇·가챠·스트릭으로
학습하고, 부모는 자녀 현황을 확인합니다.

이 저장소는 **Spring Boot 백엔드**와, AI가 생성한 문항을 백엔드 DB에 적재하기 전에
검증하는 **문제은행 품질 파이프라인**을 함께 담고 있습니다. Android 클라이언트는
맥락 파악용으로 포함되어 있으며 여기서 수정하지 않습니다.

이 저장소의 초점은 하나입니다. **AI가 만든 데이터를 그대로 믿지 않고, 검증 가능한
계약과 테스트를 거쳐 실제 PostgreSQL에 적재할 수 있음을 재현 가능하게 보이는 것.**

---

## Architecture

```
Android client
      │ REST /api
      ▼
Spring Boot backend ──▶ PostgreSQL (Flyway V1–V16)
      ├──▶ Firebase (auth, FCM)
      └──▶ OpenAI (chat, image)
              ▲
              │ seed SQL
Question quality pipeline
  data ─▶ hard contract ─▶ quality audit ─▶ backend JSON + seed SQL ─▶ PostgreSQL 검증
```

자세한 구조는 [docs/architecture.md](docs/architecture.md)에 있습니다.

---

## Question quality pipeline

AI가 생성한 문항은 신뢰하지 않는 입력으로 다룹니다. 검증은 두 층으로 나뉩니다.

```
question bank JSON
        │
        ▼
  Hard contract  ── 위반 ──▶ 파이프라인 FAIL, 산출물 생성 안 함
   (결정적 규칙)
        │ 통과
        ▼
  Quality audit  ── 발견 ──▶ 사람 검토 후보로 기록, 파이프라인은 PASS
   (휴리스틱)
        │
        ▼
  backend JSON + seed SQL
        │
        ▼
  실제 PostgreSQL 적재 후 되읽어 원본과 대조
```

**Hard contract**는 필수 필드 누락, 알 수 없는 enum, `externalId` 중복, 선택지
범위를 벗어난 정답, 선언된 구조 쿼터 위반처럼 판단이 개입하지 않는 규칙입니다.
위반하면 export가 실패합니다.

**Quality audit**는 중복·유사 문항, 절대어를 쓴 오답, 정답 길이 편향처럼 사람이
봐야 하는 후보입니다. 틀릴 수 있으므로 export를 막지 않습니다.

두 층을 섞지 않는 이유, 그리고 유사도만으로 문항을 자동 삭제하지 않는 이유는
[docs/validation-strategy.md](docs/validation-strategy.md)에 정리했습니다.

---

## Dataset

현재 canonical dataset은 **1,056문항**입니다.

| 항목 | 값 |
|---|---|
| 문항 수 | 1,056 |
| 미션 수 | 16 |
| 미션당 문항 | 66 |
| 미션당 pack 크기 | P1–P5 각 10, P6 16 |
| 미션당 난이도 | LOW 30, MEDIUM 20, HIGH 16 |
| 전체 type | OX 207, MULTIPLE 332, FILL 186, SITUATION 331 |
| content tag 종류 | 11 |

`config/mission-config.json`은 이전 960문항 생성 계획이며 현재는 stale합니다.
데이터 자체가 960 → 1,056 확장(미션당 HIGH 6문항, `P6-11..P6-16`)을 기록하고
있어 1,056을 canonical로 확정했습니다. 근거와 전체 규칙은
[docs/data-contract.md](docs/data-contract.md)에 있습니다.

계약은 `pipeline/contracts/dataset-contract.json` 한 곳에만 있고, 데이터에서
유도하되 **데이터가 스스로 선언한 값과 어긋나면 유도가 실패**합니다. 문항을 지워
검증을 통과시키는 우회가 막힙니다.

---

## Running locally

필요한 것: Python 3.11+, Java 21. 파이프라인 검증에는 데이터베이스가 필요 없습니다.

```bash
make install
make verify
```

`make verify`는 계약 최신성 확인 → hard contract → quality audit → backend JSON /
seed SQL export → 테스트를 한 번에 실행합니다.

현재 실행 결과:

```
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
- question_bank rows: 1,056
- question_answer_keys rows: 1,056
- mission_sets rows: 96

71 passed
```

다른 명령:

```bash
make test        # pytest만
make export      # backend JSON + seed SQL 재생성
make contract    # 계약 재유도
make db-verify   # 실제 PostgreSQL 적재 검증 (AIMONG_TEST_DB_URL 필요)
```

---

## Testing

| 명령 | 결과 |
|---|---|
| `make test` | 71 passed, 7 skipped |
| `AIMONG_TEST_DB_URL=… make test` | 78 passed |
| `cd backend && ./gradlew test` | 151 tests, 0 failures, 1 skipped |
| `cd backend && TEST_DB_URL=… ./gradlew test` | 151 tests, 0 failures, 0 skipped |

DB 없이도 전부 통과합니다. DB가 필요한 테스트는 건너뛰되 사유를 남기고, CI는
항상 PostgreSQL을 제공하므로 CI에서는 건너뛰지 않습니다.

---

## PostgreSQL verification

seed SQL이 생성됐다는 것은 적재 가능하다는 뜻이 아닙니다. 그래서 백엔드의 Flyway
마이그레이션을 빈 DB에 그대로 적용하고, seed를 실행한 뒤 되읽어 확인합니다.

```bash
export AIMONG_TEST_DB_URL="postgresql://postgres@localhost:5432/aimong_test"
make export && make db-verify
```

검증 항목: 행 수, `externalId` → UUID 유일성, `set_id` 바인딩, FK, unique·check
제약이 실제로 거부하는지, 샘플 행을 원본 JSON과 대조, 재실행 시 멱등성.

실행 결과는 [docs/evidence/postgres-integration.md](docs/evidence/postgres-integration.md)에
있습니다.

---

## CI

| Workflow | 내용 | 외부 키 |
|---|---|---|
| `question-pipeline` | 계약 검증, export, pytest, PostgreSQL 적재 | 불필요 |
| `backend` | Gradle 테스트, PostgreSQL service | 불필요 |
| `semantic-audit` | 임베딩 기반 검사 (미구현) | `workflow_dispatch` 전용 |

기본 CI는 유료 API 키 없이 통과해야 하므로 OpenAI가 필요한 검사는 분리했습니다.

---

## Repository structure

```
backend/            Spring Boot API 서버
  src/main/java/com/aimong/backend/
    domain/         auth, chat, mission, quest, gacha, pet, streak, home, parent, …
    global/         security, exception, config, scheduler
    infra/          openai, fcm, supabase
  src/main/resources/db/migration/   Flyway V1–V16

pipeline/           문제은행 검증 파이프라인
  contracts/        dataset-contract.json — 계약의 단일 출처
  data/             question-bank-1056.json — canonical dataset
  src/aimong_qbank/ contract, quality, adapter, export, cli
  tests/            pytest
  tools/            derive_contract.py, verify_postgres.py
  config/, docs/, reports/, scripts/   생성 당시 설정과 기록 (superseded)

frontend/android/   Android 클라이언트 (맥락용, 수정하지 않음)
docs/               architecture, data contract, validation strategy, case studies, evidence
```

---

## Documentation

| 문서 | 내용 |
|---|---|
| [architecture.md](docs/architecture.md) | 전체 구조, 문항 서빙 경로, 외부 의존성 |
| [data-contract.md](docs/data-contract.md) | 계약 전체와 백엔드 매핑 |
| [validation-strategy.md](docs/validation-strategy.md) | 두 층 검증, LLM judge의 역할 제한 |
| [case-studies/question-set-binding.md](docs/case-studies/question-set-binding.md) | `set_id` 누락으로 96개 세트가 비던 문제 |
| [case-studies/external-api-timeouts.md](docs/case-studies/external-api-timeouts.md) | 15초처럼 보였던 타임아웃이 실제로는 무제한이던 문제 |
| [case-studies/silent-contract-hole.md](docs/case-studies/silent-contract-hole.md) | 실행되지 않던 계약 검사 |
| [evidence/dataset-validation.md](docs/evidence/dataset-validation.md) | 실행 조건과 수치 |
| [evidence/postgres-integration.md](docs/evidence/postgres-integration.md) | 실제 DB 적재 결과 |

---

## Provenance

원본 AImong은 3인 팀 캡스톤 프로젝트입니다. 이 저장소는 그중 백엔드와 문제은행
파이프라인을 개인적으로 이어서 개선하는 사본이며, 팀 저장소를 `upstream`으로
둡니다.

- **팀 구현** — Android 클라이언트, 백엔드 도메인 전반, Flyway 스키마, 인증,
  게임화 기능. 커밋 이력에 세 명의 작성자가 그대로 남아 있습니다
  (`git shortlog -sne`).
- **이 저장소에서 이후 추가한 것** — 문항 데이터 계약 분리와 hard/quality 이층
  검증, `set_id` 바인딩 수정, 실제 PostgreSQL 적재 검증, OpenAI 호출 타임아웃과
  전용 스레드 풀, fresh clone에서 동작하는 테스트 환경, CI, 위 문서.

---

## Limitations

현재 상태에서 사실이 아닌 것을 적지 않기 위해 남깁니다.

- **품질 경고 95건은 미검토 상태입니다.** 결함이 아니라 검토 후보이고, 사람이
  훑은 적이 없습니다.
- **의미·사실 검증은 없습니다.** 어떤 검사도 정답이 실제로 옳다고 말하지 않습니다.
- **유사도는 어휘 수준입니다.** 임베딩 기반 비교는 구현되어 있지 않습니다.
  `semantic-audit` 워크플로는 자리만 잡아둔 상태입니다.
- **LLM judge는 없습니다.** 설계상 위치만 문서화했습니다.
- **DB 검증은 데이터 계층까지입니다.** HTTP API로 실제 미션 풀이를 끝까지 돌려본
  테스트는 없습니다.
- **성능 수치는 없습니다.** 이 저장소에는 부하 측정 결과가 없고, 문서 어디에도
  처리량·지연 개선을 주장하지 않습니다. 외부 API 관련 수치는 단일 호출이
  제한되는지만 보인 것입니다.
- **동시성은 검증하지 않았습니다.** 백엔드는 상태 변경 경로에 비관적 락을 널리
  쓰고 있으나, 이 저장소에서 동시성 테스트를 작성해 확인하지는 않았습니다.
- **Flyway 러너 자체는 거치지 않습니다.** 마이그레이션 SQL을 순서대로 직접
  적용하므로 checksum 검증 동작은 다루지 않습니다.
- **마이그레이션은 V1–V16까지입니다.** `main` 기준이며 이후 버전은 없습니다.
