# AImong 문제은행 생성·검증 파이프라인

8~13세 어린이 AI 리터러시 학습 앱 **AImong**(2026 캡스톤)의 문제은행을 만들고 검증한 파이프라인입니다.
본 저장소는 **김한욱이 단독으로 설계·구현한 문항 생성·검증 부분만** 분리한 것입니다. 앱과 서버 구현은 팀 저장소([KDUcapstone/AImong](https://github.com/KDUcapstone/AImong))에 있고 다른 팀원이 담당했습니다.

---

## 무엇을 푼 문제인가

문항을 LLM으로 한 번에 생성하면 **한쪽 품질을 고칠 때 다른 쪽이 무너집니다.**

- 정답 오류를 고치면 → 오답이 너무 쉬워집니다
- 중복을 줄이려 하면 → 상황문이 어색해집니다
- 문장을 안전하게 다듬으면 → `그대로 믿어요`, `무조건` 같은 뻔한 오답이 늘어납니다

수동 수정으로는 이 순환이 끝나지 않습니다. 1,056문항 규모에서는 사람이 전수 검토할 수도 없습니다.

**그래서 목표를 "AI가 좋은 문제를 만들게 하는 것"이 아니라 "품질 기준을 검사 가능한 규칙으로 바꾸고, 그 검사를 파이프라인 단계로 고정하는 것"으로 잡았습니다.**

---

## 설계

```text
미션 설계
  → blueprint 생성 → blueprint 검증
  → 문항 생성
  → deterministic validator        ← 규칙으로 판정 가능한 것은 전부 여기서
  → 위험 문항만 LLM Judge          ← 규칙으로 못 잡는 것만, 전체 재검증 안 함
  → 실패 문항 재생성
  → 전체 bank 검증
  → 통과본만 seed SQL로 반영
```

핵심 판단 두 가지입니다.

**1. 판정 가능한 것과 판단이 필요한 것을 나눈다.**
필수 필드 누락, 정답 인덱스 범위, 완전 중복, `externalId` 충돌, 유형·난이도·팩 분포 계약은 **규칙으로 100% 판정됩니다.** LLM을 부를 이유가 없습니다. LLM Judge는 규칙이 판정할 수 없는 것(문맥상 오답이 정답처럼 읽히는가)에만, **위험 문항으로 걸러진 것에만** 씁니다. 전체 1,056문항을 LLM으로 재검증하지 않는 구조라 비용과 시간이 문항 수에 비례해 늘지 않습니다.

**2. 하드 계약과 품질 목표를 구분한다.**
총 960문항 / 3챕터 / 16미션 / 미션당 60문항 / packNo 분포 / externalId 중복 없음 / answer 인덱스 정상은 **깨지면 앱이 동작하지 않는 하드 계약**이라 실패 시 파이프라인을 멈춥니다. FILL 비중이나 난이도 분포는 **조정 가능한 품질 목표**라 리포트로만 남기고 통과시킵니다. 둘을 섞으면 사소한 품질 편차 때문에 배포가 막힙니다.

설계 전문은 [`docs/backend-question-generation-system-guide.md`](docs/backend-question-generation-system-guide.md)에 있습니다.

---

## 결과

최종 검증 결과 ([`reports/02-replaced-report.md`](reports/02-replaced-report.md)):

| 항목 | 결과 |
|---|---|
| 유사도 0.9 이상 중복 쌍 | **109쌍 → 0쌍** |
| 실제 교체 문항 | **97개** (16개 미션 전반, 미션당 2~10개) |
| 필수 필드 누락 | 0건 |
| 정답 인덱스 오류 | 0건 |
| 완전 중복 문항 그룹 | 0개 |
| `termHints` 누락 | 0개 (문항당 최대 3개) |
| 전체 문항 | 1,056개 |

의미 유사도 감사는 `text-embedding-3-large`로 3,168개 텍스트 뷰를 임베딩했고, **캐시 적중 3,165 / 미스 3 / 실제 API 호출 1회**로 끝났습니다 ([`reports/04-openai-semantic-similarity-report.md`](reports/04-openai-semantic-similarity-report.md)). 임베딩을 캐시하지 않았다면 재실행마다 전량 재호출이 발생합니다.

### 중간에 방향을 한 번 바꿨습니다

1차 검토([`reports/01-reviewed-report.md`](reports/01-reviewed-report.md))에서 **완전 중복은 0개인데 유사도 0.94 이상 후보가 31쌍** 나왔습니다. 그런데 후보를 열어 보니 *말끝만 바뀐 문항*과 *긍정/부정을 대조시킨 의도된 문항*이 같이 잡혀 있었습니다. **자동 교체 대상으로 바로 쓸 수 없다고 판단해 1차에서는 원본을 보존하고 용어 해설(`termHints`)만 추가**했습니다.

교체는 참고 자료(KERIS 교재)를 근거로 새 문항을 쓸 수 있게 된 2차에서 실행했습니다. 이때도 문항 유형과 난이도 구조는 유지하고 **질문 장면과 보기 구성을 함께** 바꿨습니다 — 문장만 바꾸면 유사도 점수는 내려가도 체감 중복은 그대로이기 때문입니다.

> **유사도 점수는 교체 대상을 정해 주지 않습니다.** 점수가 높은 쌍에는 진짜 중복과 의도된 대조가 섞여 있습니다. 자동 지표는 후보를 좁히는 데까지만 쓰고, 교체 여부는 사람이 판단합니다.

---

## 저장소 구성

```
scripts/
  review_question_bank.py        1차 검토 — 완전중복·유사후보 검출, termHints 주입
  replace_similar_questions.py   2차 교체 — 유사쌍 교체, 최종 전수 검증, 리포트 생성
  export_question_bank.py        백엔드 산출물 변환 — JSON → seed SQL + 어댑터 스모크 리포트
  generate_issue_inventory.js    리포트 3종을 대조해 잔여 이슈 인벤토리 생성

reports/
  01-reviewed-report.md          1차 검토 결과 (완전중복 0, 유사후보 31쌍, termHints 544문항)
  02-replaced-report.md          2차 교체 결과 + 최종 검증 (109→0쌍, 97문항 교체)
  03-option-quality-report.md    보기(오답) 품질 — 반복 오답 상위 목록
  04-openai-semantic-similarity-report.md   의미 유사도 감사
  05-current-issue-inventory.md  잔여 이슈 전수 목록

config/
  mission-config.json            미션·주제·유형/난이도 분포 계약 (960문항 기준)
  mission-config-480.json        축소 구성

data/
  question-bank-1056.json        최종 문제은행 (1,056문항)

docs/
  backend-question-generation-system-guide.md   생성 시스템 설계 문서
```

## 실행

`scripts/`의 파이썬 스크립트는 표준 라이브러리만 사용하며 네트워크를 호출하지 않습니다. 결정적으로 동작하므로 같은 입력에 같은 출력이 나옵니다.

```bash
AIMONG_ROOT=/path/to/workdir python3 scripts/review_question_bank.py
```

`AIMONG_ROOT`를 생략하면 이 저장소 루트를 작업 디렉터리로 씁니다. 입력·출력은 `$AIMONG_ROOT/.tmp/` 아래 단계별 디렉터리에 놓입니다.

`export_question_bank.py`는 `--help`로 인자를 확인하세요.

---

## 범위와 한계

- **본인 기여:** 서비스 기획, 문제은행 생성·검증 시스템 설계, 이 저장소의 스크립트·설정·리포트 전부. 팀 저장소에서는 엔티티·enum 정합성 조정과 배포 프로필 등 일부 기술 커밋에 참여했습니다.
- **본인 기여 아님:** 서버 핵심 도메인 기능 구현, Android 앱 구현.
- 문항 내용은 KERIS 등 공식 교육자료의 학습 목표를 기준으로 작성했습니다. 원 교재 자체는 저작권 문제로 이 저장소에 포함하지 않았습니다.
- LLM Judge 단계는 설계·운용했으나 프롬프트와 호출 코드는 팀 저장소 쪽에 있어 여기 포함되지 않았습니다. 이 저장소에 담긴 것은 **결정적 검증 단계와 그 산출물**입니다.
