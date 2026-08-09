# 백엔드용 문제은행 생성 시스템 가이드

## 1. 목적

이 문서는 백엔드에서 AImong 문제은행을 안정적으로 생성하기 위한 시스템 가이드입니다.

현재 문제은행은 수동 수정만 반복하면 한쪽 품질을 고칠 때 다른 품질이 무너지는 문제가 있습니다.
예를 들어 정답 오류를 고치면 오답이 너무 쉬워지고, 중복을 줄이려 하면 상황문이 어색해지고, 문장을 안전하게 만들면 `그대로 믿어요`, `확인하지 않아요`, `무조건` 같은 너무 뻔한 오답이 늘어납니다.

목표는 AI가 한 번에 좋은 문제를 만들게 하는 것이 아닙니다.
목표는 다음 흐름을 시스템으로 고정하는 것입니다.

```text
미션 설계
-> blueprint 생성
-> blueprint 검증
-> 문제 생성
-> deterministic validator
-> 위험 문항 LLM Judge
-> 실패 문항 재생성
-> 전체 bank 검증
-> 통과본만 반영
```

## 2. 유지할 구조

앱과 DB가 기대하는 큰 구조는 유지합니다.

| 항목 | 기준 |
| --- | ---: |
| 총 문항 수 | 960 |
| 챕터 수 | 3 |
| 미션 수 | 16 |
| 미션당 문항 수 | 60 |
| 확정 유형 분포 | OX 192 / MULTIPLE 288 / FILL 96 / SITUATION 384 |
| 기본 난이도 분포 | LOW 384 / MEDIUM 320 / HIGH 256 |
| 팩 분포 | P1 160 / P2 160 / P3 160 / P4 160 / P5 160 / P6 160 |

반드시 지켜야 하는 하드 계약:

- 총 960문항
- 3챕터
- 16미션
- 미션당 60문항
- packNo 분포
- externalId 중복 없음
- answer 인덱스 정상

조건부로 조정 가능한 품질 목표:

- FILL 추가 감축 여부
- 난이도 분포

현재 유형 분포는 `mission-config.json` 기준으로 확정합니다.
다만 FILL은 검수가 어렵고 정답/오답 경계가 자주 흔들리므로, 생성 후 validator와 LLM Judge에서 문제가 반복되면 더 줄일 수 있습니다.
FILL을 줄이면 줄인 수량은 MULTIPLE 또는 SITUATION으로 이동합니다.

권장 유형 비율:

| 유형 | 권장 비율 |
| --- | ---: |
| OX | 15~30% |
| MULTIPLE | 25~45% |
| FILL | 8~20% |
| SITUATION | 25~45% |

## 3. 현재 목표 학습 흐름

현재 문제은행의 목적은 다음 순서입니다.

```text
AI를 알아본다
-> AI를 안전하게 쓴다
-> AI 답을 잘 판단한다
-> AI에게 잘 질문하고 활용한다
```

챕터는 3개로 유지해야 하므로, `AI를 안전하게 쓴다`와 `AI 답을 잘 판단한다`를 Ch2 안에서 함께 다룹니다.

| 챕터 | 역할 | 미션 수 | 문항 수 |
| --- | --- | ---: | ---: |
| Ch1 AI 알아보기 | AI가 무엇인지, 어떻게 배우고 판단하는지 이해 | 5 | 300 |
| Ch2 AI 안전하게 쓰고 판단하기 | 개인정보와 책임을 알고, AI 답을 믿어도 되는지 판단 | 6 | 360 |
| Ch3 AI에게 잘 질문하고 활용하기 | 좋은 질문, 재질문, 결과 개선, 내 말로 정리 | 5 | 300 |

챕터 경계:

- Ch1은 AI 개념 이해입니다. 안전, 출처, 프롬프트 기술을 깊게 묻지 않습니다.
- Ch2는 "믿기 전에 따져보기"입니다. 개인정보, 출처, 근거, 편향, 공정성, 위험 판단을 다룹니다.
- Ch3는 "잘 물어보고 고쳐 쓰기"입니다. 목적 말하기, 형식 요청, 조건 추가, 재질문, 내 말로 정리를 다룹니다.

## 4. 현재 미션 구성

미션 제목은 초등학생이 이해하기 쉬우면서도 너무 좁은 사례에 갇히지 않게 작성합니다.
예를 들어 `친구 사진 조심하기`처럼 좁게 쓰지 않고, `다른 사람의 정보를 조심해서 다루기`처럼 여러 사례를 담을 수 있게 씁니다.

| 코드 | 순서 | 챕터 | 미션 제목 | 핵심 범위 |
| --- | ---: | --- | --- | --- |
| S0101 | 1 | Ch1 AI 알아보기 | 우리 주변의 AI 찾아보기 | 생활 속 AI 기능 찾기 |
| S0102 | 2 | Ch1 AI 알아보기 | AI가 자료로 배우는 과정 알기 | 데이터, 학습, 예시 |
| S0103 | 3 | Ch1 AI 알아보기 | AI가 잘하는 일과 어려워하는 일 구분하기 | AI의 가능/한계 |
| S0104 | 4 | Ch1 AI 알아보기 | AI가 여러 정보를 알아보는 방법 알기 | 사진, 소리, 글, 영상 인식 |
| S0105 | 5 | Ch1 AI 알아보기 | AI와 사람이 할 일 구분하기 | 자동화와 사람의 역할 |
| S0201 | 6 | Ch2 AI 안전하게 쓰고 판단하기 | 개인정보를 안전하게 다루기 | 내 이름, 위치, 사진, 연락처 등 |
| S0202 | 7 | Ch2 AI 안전하게 쓰고 판단하기 | 다른 사람의 정보를 조심해서 다루기 | 타인의 정보, 허락, 공유 |
| S0203 | 8 | Ch2 AI 안전하게 쓰고 판단하기 | AI 답이 맞는지 확인하기 | AI 답 재확인, 틀릴 가능성 |
| S0204 | 9 | Ch2 AI 안전하게 쓰고 판단하기 | 출처와 근거를 비교하기 | 출처, 근거, 날짜, 공식 자료 |
| S0205 | 10 | Ch2 AI 안전하게 쓰고 판단하기 | AI 결과가 치우쳤는지 살펴보기 | 데이터 편향, 빠진 집단, 공정성 |
| S0206 | 11 | Ch2 AI 안전하게 쓰고 판단하기 | AI의 좋은 점과 조심할 점 생각하기 | 편리함, 위험, 책임, 영향 |
| S0301 | 12 | Ch3 AI에게 잘 질문하고 활용하기 | AI에게 원하는 것을 분명히 말하기 | 목적, 대상, 상황 설명 |
| S0302 | 13 | Ch3 AI에게 잘 질문하고 활용하기 | 원하는 답 형식을 요청하기 | 표, 목록, 짧은 글, 비교표 |
| S0303 | 14 | Ch3 AI에게 잘 질문하고 활용하기 | 조건을 넣어 다시 질문하기 | 추가 조건, 재질문, 구체화 |
| S0304 | 15 | Ch3 AI에게 잘 질문하고 활용하기 | AI 답을 비교하고 고치기 | 여러 답 비교, 수정, 개선 |
| S0305 | 16 | Ch3 AI에게 잘 질문하고 활용하기 | AI 도움을 내 말로 정리하기 | 베끼지 않기, 요약, 자기 표현 |

이전 구성과 맞지 않아 제거하거나 이동해야 하는 기준:

- Ch2를 `AI 안전하게 쓰기`만으로 제한하지 않습니다.
- Ch3를 `AI 판단하기`만으로 두지 않습니다.
- `AI에게 도움 요청하기`, `AI 답을 더 알맞게 고치기`, `AI 도움을 내 말로 정리하기`는 Ch3 활용 미션으로 보냅니다.
- `AI 답 다시 확인하기`, `출처와 근거 비교하기`, `데이터 편향 찾아보기`, `공정성`, `조심할 점`은 Ch2 판단 미션으로 보냅니다.
- Ch3 문제에서 출처/근거 판단을 중심 문제로 만들지 않습니다. 필요한 경우 "AI에게 질문할 때 개인정보나 출처 조건을 빼먹지 않는다" 수준의 보조 조건으로만 사용합니다.

## 5. 중복 방지 규칙

현재 구성에서 가장 중요한 것은 Ch2와 Ch3의 경계를 지키는 것입니다.

| 구분 | Ch2에 둔다 | Ch3에 둔다 |
| --- | --- | --- |
| 핵심 질문 | 이 답을 믿어도 될까? 위험하지 않을까? | 어떻게 물어보면 더 좋은 답을 받을까? |
| 중심 행동 | 확인하기, 비교하기, 판단하기, 조심하기 | 요청하기, 조건 넣기, 다시 묻기, 고치기 |
| 주요 개념 | 개인정보, 출처, 근거, 날짜, 편향, 공정성, 위험 | 목적, 대상, 형식, 조건, 재질문, 요약, 내 말 |
| 좋은 문제 예 | AI 답이 맞는지 공식 자료와 비교해요. | AI에게 표로 정리해 달라고 요청해요. |
| 피해야 할 중복 | 좋은 질문법을 길게 묻기 | 출처/근거 검증을 중심으로 묻기 |

중복 방지 세부 규칙:

- Ch2의 개인정보 문항은 `안전한 판단/보호`가 중심입니다.
- Ch3의 개인정보 문항은 `질문에 넣지 말아야 할 조건` 정도로만 보조 사용합니다.
- Ch2의 데이터/공정성 문항은 `결과를 의심하고 판단하기`가 중심입니다.
- Ch3의 데이터 문항은 `더 나은 답을 위해 조건을 추가하기`가 중심입니다.
- `출처`, `근거`, `날짜`, `공식 자료`가 정답 핵심이면 Ch2로 보냅니다.
- `표로`, `목록으로`, `초등학생이 이해하기 쉽게`, `조건을 더 넣어`, `다시 질문`이 정답 핵심이면 Ch3로 보냅니다.

## 6. Blueprint 먼저 만들기

문제를 바로 생성하면 모델은 자주 쓰는 쉬운 패턴으로 돌아갑니다.
따라서 실제 문제 문장을 만들기 전에 blueprint를 먼저 만듭니다.

Blueprint는 문항의 설계도입니다.

```json
{
  "externalId": "S0303-P4-06",
  "missionCode": "S0303",
  "chapterTitle": "AI에게 잘 질문하고 활용하기",
  "missionTitle": "조건을 넣어 다시 질문하기",
  "type": "SITUATION",
  "difficulty": "MEDIUM",
  "targetSkill": "AI 답이 부족할 때 조건을 추가해 다시 질문한다",
  "studentContext": "집에서 여행 준비물을 물어봤는데 답이 너무 넓게 나왔을 때",
  "correctReason": "대상, 상황, 필요한 형식을 추가해 다시 질문한다",
  "misconceptions": [
    "AI가 처음 답한 내용이면 충분하다고 생각한다",
    "조건을 많이 넣으면 AI가 더 헷갈린다고 생각한다",
    "답이 길면 더 좋은 답이라고 생각한다"
  ],
  "contextCategory": "FAMILY_CHOICE",
  "forbiddenPatterns": [
    "그대로 믿어요",
    "확인하지 않아요",
    "무조건",
    "항상"
  ]
}
```

Blueprint 필수 필드:

- `externalId`
- `missionCode`
- `chapterTitle`
- `missionTitle`
- `type`
- `difficulty`
- `targetSkill`
- `studentContext`
- `correctReason`
- `misconceptions`
- `contextCategory`
- `forbiddenPatterns`

## 7. 생활 맥락 기준

미션별 상황 예산을 둡니다.

| 상황 유형 | 기준 |
| --- | ---: |
| 생활 맥락 | 미션별 90% 이상 |
| 학교/수업 맥락 | 미션별 10% 이하 |

생활 맥락은 집, 스마트폰, 가족, 친구와의 대화, 유튜브/쇼츠 추천, 사진 앱, 번역 앱, 길 찾기, 키오스크, QR 메뉴, 카카오톡/메신저, 게임 추천, 쇼핑/음식 추천처럼 아이가 실제로 만날 수 있는 상황입니다.

상황이 없어도 이해 가능한 개념 확인 문제는 억지로 상황을 붙이지 않습니다.

고정 생활 맥락 카테고리:

| 카테고리 | 예시 |
| --- | --- |
| AI_GENERATED_SHORTS | AI로 만든 짧은 영상, AI 음성/이미지로 만든 영상 |
| SHORT_VIDEO_RECOMMEND | 유튜브/쇼츠 추천, 짧은 영상 추천 |
| AI_SEARCH_SUMMARY | 검색 결과 위 AI 요약, AI가 정리한 답변 |
| AI_CHATBOT_HOMEWORK | AI 챗봇으로 숙제, 검색, 글쓰기 도움 받기 |
| AI_AVATAR_CHAT | AI 캐릭터/아바타와 대화하는 앱 |
| GAME | 게임 추천, 자동 매칭, 아이템 추천, 게임 채팅 |
| MESSENGER | 카카오톡/메신저 대화, 사진 공유, 단체방 |
| AI_PHOTO_FILTER | 사진 보정, 얼굴 필터, AI 프로필 |
| SMARTPHONE_PHOTO | 스마트폰 사진첩, 얼굴/동물/꽃/장소 인식 |
| SEARCH_HOMEWORK | 집에서 숙제 검색, AI 답 확인 |
| FAMILY_CHOICE | 가족과 영화, 음식, 여행지, 선물 고르기 |
| SHOPPING_FOOD | 배달 앱, 쇼핑 추천, 음식 추천 |
| MAP_TRANSPORT | 길 찾기, 버스/지하철 경로 추천 |
| TRANSLATION | 번역 앱, 외국어 문장 확인 |
| VOICE_SPEAKER | 스마트 스피커, 음성 인식, 받아쓰기 |
| KIOSK_QR | 키오스크, QR 메뉴, 매장 주문 |
| HEALTH_SAFETY | 건강 정보, 안전 정보, 생활 정보 확인 |
| CREATOR_TOOL | 그림/영상/음악/글 생성 도구 |
| SCHOOL_LIMITED | 학교/수업/발표/모둠/수행평가. 미션별 10% 이하 |

서비스명은 무조건 금지하지 않습니다.
한국인에게 매우 친숙하거나 초등학생에게 유명한 앱/서비스는 사용할 수 있습니다.
단, 특정 AI 앱명이나 일시적으로 유행하는 앱명은 일반명으로 바꿉니다.

허용 예시:

- 유튜브
- 쇼츠
- 카카오톡

이 목록만 허용한다는 뜻은 아닙니다.
추가 서비스명은 `allowedServiceNames` 설정값에 넣고, 왜 허용했는지 짧은 근거를 남깁니다.

## 8. 좋은 오답 기준

나쁜 오답은 틀린 행동을 너무 직접적으로 드러냅니다.

나쁜 오답:

- AI 답을 그대로 믿어요.
- 출처를 확인하지 않아요.
- 허락 없이 친구 사진을 올려요.
- 무조건 AI가 맞다고 생각해요.

이런 오답은 개념을 몰라도 정답을 맞힐 수 있습니다.
좋은 오답은 실제 학생이 할 법한 착각이어야 합니다.

좋은 오답:

- AI보다 확실해 보이는 블로그 글 하나만 확인해요.
- 날짜보다는 출처가 중요하니 출처만 확인해요.
- 얼굴은 가렸으니 이름과 학교는 남겨도 괜찮다고 생각해요.
- 헷갈릴 수 있으니 추천 결과는 하나만 보고 골라요.

좋은 오답은 학생이 그 선택을 고를 법한 이유나 수식어를 앞에 붙입니다.

| 약한 오답 | 더 나은 오답 |
| --- | --- |
| AI 답과 비슷한 블로그 글 하나만 확인해요. | AI보다 확실해 보이는 블로그 글 하나만 확인해요. |
| 출처는 봤지만 날짜는 확인하지 않아요. | 날짜보다는 출처가 중요하니 출처만 확인해요. |
| 얼굴은 가렸지만 이름과 학교는 그대로 둬요. | 얼굴은 가렸으니 이름과 학교는 남겨도 괜찮다고 생각해요. |
| 추천 결과가 왜 나왔는지는 보지 않고 첫 번째만 골라요. | 헷갈릴 수 있으니 추천 결과는 하나만 보고 골라요. |

난이도별 오답 기준:

| 난이도 | 오답 설계 기준 |
| --- | --- |
| LOW | 쉽게 맞힐 수 있어도 됩니다. 단, 너무 말이 안 되는 오답은 넣지 않습니다. |
| MEDIUM | 정답과 헷갈릴 수 있는 그럴듯한 오답 1개를 반드시 넣습니다. |
| HIGH | 근거가 포함된 그럴듯한 오답 1개와 일반적으로 그럴듯한 오답 1개를 반드시 넣습니다. |

HIGH의 근거 포함 오답은 자연문으로 허용합니다.
단, 오답 안에 근거 단서가 1개 이상 들어가야 합니다.

근거 단서 예시:

- `비슷한 글이 여러 개 있어서`
- `친구들도 그렇게 말해서`
- `조회 수가 높아서`
- `AI가 이유를 길게 설명해서`
- `공식처럼 보이는 제목이 있어서`
- `사진이 선명해서`
- `리뷰가 많아서`

## 9. 유형별 생성 규칙

OX:

- answer와 해설 방향이 맞아야 합니다.
- LOW는 핵심 개념 하나만 묻습니다.
- MEDIUM은 생활 상황을 짧게 붙입니다.
- HIGH는 예외 조건이나 확인 기준을 포함하되 말장난으로 어렵게 만들지 않습니다.

MULTIPLE:

- 정답 1개와 오답 3개가 있어야 합니다.
- 정답은 하나만 명확해야 합니다.
- LOW는 쉬운 오답 3개도 가능하지만 말이 안 되는 오답은 금지합니다.
- MEDIUM은 그럴듯한 오답 1개와 쉬운 오답 2개로 구성합니다.
- HIGH는 근거가 포함된 그럴듯한 오답 1개, 일반 그럴듯한 오답 1개, 쉬운 오답 1개로 구성합니다.

FILL:

- 가장 검수가 어렵습니다.
- 정답 단어가 빈칸에 문법적으로 자연스럽게 들어가야 합니다.
- 오답도 문법적으로는 들어갈 수 있어야 하지만 의미상 정답은 아니어야 합니다.
- `휴식`, `충전`, `색깔`, `소리`처럼 너무 쉽게 배제되는 오답은 실패입니다.
- FILL은 품질을 위해 적게 만들어도 됩니다.

SITUATION:

- 실제 생활 맥락이어야 합니다.
- 상황과 AI 기능이 자연스럽게 연결되어야 합니다.
- 학교/모둠/발표 상황은 각 미션의 10%를 넘으면 실패입니다.
- 상황이 없어도 이해 가능한 문항은 억지로 상황을 붙이지 않습니다.

## 10. 자동 검수 규칙

구조 검사:

- 총 960문항인지
- 3챕터인지
- 16미션인지
- 미션당 60문항인지
- missionCode와 missionTitle이 현재 미션 구성과 맞는지
- 유형 분포가 권장 범위 안에 있는지
- 난이도 분포가 한쪽으로 치우치지 않았는지
- packNo 분포가 맞는지
- externalId 중복이 없는지
- answer 인덱스가 options 범위를 벗어나지 않는지

정답/해설 검사:

- OX answer와 해설 방향이 맞는지
- FILL answer 인덱스가 실제 정답 옵션을 가리키는지
- MULTIPLE/SITUATION 정답이 하나로 명확한지
- 해설이 정답 이유를 설명하는지

선택지 품질 검사:

- `무조건`, `항상`, `절대`, `모두`, `완벽`, `그대로 믿어요`, `확인하지 않아요`, `모른 척해요`, `허락 없이`, `숨겨요`, `장난`, `필요 없어요`, `상관없어요` 같은 표현이 반복되면 재생성합니다.
- 같은 선택지 문장이 5회 이상 반복되면 실패입니다.
- same-mission duplicate가 1건이라도 있으면 실패입니다.
- LOW 문항에 어려운 단어가 3개 이상 겹치면 재작성합니다.

챕터 경계 검사:

- Ch1 문항에 안전/출처/프롬프트 기술이 중심으로 들어가면 경고입니다.
- Ch2 문항이 좋은 질문법 중심이면 Ch3로 이동합니다.
- Ch3 문항이 출처/근거 판단 중심이면 Ch2로 이동합니다.
- Ch2와 Ch3 사이에 같은 문장틀이 반복되면 template repeat로 잡습니다.

## 11. LLM Judge

자동 validator로 먼저 거르고, 위험 문항만 LLM Judge를 돌립니다.
권장 기본값은 HIGH 문항 전체, FILL 문항 전체, validator 경고 문항 전체입니다.

LLM Judge 대상:

- validator 경고 문항
- FILL 문항 중 정답과 오답이 의미적으로 가까운 문항
- HIGH 문항
- 같은 미션 내 template repeat 후보
- Ch2/Ch3 경계가 애매한 문항
- repeated option 후보
- 정답 길이 편향 후보
- 학교/수업 맥락 후보

Judge 질문:

```text
아래 문항을 초등학생용 AI 리터러시 문제로 검수해 주세요.

판정은 PASS / REWRITE / MOVE / DROP 중 하나로만 내려 주세요.

검수 기준:
1. 정답이 하나로 명확한가?
2. 오답 중 정답처럼 보이는 것이 있는가?
3. 개념을 몰라도 나쁜 말만 피해서 맞힐 수 있는가?
4. 현재 missionTitle과 실제 문항 목표가 맞는가?
5. Ch2/Ch3 경계가 맞는가?
6. 상황이 실제 생활 맥락으로 자연스러운가?
7. 난이도별 오답 기준을 만족하는가?

문항:
...
```

판정 기준:

- PASS: 그대로 사용 가능
- REWRITE: 같은 blueprint로 다시 생성
- MOVE: 문항 목표는 괜찮지만 다른 미션으로 이동해야 함
- DROP: blueprint 자체를 바꿔야 함

## 12. 구현 흐름

1. 현재 미션 구성 테이블을 코드 상수로 둡니다.
2. 미션별 targetSkill 목록을 만듭니다.
3. 미션별 contextCategory 예산을 만듭니다.
4. pack 단위로 blueprint를 생성합니다.
5. blueprint가 현재 미션 구성과 맞는지 검증합니다.
6. 검증된 blueprint만 문제로 생성합니다.
7. deterministic validator를 실행합니다.
8. 위험 문항만 LLM Judge로 보냅니다.
9. 실패 문항은 같은 blueprint 또는 수정된 blueprint로 재생성합니다.
10. 전체 bank 검증 후 통과본만 백엔드에 반영합니다.

## 13. 출시 차단 조건

아래 중 하나라도 있으면 백엔드 반영을 막습니다.

- 총 문항 수가 960이 아님
- 챕터 수가 3이 아님
- 미션 수가 16이 아님
- 미션당 문항 수가 60이 아님
- missionCode와 missionTitle이 현재 미션 구성과 다름
- answer 인덱스 오류 1건 이상
- OX 정답/해설 불일치 1건 이상
- same-mission duplicate 1건 이상
- 정답처럼 보이는 오답 1건 이상
- 같은 선택지 문장 5회 이상 반복
- P0 정답 오류 1건 이상
- 미션별 학교/수업 맥락 10% 초과
- 미션별 생활 맥락 90% 미만
- MEDIUM 문항에 그럴듯한 오답 1개가 없음
- HIGH 문항에 근거 있는 그럴듯한 오답 1개와 일반 그럴듯한 오답 1개가 없음
- 경고 총량 50건 초과
- LOW 어휘 부담 후보 30건 초과

## 14. 최종 원칙

가장 중요한 원칙은 다음 4개입니다.

1. 현재 미션 구성과 맞지 않는 문항은 억지로 남기지 않습니다.
2. 문제를 바로 만들지 말고 blueprint부터 만듭니다.
3. 난이도별로 오답의 그럴듯함 기준을 다르게 둡니다.
4. 자동 validator로 먼저 거르고, 위험 문항만 LLM Judge를 돌립니다.

이 구조를 만들면 문제를 수정할수록 품질이 떨어지는 상황을 줄일 수 있습니다.
수동 수정은 마지막 보정 단계로만 사용하고, 기본 품질은 생성 시스템 안에서 보장해야 합니다.

## 15. 구현자가 만들어야 할 최종 산출물

이 문서는 실제 코드 구현자가 그대로 따라가는 실행 가이드입니다.
최종 구현은 아래 8개 산출물을 만들어야 합니다.

| 산출물 | 목적 | 실패하면 생기는 문제 |
| --- | --- | --- |
| rich 문제 JSON | 문제 품질을 만들고 검수하기 위한 원본 데이터 | 문제 의도, 오개념, 생활 맥락, 검수 근거가 사라짐 |
| backend-compatible JSON | rich 문제 JSON에서 백엔드 반영 필드만 정규화한 변환본 | seed SQL 변환 단계에서 필드 누락이나 명칭 불일치가 생김 |
| seed SQL | 백엔드 DB에 반영할 실행 파일 | 앱에서 미션/문항을 불러오지 못함 |
| validator | 구조, 정답, 중복, 품질 기준 자동 검사 | 정답 오류와 뻔한 오답이 그대로 출시됨 |
| 프롬프트 | OpenAI API로 blueprint와 문제를 생성하는 입력 계약 | 생성할 때마다 말투와 품질이 달라짐 |
| 검수 리포트 | 실패 문항, 경고 문항, 재생성 대상을 구현자가 확인 | 어떤 문항을 고쳐야 하는지 추적 불가 |
| HTML 리뷰 파일 | 사람이 마지막으로 빠르게 훑는 검수 화면 | JSON만 보고는 아이 눈높이와 어색한 문장을 놓침 |
| adapter/exporter | rich JSON을 백엔드 seed SQL로 바꾸는 변환기 | 문제는 좋아도 DB 스키마와 맞지 않아 반영 실패 |

권장 파일 흐름:

```text
mission-config.json
-> blueprints.json
-> generated-question-bank.rich.json
-> validation-report.json
-> regeneration-queue.json
-> final-question-bank.rich.json
-> backend-compatible-question-bank.json
-> question-bank-seed.sql
-> question-bank-review.html
-> release-summary.md
```

구현자는 중간 산출물을 모두 남깁니다.
특히 `blueprints.json`, `validation-report.json`, `regeneration-queue.json`은 문제 품질이 왜 좋아졌는지 설명하는 근거가 됩니다.
`final-question-bank.rich.json`은 문제 품질의 최종 정본이고, `question-bank-seed.sql`은 백엔드 반영의 최종 정본입니다.
두 파일 사이의 변환 규칙은 adapter/exporter에서 고정합니다.

### 15-1. mission-config.json 확정 계약

문제 생성은 `문제은행/26-06-04/mission-config.json`을 기준으로 시작합니다.
이 파일은 프롬프트에 매번 넣을 설정이 아니라, 생성 파이프라인 전체가 지켜야 하는 고정 계약입니다.

확정값:

| 항목 | 값 |
| --- | --- |
| configVersion | `v1.0` |
| guideVersion | `backend-question-generation-system-guide v1.4` |
| 총 문항 수 | 960 |
| 총 미션 수 | 16 |
| 미션별 문항 수 | 60 |
| 유형 분포 | OX 192 / MULTIPLE 288 / FILL 96 / SITUATION 384 |
| 난이도 분포 | LOW 384 / MEDIUM 320 / HIGH 256 |
| 미션별 pack 분포 | P1 10 / P2 10 / P3 10 / P4 10 / P5 10 / P6 10 |
| 허용 contentTags | FACT / PRIVACY / PROMPT / SAFETY / VERIFICATION |
| 학교/수업 맥락 제한 | 미션당 최대 6문항, 10% 이하 |

생성/검수 마일스톤:

| 단계 | 문항 수 | 기준 | 처리 |
| --- | ---: | --- | --- |
| 1차 중간본 | 480 | 8미션 또는 16미션의 절반 분량 | validator, FILL 집중 검수, 미션 경계 중복 확인 |
| 2차 최종 생성본 | 960 | 16미션 x 60문항 | 전체 validator, LLM Judge, HTML 리뷰, adapter/exporter 실행 |

백엔드에 반영하는 최종본은 960문항입니다.
480문항은 중간 품질 확인용 산출물이며, seed SQL 최종 반영 대상이 아닙니다.
480문항 생성에는 `문제은행/26-06-04/mission-config-480.json`을 사용하고, 960문항 최종 생성에는 `문제은행/26-06-04/mission-config.json`을 사용합니다.

참고 자료:

- `초등 교사를 위한 KERIS와 시작하는 인공지능 교육 1.pdf`
- `초등 교사를 위한 KERIS와 시작하는 인공지능 교육 2.pdf`
- `[GM 2024-05] 생성형 AI를 활용한 교수학습 운영 가이드_f.pdf`
- `[별책본] 디지털 리터러시 구성 체계 및 교과별 성취기준 연계.pdf`
- `2021년 인공지능(AI)기본 역량 강화 연수 교재(초등).pdf`

FILL 정책:

- FILL은 초기 128문항으로 시작합니다.
- FILL validator에서 문법 애매함, 복수 정답 가능성, 오답 부자연스러움이 반복되면 더 줄입니다.
- 줄인 수량은 MULTIPLE 또는 SITUATION으로 이동합니다.
- FILL의 복수 정답 배열은 꼭 필요한 경우만 허용하고, 전부 LLM Judge 대상으로 보냅니다.

미션별 주 타겟 스킬:

| missionCode | missionTitle | 주 타겟 스킬 |
| --- | --- | --- |
| S0101 | 우리 주변의 AI 찾아보기 | 생활 속 도구에서 AI가 하는 일을 기능 중심으로 설명한다 |
| S0102 | AI가 자료로 배우는 과정 알기 | AI가 자료와 예시를 보고 패턴을 배운다는 점을 설명한다 |
| S0103 | AI가 잘하는 일과 어려워하는 일 구분하기 | AI가 반복 계산, 분류, 추천, 요약을 빠르게 할 수 있음을 안다 |
| S0104 | AI가 여러 정보를 알아보는 방법 알기 | AI가 사진, 소리, 글, 영상에서 특징을 찾아 구분할 수 있음을 안다 |
| S0105 | AI와 사람이 할 일 구분하기 | AI가 자동으로 도와줄 수 있는 일을 생활 사례로 설명한다 |
| S0201 | 개인정보를 안전하게 다루기 | 개인정보와 생체정보의 예를 생활 속에서 찾는다 |
| S0202 | 다른 사람의 정보를 조심해서 다루기 | 다른 사람의 개인정보와 생체정보도 보호해야 함을 안다 |
| S0203 | AI 답이 맞는지 확인하기 | AI 답이 틀릴 수 있음을 생활 사례로 설명한다 |
| S0204 | 출처와 근거를 비교하기 | 출처, 작성자, 날짜, 근거를 확인해야 하는 이유를 설명한다 |
| S0205 | AI 결과가 치우쳤는지 살펴보기 | 데이터가 한쪽으로 치우치면 AI 결과도 치우칠 수 있음을 설명한다 |
| S0206 | AI의 좋은 점과 조심할 점 생각하기 | AI가 생활을 편리하게 만드는 장점을 설명한다 |
| S0301 | AI에게 원하는 것을 분명히 말하기 | 질문하기 전에 내가 원하는 목적을 분명히 정한다 |
| S0302 | 원하는 답 형식을 요청하기 | 필요한 답 형식을 상황에 맞게 고른다 |
| S0303 | 조건을 넣어 다시 질문하기 | AI 답이 부족하거나 너무 넓을 때 다시 질문해야 함을 안다 |
| S0304 | AI 답을 비교하고 고치기 | AI 답 여러 개를 목적, 정확성, 쉬운 표현 기준으로 비교한다 |
| S0305 | AI 도움을 내 말로 정리하기 | AI 답을 그대로 제출하거나 보내지 않고 내 말로 바꾼다 |

중복 방지 규칙:

- `missionBoundaryPolicy`는 각 미션의 주 초점을 고정합니다.
- 안전, 검증, 개인정보, 프롬프트는 서로 관련될 수 있지만 정답의 핵심 초점은 해당 미션의 `primaryFocus`를 따라야 합니다.
- 예를 들어 S0203은 "AI 답이 맞는지 확인하기"가 핵심이고, S0204처럼 출처/작성자/날짜를 비교하는 문제로 넘어가면 안 됩니다.
- 예를 들어 S0303은 "조건을 넣어 다시 질문하기"가 핵심이고, S0305처럼 AI 답을 내 말로 바꾸는 문제로 넘어가면 안 됩니다.

## 16. 정본 미션 매핑 고정 규칙

문제 생성 코드의 기준은 이 문서 4번의 현재 미션 구성입니다.
기존 seed SQL, 예전 JSON, 이전 기획 문서에 다른 미션명이 남아 있어도 이 문서 4번 표를 최종 정본으로 사용합니다.

구현 규칙:

1. `missionCode`는 바꾸지 않습니다.
2. `missionTitle`, `chapterTitle`, `targetSkill`, `missionSummary`는 이 문서 기준으로 맞춥니다.
3. 기존 산출물에 예전 미션명이 있으면 새 문제 생성 전에 매핑을 교정합니다.
4. 미션명이 다른 상태로 seed SQL을 만들면 출시 차단입니다.

기존 산출물에서 아래 표현이 보이면 교정합니다.

| 코드 | 기존 산출물에서 보일 수 있는 표현 | 이 문서 기준 정본 |
| --- | --- | --- |
| S0101 | 우리 주변의 AI 찾기 | 우리 주변의 AI 찾아보기 |
| S0206 | AI 도움을 내 말로 정리하기 | AI의 좋은 점과 조심할 점 생각하기 |
| S0305 | 생활 속 공정한 AI 사용 | AI 도움을 내 말로 정리하기 |

주의할 점:

- 위 표는 현재 확인된 대표 불일치입니다.
- 구현자는 전체 `S0101`부터 `S0305`까지 모두 4번 표와 비교해야 합니다.
- 미션 제목만 바꾸면 안 됩니다. 해당 미션의 문제 목표, 해설, contentTags, sourceReference까지 함께 맞춰야 합니다.

## 17. 최종 문제 JSON 계약

최종 생성물은 처음부터 백엔드 DB 형식으로 납작하게 만들지 않습니다.
문제는 `targetSkill`, `contextCategory`, `misconceptions`, `correctReason`처럼 품질을 만드는 필드를 가진 rich JSON으로 생성합니다.
다만 rich JSON 안에는 백엔드 변환에 필요한 필드도 처음부터 반드시 포함합니다.

즉, 구현 흐름은 다음 원칙을 따릅니다.

```text
품질 생성/검수: rich JSON
백엔드 반영: rich JSON -> backend-compatible JSON -> seed SQL
```

rich JSON 루트는 `missions`와 `questions`를 함께 가집니다.
`missions`는 seed SQL에서 `public.missions`, `public.mission_sets`를 만들기 위한 입력입니다.
`questions`는 seed SQL에서 `public.question_bank`, `private.question_answer_keys`를 만들기 위한 입력입니다.

루트 예시:

```json
{
  "generationVersion": "v1.4",
  "totalQuestionCount": 960,
  "totalMissionCount": 16,
  "questionsPerMission": 60,
  "missions": [
    {
      "missionCode": "S0303",
      "stage": 3,
      "chapterTitle": "Ch3 AI에게 잘 질문하고 활용하기",
      "missionTitle": "조건을 넣어 다시 질문하기",
      "missionSummary": "AI 답이 부족할 때 조건을 추가해 다시 질문하는 방법을 익힌다."
    }
  ],
  "questions": []
}
```

아래 필드는 문항마다 반드시 들어갑니다.

```json
{
  "externalId": "S0303-P4-06",
  "missionCode": "S0303",
  "stage": 3,
  "chapterTitle": "Ch3 AI에게 잘 질문하고 활용하기",
  "missionTitle": "조건을 넣어 다시 질문하기",
  "packNo": 4,
  "type": "SITUATION",
  "difficulty": "MEDIUM",
  "question": "가족 여행 준비물을 AI에게 물었는데 답이 너무 넓게 나왔어요. 다시 질문하는 방법으로 가장 알맞은 것은?",
  "options": [
    "초등학생 가족 여행이라는 조건과 원하는 형식을 함께 말해요.",
    "AI가 처음 준 답을 그대로 사용해요.",
    "답이 길어질 수 있으니 조건을 빼고 다시 물어요.",
    "여행지는 말하지 않고 준비물만 다시 물어요."
  ],
  "answer": 0,
  "explanation": "조건을 넣어 다시 질문하면 상황에 맞는 답을 받을 가능성이 높아져요.",
  "targetSkill": "AI 답이 부족할 때 조건을 추가해 다시 질문한다",
  "contextCategory": "FAMILY_CHOICE",
  "contentTags": ["PROMPTING", "REVISION"],
  "curriculumRef": "백엔드용 문제은행 생성 시스템 가이드 v1.4",
  "sourceType": "GPT",
  "generationPhase": "PREGENERATED",
  "sourceReference": "백엔드용 문제은행 생성 시스템 가이드 v1.4",
  "termHints": []
}
```

정답 형식:

| 유형 | options | answer |
| --- | --- | --- |
| OX | `null` | `true` 또는 `false` |
| MULTIPLE | 문자열 4개 배열 | 정답 options의 0-base 인덱스 |
| SITUATION | 문자열 4개 배열 | 정답 options의 0-base 인덱스 |
| FILL | 문자열 4개 배열 | 정답 options 인덱스 배열. 예: `[2]` |

공통 규칙:

- `externalId` 형식은 `S0101-P1-01`처럼 유지합니다.
- `packNo`는 `P1`이면 `1`, `P6`이면 `6`입니다.
- MULTIPLE과 SITUATION의 정답은 반드시 하나입니다.
- FILL도 기본은 정답 1개만 둡니다. 복수 정답이 꼭 필요하면 `[1, 3]`처럼 배열로 표현하되 LLM Judge 대상에 넣습니다.
- `question`, `options`, `explanation`에는 내부 구현 용어를 넣지 않습니다. 예: blueprint, validator, LLM Judge.
- `curriculumRef`는 백엔드 DB의 `curriculum_ref` 컬럼으로 들어가므로 반드시 둡니다.
- `sourceReference`는 검수/추적용 메타데이터입니다. 백엔드에 직접 들어가는 필드는 `curriculumRef`입니다.
- `chapterTitle`, `targetSkill`, `contextCategory`, `termHints`는 문제 품질과 리뷰를 위한 rich JSON 필드입니다. 현재 seed SQL 변환에서는 DB에 직접 넣지 않더라도 삭제하지 않습니다.

### 17-1. 백엔드 변환 계약

백엔드 반영은 rich JSON을 그대로 DB에 넣는 방식이 아닙니다.
adapter/exporter가 rich JSON에서 백엔드가 쓰는 필드만 꺼내 seed SQL을 만듭니다.

현재 구현 파일:

- `문제은행/26-06-04/export_question_bank.py`
- 입력: `final-question-bank.rich.json`, `mission-config.json`
- 출력: `backend-compatible-question-bank.json`, `question-bank-seed.sql`, `adapter-smoke-report.json`

변환 규칙:

| rich JSON | 백엔드 반영 위치 |
| --- | --- |
| `missions[].missionCode` | `public.missions.mission_code`, `public.mission_sets.mission_code`, deterministic UUID seed |
| `missions[].stage` | `public.missions.stage`, `public.mission_sets.stage` |
| `missions[].missionTitle` | `public.missions.title`, `public.mission_sets.title` |
| `missions[].missionSummary` | `public.missions.description`, `public.mission_sets.description` |
| `questions[].externalId` | `public.question_bank.id` deterministic UUID seed |
| `questions[].missionCode` | `mission_id` 매핑 기준 |
| `questions[].packNo` | `public.question_bank.pack_no` |
| `questions[].type` | `public.question_bank.question_type` |
| `questions[].difficulty` | `public.question_bank.difficulty` |
| `questions[].question` | `public.question_bank.prompt` |
| `questions[].options` | `public.question_bank.options` |
| `questions[].contentTags` | `public.question_bank.content_tags` |
| `questions[].curriculumRef` | `public.question_bank.curriculum_ref` |
| `questions[].sourceType` | `public.question_bank.source_type` |
| `questions[].generationPhase` | `public.question_bank.generation_phase` |
| `questions[].answer` | `private.question_answer_keys.answer_payload` |
| `questions[].explanation` | `private.question_answer_keys.explanation` |

정답 인덱스 변환:

- rich JSON의 MULTIPLE/SITUATION `answer`는 0-base 숫자입니다.
- rich JSON의 FILL `answer`는 0-base 숫자 배열입니다.
- seed SQL의 `answer_payload`는 백엔드 채점 로직에 맞게 1-base로 변환합니다.
- OX는 `true` 또는 `false`를 그대로 유지합니다.

출시 차단 조건:

- rich JSON에는 있는데 backend-compatible JSON 또는 seed SQL에 필요한 필드가 빠지면 출시 차단입니다.
- `curriculumRef`가 없거나 빈 문자열이면 출시 차단입니다.
- seed SQL 생성 후 `public.question_bank` 문항 수와 `private.question_answer_keys` 정답 수가 다르면 출시 차단입니다.
- 생성 JSON의 0-base 정답과 seed SQL의 1-base `answer_payload`가 서로 맞지 않으면 출시 차단입니다.

## 18. OpenAI API 생성 흐름

OpenAI API는 한 번에 최종 문제를 만들기보다 두 번 나누어 호출합니다.

```text
1차 호출: blueprint 생성
2차 호출: 검증된 blueprint로 문제 생성
```

이렇게 나누는 이유는 문제 문장을 바로 만들면 모델이 자주 쓰는 쉬운 틀로 돌아가기 때문입니다.
blueprint 단계에서 `targetSkill`, `studentContext`, `misconceptions`, `contextCategory`를 먼저 고정해야 오답과 상황이 다양해집니다.

### 18-1. Blueprint 생성 프롬프트

```text
너는 초등학생용 AI 리터러시 문제은행 설계자다.

목표:
- 아래 미션에 맞는 문제 blueprint를 만든다.
- 아직 실제 문제 문장과 선택지는 만들지 않는다.
- 같은 미션 안에서 상황, 오개념, 정답 이유가 반복되지 않게 한다.

고정 입력:
- missionCode: {{missionCode}}
- chapterTitle: {{chapterTitle}}
- missionTitle: {{missionTitle}}
- coreScope: {{coreScope}}
- packNo: {{packNo}}
- requiredCount: {{count}}
- allowedTypes: {{allowedTypes}}
- difficultyPlan: {{difficultyPlan}}
- contextBudget: {{contextBudget}}

반드시 지킬 기준:
1. 이 문서의 4번 미션 구성을 정본으로 사용한다.
2. 생활 맥락을 우선 사용한다.
3. 학교/수업 맥락은 같은 미션 안에서 10%를 넘지 않는다.
4. Ch2는 확인, 비교, 판단, 조심하기 중심이다.
5. Ch3는 요청, 조건 추가, 다시 질문, 고치기, 내 말로 정리 중심이다.
6. `그대로 믿어요`, `확인하지 않아요`, `무조건`, `항상` 같은 뻔한 오답 패턴을 피한다.

출력:
JSON 배열만 출력한다.
각 객체는 externalId, missionCode, chapterTitle, missionTitle, type, difficulty, targetSkill, studentContext, correctReason, misconceptions, contextCategory, forbiddenPatterns를 가진다.
```

### 18-2. 문제 생성 프롬프트

```text
너는 초등학생용 AI 리터러시 문제 출제자다.

아래 blueprint를 실제 문제로 바꾼다.

생성 기준:
1. 초등학생이 읽을 수 있는 짧고 자연스러운 한국어로 쓴다.
2. 정답은 하나로 명확해야 한다.
3. 오답은 말이 안 되는 행동이 아니라 실제 학생이 헷갈릴 법한 착각으로 만든다.
4. MEDIUM은 그럴듯한 오답 1개를 반드시 포함한다.
5. HIGH는 근거 있는 그럴듯한 오답 1개와 일반 그럴듯한 오답 1개를 포함한다.
6. FILL은 빈칸에 정답과 오답이 모두 문법적으로 들어갈 수 있어야 한다.
7. 해설은 정답 이유를 한두 문장으로 설명한다.

금지:
- 정답을 options 중 가장 길거나 가장 착하게만 만들기
- `무조건`, `항상`, `그대로 믿어요`, `확인하지 않아요` 같은 쉬운 단서 반복
- 학교 발표, 모둠 활동, 수행평가 상황 과다 사용
- 미션 목표와 다른 Ch2/Ch3 개념 섞기

입력 blueprint:
{{blueprintJson}}

출력:
rich 문제 JSON 객체만 출력한다.
```

### 18-3. 실패 문항 재생성 프롬프트

```text
아래 문항은 validator 또는 LLM Judge에서 실패했다.

실패 코드:
{{issueCodes}}

실패 이유:
{{issueReasons}}

원래 blueprint:
{{blueprintJson}}

원래 문항:
{{questionJson}}

수정 지시:
1. missionCode, missionTitle, type, difficulty, packNo는 유지한다.
2. 실패 이유를 직접 해결한다.
3. 같은 표현을 살짝 바꾸는 수준이 아니라, 오답의 착각 이유와 생활 상황을 다시 설계한다.
4. 정답 형식은 기존 rich JSON 계약을 따른다.

출력:
수정된 rich 문제 JSON 객체만 출력한다.
```

## 19. Validator 리포트 형식

validator는 사람이 바로 고칠 수 있게 JSON과 Markdown 두 가지 리포트를 만듭니다.

JSON 리포트 예시:

```json
{
  "verdict": "FAIL",
  "totalQuestions": 960,
  "blockingIssueCount": 2,
  "warningCount": 37,
  "issues": [
    {
      "severity": "P0",
      "code": "ANSWER_INDEX_OUT_OF_RANGE",
      "externalId": "S0203-P2-04",
      "missionCode": "S0203",
      "message": "answer가 options 범위를 벗어났습니다.",
      "action": "정답 인덱스를 수정하거나 문항을 재생성합니다."
    }
  ],
  "summaryByCode": {
    "OBVIOUS_DISTRACTOR": 18,
    "TEMPLATE_REPEAT": 11,
    "SCHOOL_CONTEXT_OVERUSE": 8
  }
}
```

Markdown 리포트는 아래 순서로 씁니다.

```text
# 문제은행 검수 리포트

## 결론
- PASS / WARN / FAIL
- 출시 차단 여부

## P0 출시 차단
- externalId, issueCode, 이유, 권장 조치

## P1 재생성 권장
- 뻔한 오답
- 정답처럼 보이는 오답
- 미션 경계 오류

## P2 수동 검수 권장
- 어색한 생활 맥락
- LOW 어휘 부담
- template repeat 후보

## 미션별 요약
- S0101: 통과 n건, 경고 n건, 실패 n건

## 재생성 큐
- 같은 blueprint 재생성 대상
- blueprint 수정 후 재생성 대상
- DROP 대상
```

issueCode는 최소한 아래 값을 사용합니다.

| 코드 | 의미 | 기본 조치 |
| --- | --- | --- |
| STRUCTURE_COUNT_MISMATCH | 총 문항/미션/팩 수 불일치 | 생성 중단 |
| MISSION_MAPPING_MISMATCH | missionCode와 missionTitle 불일치 | 정본 매핑으로 수정 |
| ANSWER_INDEX_OUT_OF_RANGE | answer가 options 범위 밖 | 즉시 수정 |
| OX_EXPLANATION_CONFLICT | OX 정답과 해설 방향 충돌 | 재생성 |
| AMBIGUOUS_CORRECT_ANSWER | 정답이 2개 이상처럼 보임 | 재생성 |
| OBVIOUS_DISTRACTOR | 너무 뻔한 오답 | 오답 재작성 |
| WEAK_FILL_DISTRACTOR | FILL 오답이 문법/의미상 너무 쉽게 배제됨 | FILL 재작성 |
| TEMPLATE_REPEAT | 같은 미션 안 문장틀 반복 | blueprint 또는 문항 재생성 |
| CHAPTER_BOUNDARY_MISMATCH | Ch2/Ch3 역할 혼합 | MOVE 또는 재생성 |
| SCHOOL_CONTEXT_OVERUSE | 학교/수업 맥락 10% 초과 | 생활 맥락으로 재작성 |
| LOW_VOCABULARY_BURDEN | LOW 문항 어휘 부담 | 문장 단순화 |

## 20. 재생성 정책

실패 문항은 아무 기준 없이 다시 만들지 않습니다.
실패 이유에 따라 같은 blueprint를 유지할지, blueprint 자체를 버릴지 결정합니다.

| 판정 | 언제 사용 | 처리 |
| --- | --- | --- |
| PASS | 그대로 사용 가능 | final rich JSON에 포함 |
| REWRITE_SAME_BLUEPRINT | 문항 표현, 오답, 해설만 문제 | 같은 blueprint로 1회 재생성 |
| REWRITE_BLUEPRINT | targetSkill, 상황, 오개념 설계가 약함 | blueprint 수정 후 재생성 |
| MOVE | 목표는 괜찮지만 미션이 다름 | 정본 미션으로 이동 후 재검수 |
| DROP | 목표 자체가 교육 흐름과 맞지 않음 | 새 blueprint 생성 |
| MANUAL_REVIEW | 자동 판단이 애매함 | HTML 리뷰 파일에서 사람이 확인 |

재시도 제한:

- 같은 blueprint 재생성은 최대 2회까지만 합니다.
- 2회 재생성 후에도 같은 issueCode가 나오면 `MANUAL_REVIEW`로 보냅니다.
- P0 오류는 수동 수정으로 덮어쓰지 말고 원인과 수정 내역을 리포트에 남깁니다.

## 21. HTML 리뷰 파일 요구사항

HTML 리뷰 파일은 개발자가 보기 위한 예쁜 페이지가 아니라, 사람이 빠르게 문제 품질을 확인하는 검수 도구입니다.

필수 기능:

- 미션, packNo, 유형, 난이도, issueCode 필터
- P0/P1/P2 심각도 필터
- 문제 있음 표시
- 검수 메모 입력
- JSON/CSV export
- issue가 있는 문항만 보기
- 같은 미션 안 template repeat 후보 묶어 보기

리뷰 카드에 보여야 하는 정보:

- `externalId`
- `missionCode`
- `missionTitle`
- `packNo`
- `type`
- `difficulty`
- `question`
- `options`
- `answer`
- `explanation`
- `issueCodes`
- `validator message`
- `review memo`

성능 기준:

- 960문항 전체를 매번 다시 렌더링하지 않습니다.
- 필터 변경, 체크박스 클릭, 메모 입력 때는 필요한 카드만 갱신합니다.
- localStorage에 저장하되, 최종 공유는 export 파일로 합니다.

## 22. 구현 체크리스트

구현자는 아래 순서대로 작업합니다.

1. 4번 미션 구성을 코드 상수 또는 JSON 설정으로 만든다.
2. 기존 seed/JSON의 미션명과 정본 미션명을 비교하는 검사를 만든다.
3. 미션별 `targetSkill` 목록을 만든다.
4. 미션별 `contextCategory` 예산을 만든다.
5. blueprint 생성 프롬프트를 만든다.
6. blueprint validator를 먼저 만든다.
7. 문제 생성 프롬프트를 만든다.
8. rich 문제 JSON validator를 만든다.
9. 실패 문항 재생성 큐를 만든다.
10. LLM Judge는 HIGH, FILL, validator 경고 문항부터 적용한다.
11. rich JSON을 backend-compatible JSON으로 변환하는 adapter/exporter를 만든다.
12. backend-compatible JSON만 seed SQL로 변환한다.
13. seed SQL과 rich JSON의 문항 수, 정답 수, missionCode, packNo, answer 변환을 대조한다.
14. 검수 리포트와 HTML 리뷰 파일을 함께 만든다.
15. 출시 차단 조건이 0건인지 확인한다.
16. 통과본의 rich JSON, backend-compatible JSON, SQL, 리포트, HTML을 같은 버전명으로 묶어 남긴다.

완료 기준:

- final rich JSON 총 문항 수가 960입니다.
- missionCode와 missionTitle이 이 문서 4번 표와 모두 일치합니다.
- answer 오류가 0건입니다.
- P0 오류가 0건입니다.
- same-mission duplicate가 0건입니다.
- 미션별 학교/수업 맥락이 10% 이하입니다.
- validator 리포트와 HTML 리뷰 파일이 함께 생성됩니다.
- seed SQL은 backend-compatible JSON에서만 만들어집니다.
- seed SQL의 `question_bank` 문항 수와 `question_answer_keys` 정답 수가 각각 960입니다.
- rich JSON의 0-base 정답이 seed SQL의 1-base `answer_payload`로 정확히 변환됩니다.

## 23. 실제 구현 시 추가 고려사항

이 생성기는 실시간 서비스 기능이 아니라, 로컬에서 한 번 돌려 문제은행을 만드는 배치 스크립트입니다.
따라서 빠른 응답보다 재현성, 중단 후 재개, 품질 검수, seed SQL 안전성이 더 중요합니다.

로컬 문서 제목:

- `백엔드용 문제은행 생성 시스템 가이드`

로컬 문서 파일:

- `docs/backend-question-generation-system-guide.md` (이 문서)

### 23-1. 생성 단위

OpenAI API 호출은 10문항씩 묶어서 실행합니다.

권장 단위:

```text
missionCode + packNo + batchNo
예: S0303-P4-B1 = S0303의 P4 안에서 10문항 생성
```

10개씩 묶는 이유:

- 한 번에 너무 많이 만들면 같은 문장틀이 반복되기 쉽습니다.
- 한 번에 1개씩 만들면 비용과 시간이 커지고 미션 전체 균형을 보기 어렵습니다.
- 10개 단위면 중간 실패 시 해당 batch만 다시 돌리기 쉽습니다.

batch마다 아래 메타데이터를 남깁니다.

```json
{
  "generationRunId": "2026-06-05-questionbank-v1.5",
  "missionCode": "S0303",
  "packNo": 4,
  "batchNo": 1,
  "requestedCount": 10,
  "model": "사용한 모델명",
  "temperature": 0.4,
  "promptVersion": "prompt-v1.5",
  "missionConfigVersion": "mission-config-v1.5",
  "inputHash": "...",
  "outputHash": "...",
  "status": "PASS"
}
```

### 23-2. PASS 문항 잠금

한 번 PASS 된 문항은 다음 생성 때 기본적으로 유지합니다.
좋은 문항을 계속 갈아엎으면 문제은행 품질이 안정되지 않습니다.

문항 상태는 최소한 아래처럼 관리합니다.

| 상태 | 의미 | 다음 실행 때 처리 |
| --- | --- | --- |
| PASS_LOCKED | validator와 사람 검수를 통과해 잠긴 문항 | 재생성하지 않음 |
| PASS_AUTO | validator는 통과했지만 사람 검수 전 문항 | HTML 리뷰 대상으로 표시 |
| REWRITE | 같은 blueprint로 재생성 | 해당 문항만 재생성 |
| REBLUEPRINT | blueprint부터 다시 작성 | blueprint와 문항 모두 재생성 |
| MANUAL_REVIEW | 자동 판단이 애매함 | 사람이 HTML에서 확인 |
| DROP | 버리고 새 문항으로 대체 | externalId는 유지하고 내용만 교체 |

잠금 규칙:

- `PASS_LOCKED` 문항은 프롬프트가 바뀌어도 자동 재생성하지 않습니다.
- 미션 구성, 정답 형식, seed 변환 계약이 바뀐 경우에만 잠금 해제를 검토합니다.
- 잠금 해제 시 `unlockReason`을 리포트에 남깁니다.

### 23-3. seed SQL 자동 생성 조건

사용자가 정한 기준은 `validator PASS면 자동 seed 생성`입니다.
다만 여기서 PASS는 단순 구조 PASS가 아니라 아래 조건을 모두 만족해야 합니다.

자동 seed 생성 조건:

- final rich JSON 총 문항 수가 960입니다.
- backend-compatible JSON 변환이 성공합니다.
- answer 오류가 0건입니다.
- P0 오류가 0건입니다.
- `MISSION_MAPPING_MISMATCH`가 0건입니다.
- same-mission duplicate가 0건입니다.
- `OBVIOUS_DISTRACTOR`가 출시 차단 기준 이하입니다.
- `LOW_VOCABULARY_BURDEN`가 출시 차단 기준 이하입니다.
- `SCHOOL_CONTEXT_OVERUSE`가 0건입니다.
- seed SQL의 `question_bank` 문항 수와 `question_answer_keys` 정답 수가 각각 960입니다.
- rich JSON의 0-base 정답이 seed SQL의 1-base `answer_payload`로 정확히 변환됩니다.

자동 seed 생성 후에도 HTML 리뷰 파일은 반드시 만듭니다.
seed SQL 생성은 자동화해도, 최종 품질 확인은 HTML 리뷰 파일에서 사람이 빠르게 확인합니다.

### 23-4. 가장 무서운 품질 실패

이번 문제은행에서 가장 조심해야 할 실패는 아래 6개입니다.

| 실패 | 왜 위험한가 | 차단 방법 |
| --- | --- | --- |
| 정답 오류 | 서비스 신뢰를 바로 떨어뜨림 | answer, options, explanation 3자 대조 |
| 너무 뻔한 오답 | 개념을 몰라도 맞힐 수 있음 | 금지 표현, obvious cue, 정답 길이 편향 검사 |
| 초등학생에게 어려운 말 | 대상 연령과 맞지 않음 | LOW 어휘 부담 검사와 어려운 용어 whitelist |
| 미션 경계 섞임 | 학습 흐름이 무너짐 | mission primaryFocus 검사 |
| 중복 | 문제은행이 풍성해 보이지 않음 | same-mission duplicate와 template repeat 검사 |
| 학교 상황 과다 | 실제 생활 AI 리터러시와 멀어짐 | contextCategory 예산 검사 |

어려운 말 검사는 단순히 글자 수만 보지 않습니다.
아래 경우는 경고로 잡습니다.

- LOW 문항에 추상어가 3개 이상 겹침
- 초등학생에게 낯선 한자어가 핵심 정답 근거가 됨
- 설명 없이 `편향`, `출처`, `근거`, `개인정보`, `생체정보` 같은 용어가 반복됨
- 문장이 길어 한 번에 읽기 어려움

용어가 꼭 필요하면 `termHints`에 쉬운 설명을 붙입니다.

### 23-5. 품질 보장 수준

이 구조가 완성되면 문제 품질 리스크는 크게 줄어듭니다.
하지만 “문제없다”고 단정하려면 아래 조건까지 끝나야 합니다.

출시 가능 판단:

```text
deterministic validator PASS
-> LLM Judge 대상 문항 PASS 또는 MANUAL_REVIEW 처리 완료
-> HTML 리뷰에서 사용자가 핵심 샘플 확인
-> seed SQL 변환 smoke test PASS
```

최소 사람 검수 기준:

- P0/P1 문항은 전부 확인합니다.
- 각 미션에서 LOW/MEDIUM/HIGH를 최소 1개씩 확인합니다.
- 각 미션에서 SITUATION 문항을 최소 2개 확인합니다.
- `OBVIOUS_DISTRACTOR`, `LOW_VOCABULARY_BURDEN`, `CHAPTER_BOUNDARY_MISMATCH`, `SCHOOL_CONTEXT_OVERUSE` 경고 문항은 우선 확인합니다.

이 기준까지 통과하면 “자동 생성 문제은행으로 사용해도 되는 수준”이라고 볼 수 있습니다.
다만 교육 콘텐츠이므로 최종 책임은 자동화가 아니라 검수 리포트와 사람 확인을 포함한 전체 파이프라인이 집니다.

### 23-6. 더 고려해야 할 점

추가로 고려할 점은 아래 정도입니다.

1. 생성 결과를 항상 버전 폴더에 저장합니다.
   - 예: `question-bank-v1.5/`
   - 같은 버전 안에 rich JSON, backend-compatible JSON, seed SQL, report, HTML을 함께 둡니다.

2. 프롬프트와 설정을 결과물에 같이 보관합니다.
   - 나중에 문항 품질 문제가 생겼을 때 어떤 프롬프트로 만든 것인지 추적해야 합니다.

3. API 실패와 JSON 파싱 실패를 구분합니다.
   - API 호출 실패는 같은 batch 재시도입니다.
   - JSON 파싱 실패는 프롬프트나 response format 수정 대상입니다.

4. 재시도 횟수를 제한합니다.
   - 같은 batch는 최대 2회 재시도합니다.
   - 계속 실패하면 `MANUAL_REVIEW` 또는 `REBLUEPRINT`로 넘깁니다.

5. seed SQL 생성 전후를 대조합니다.
   - rich JSON 문항 수와 SQL insert 문항 수가 같아야 합니다.
   - 정답 수가 문항 수와 같아야 합니다.
   - missionCode, packNo, difficulty, questionType 분포가 변환 전후 동일해야 합니다.

6. HTML 리뷰 결과를 다음 생성 입력으로 되돌릴 수 있게 합니다.
   - HTML에서 표시한 이슈가 `manual-review-export.json`으로 나와야 합니다.
   - 다음 실행은 이 파일을 읽고 해당 문항만 재생성할 수 있어야 합니다.

7. 최종 PASS 기준을 숫자로 남깁니다.
   - 예: P0 0건, P1 0건, P2 30건 이하, 학교 맥락 초과 0건.
   - 기준이 숫자로 남아야 팀원이 임의로 “이 정도면 괜찮다”고 넘기지 않습니다.

결론:

- 지금 구조에 23번 운영 기준까지 적용하면 문제 생성 품질은 충분히 안정화할 수 있습니다.
- 그래도 완전 자동으로 “문제없음”은 아닙니다.
- validator PASS, LLM Judge, HTML 사람 검수, seed smoke test가 모두 끝났을 때 최종 통과로 봅니다.

## 24. 최종 확정 기준

아래 기준은 문제은행 생성기의 최종 숫자 계약입니다.

| 항목 | 확정값 |
| --- | --- |
| 최종 생성 대상 | 960문항 |
| 미션 수 | 16 |
| 미션당 문항 수 | 60 |
| 미션당 pack 수 | 6 |
| pack당 문항 수 | 10 |
| 미션당 유형 분포 | OX 12 / MULTIPLE 18 / FILL 6 / SITUATION 24 |
| 전체 유형 분포 | OX 192 / MULTIPLE 288 / FILL 96 / SITUATION 384 |
| 별 1개 난이도 | LOW 7 / MEDIUM 2 / HIGH 1 |
| 별 2개 난이도 | LOW 3 / MEDIUM 5 / HIGH 2 |
| 별 3개 난이도 | LOW 2 / MEDIUM 3 / HIGH 5 |
| 미션당 난이도 분포 | LOW 24 / MEDIUM 20 / HIGH 16 |
| 전체 난이도 분포 | LOW 384 / MEDIUM 320 / HIGH 256 |
| seed SQL 생성 조건 | validator PASS |
| 검수 우선순위 | 경고 문항 우선 |

참고: `AImong 문제 생성 시스템 설계서 v1.8`의 별 난이도별 실제 출제 비율은 `별1=7/2/1`, `별2=3/5/2`, `별3=2/3/5`입니다. 별 2개 기준은 `LOW 3 / MEDIUM 5 / HIGH 2`가 정본입니다.

출시 차단 기준:

- P0 0건
- 정답 오류 0건
- same-mission duplicate 0건
- 학교 상황 초과 0건
- P1 0건
- P2 30건 이하

반복 금지 표현:

- `그대로 믿어요`
- `확인하지 않아요`
- `무조건`
- `항상`
- `모두`
- `상관없어요`
- `필요 없어요`

운영 원칙:

- validator가 PASS일 때만 seed SQL을 자동 생성합니다.
- 경고 문항은 HTML 리뷰에서 우선 확인합니다.
- PASS_LOCKED 문항은 다음 생성 때 유지합니다.
- 연결된 v1.8 문서의 1,056 운영 풀은 런타임 운영/보강 풀 개념이고, 이 배치 생성기의 최종 생성 대상은 960문항입니다.
