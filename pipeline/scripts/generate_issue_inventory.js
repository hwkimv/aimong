const fs = require("fs");
const path = require("path");

const dir = __dirname;
const jsonPath = path.join(dir, "question-bank-1056-starlevel-ultra-diverse-patched.json");
const optionReportPath = path.join(dir, "question-bank-1056-option-quality-report.md");
const semanticReportPath = path.join(dir, "question-bank-1056-openai-semantic-similarity-report.md");
const outPath = path.join(dir, "question-bank-1056-current-issue-inventory.md");

const bank = JSON.parse(fs.readFileSync(jsonPath, "utf8"));
const questions = bank.questions || [];
const byId = new Map(questions.map((q) => [q.externalId, q]));
const optionReport = fs.readFileSync(optionReportPath, "utf8");
const semanticReport = fs.readFileSync(semanticReportPath, "utf8");

const idSort = (a, b) => a.localeCompare(b, "en", { numeric: true });
const uniq = (arr) => [...new Set(arr)].sort(idSort);
const textOf = (q) => [q.question || "", q.explanation || "", ...(q.options || [])].join(" ");
const csv = (ids) => (ids.length ? ids.join(", ") : "없음");
const code = (value) => "`" + String(value).replaceAll("`", "\\`") + "`";

function groupByMission(ids) {
  const grouped = {};
  for (const id of ids) {
    const mission = id.split("-")[0];
    if (!grouped[mission]) grouped[mission] = [];
    grouped[mission].push(id);
  }
  return Object.entries(grouped)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([mission, missionIds]) => `- ${mission} (${missionIds.length}): ${csv(missionIds.sort(idSort))}`)
    .join("\n");
}

function optionLabel(q, index) {
  if (!q || !Array.isArray(q.options)) return "";
  const answer = Array.isArray(q.answer) ? q.answer : [q.answer];
  const mark = answer.includes(index) ? "정답" : "오답";
  return `${index}번 ${mark}: ${q.options[index]}`;
}

const optionCounts = new Map();
for (const q of questions) {
  if (!Array.isArray(q.options)) continue;
  for (const option of q.options) {
    optionCounts.set(option, (optionCounts.get(option) || 0) + 1);
  }
}

const obviousPatterns = [
  "무조건",
  "항상",
  "그대로",
  "확인하지 않",
  "보지 않",
  "읽어 보지",
  "모른 척",
  "허락 없이",
  "숨겨",
  "숨기",
  "장난",
  "필요 없",
  "상관없",
  "모두 AI",
  "모두 정답",
  "내 생각처럼",
  "내 자료처럼",
  "공개 질문",
  "베껴",
  "복사",
  "절대",
  "완벽",
  "빠르면",
  "제목만",
  "한 자료만",
  "한쪽 의견만",
  "댓글을 먼저 믿",
  "날짜가 오래됐는지 확인하지 않"
];

const weakFillTerms = new Set([
  "휴식",
  "충전",
  "색깔",
  "소리",
  "비밀번호",
  "주소",
  "날씨",
  "운동",
  "간식",
  "삭제",
  "숨김",
  "무늬",
  "제작",
  "전달",
  "모양"
]);

const issueBuckets = {
  obvious: [],
  absolute: [],
  repeatedOption: [],
  weakFill: [],
  veryShortFill: [],
  lengthBias: []
};
const issueDetails = new Map();

function addIssue(id, kind, detail) {
  issueBuckets[kind].push(id);
  if (!issueDetails.has(id)) issueDetails.set(id, []);
  issueDetails.get(id).push(detail);
}

for (const q of questions) {
  if (!Array.isArray(q.options)) continue;
  const answerIndexes = Array.isArray(q.answer) ? q.answer : [q.answer];
  const answerTexts = answerIndexes.map((i) => q.options[i]).filter(Boolean);
  const distractors = q.options.map((option, index) => ({ option, index })).filter(({ index }) => !answerIndexes.includes(index));

  for (const { option, index } of distractors) {
    const matched = obviousPatterns.filter((pattern) => option.includes(pattern));
    if (matched.length) addIssue(q.externalId, "obvious", `${optionLabel(q, index)} / obvious-cue=${matched.join("|")}`);
    if (/(무조건|항상|절대|모두|완벽)/.test(option)) addIssue(q.externalId, "absolute", `${optionLabel(q, index)} / absolute-word`);
    const repeated = optionCounts.get(option) || 0;
    if (repeated >= 4) addIssue(q.externalId, "repeatedOption", `${optionLabel(q, index)} / repeated-${repeated}`);
    if (q.type === "FILL" && weakFillTerms.has(option)) addIssue(q.externalId, "weakFill", `${optionLabel(q, index)} / weak-fill-distractor`);
    if (q.type === "FILL" && [...option].length <= 3) addIssue(q.externalId, "veryShortFill", `${optionLabel(q, index)} / very-short-fill`);
  }

  if (answerTexts.length && distractors.length) {
    const answerMax = Math.max(...answerTexts.map((s) => [...s].length));
    const avgDistractor = distractors.reduce((sum, d) => sum + [...d.option].length, 0) / distractors.length;
    if (answerMax >= 18 && answerMax / Math.max(avgDistractor, 1) >= 1.6) {
      addIssue(q.externalId, "lengthBias", `정답 길이 ${answerMax}, 오답 평균 ${avgDistractor.toFixed(1)} / correct-length-bias`);
    }
  }
}

for (const key of Object.keys(issueBuckets)) {
  issueBuckets[key] = uniq(issueBuckets[key]);
}

const optionTopEntries = [];
const blocks = optionReport.split(/\n(?=### S\d+-P\d+-\d+ score=)/);
for (const block of blocks) {
  const header = block.match(/^### (S\d+-P\d+-\d+) score=(\d+) mission=(S\d+) type=(\w+)/m);
  if (!header) continue;
  const [, id, score, mission, type] = header;
  const flags = [...block.matchAll(/^- flag option (\d+): (.+)$/gm)].map((m) => `${m[1]}번 ${m[2]}`);
  optionTopEntries.push({ id, score: Number(score), mission, type, flags });
}

const p0Ids = ["S0102-P1-09", "S0102-P3-09", "S0103-P2-02", "S0301-P2-01", "S0302-P2-02", "S0302-P2-03"];
const oldPhrase = "사진·소리·글을 알아보는 AI";
const newPhrase = "AI가 보고 듣고 읽어요";
const oldPhraseIds = questions.filter((q) => textOf(q).includes(oldPhrase) || q.missionTitle === oldPhrase).map((q) => q.externalId);
const newPhraseIds = questions.filter((q) => textOf(q).includes(newPhrase) || q.missionTitle === newPhrase).map((q) => q.externalId);

const expectedPerMission = { OX: 13, MULTIPLE: 20, FILL: 13, SITUATION: 20 };
const typeMismatch = [];
const missionCodes = uniq(questions.map((q) => q.missionCode));
for (const mission of missionCodes) {
  const missionQuestions = questions.filter((q) => q.missionCode === mission);
  const actual = {};
  for (const q of missionQuestions) actual[q.type] = (actual[q.type] || 0) + 1;
  const differs = Object.keys(expectedPerMission).some((type) => (actual[type] || 0) !== expectedPerMission[type]);
  if (differs) typeMismatch.push({ mission, actual });
}

const schoolTerms = ["학교", "수업", "모둠", "발표", "수행평가", "학급", "국어", "과학", "사회", "코딩 활동", "도서관"];
const schoolByTerm = {};
for (const term of schoolTerms) {
  schoolByTerm[term] = uniq(questions.filter((q) => textOf(q).includes(term)).map((q) => q.externalId));
}
const schoolAny = uniq(Object.values(schoolByTerm).flat());

const lowHeavyTerms = ["출처", "검증", "목적", "데이터", "개인정보", "편향", "공정", "근거", "판단 방식", "학습", "테스트", "자료", "조건", "비교"];
const lowVocabulary = questions
  .filter((q) => q.difficulty === "LOW")
  .map((q) => {
    const matched = lowHeavyTerms.filter((term) => textOf(q).includes(term));
    return { id: q.externalId, matched };
  })
  .filter((item) => item.matched.length >= 2)
  .sort((a, b) => idSort(a.id, b.id));

const awkwardS0104 = questions
  .filter((q) => q.missionCode === "S0104")
  .filter((q) => /물체 인식/.test(textOf(q)) && /소음|소리/.test(textOf(q)))
  .map((q) => q.externalId)
  .sort(idSort);

const semanticSummary = {};
for (const key of [
  "same-mission duplicate count",
  "same-mission template repeat count",
  "review count",
  "global duplicate/review count",
  "verdict"
]) {
  const match = semanticReport.match(new RegExp(`- ${key}: (.+)`));
  semanticSummary[key] = match ? match[1].trim() : "";
}

const pairLines = [...semanticReport.matchAll(/^- (TEMPLATE_REPEAT|DUPLICATE|REVIEW) (S\d+-P\d+-\d+) vs (S\d+-P\d+-\d+) core=([0-9.]+) surface=([0-9.]+) template=([0-9.]+\/[0-9.]+)/gm)]
  .map((m) => ({ kind: m[1], a: m[2], b: m[3], core: m[4], surface: m[5], template: m[6] }));

const clusterBlocks = semanticReport.split(/\n(?=- C\d{4} `)/).filter((block) => /^- C\d{4} `/.test(block.trim()));
const clusters = clusterBlocks.map((block) => {
  const head = block.match(/^- (C\d{4}) `([^`]+)` size=(\d+) missions=([^\n]+)/m);
  const ids = block.match(/questionIds: ([^\n]+)/m);
  const action = block.match(/recommendedAction: ([^\n]+)/m);
  return {
    cluster: head?.[1] || "",
    kind: head?.[2] || "",
    size: Number(head?.[3] || 0),
    missions: head?.[4] || "",
    ids: ids ? ids[1].split(/,\s*/).filter(Boolean) : [],
    action: action?.[1] || ""
  };
}).filter((c) => c.cluster);

const repeatedOptionStrings = [...optionCounts.entries()]
  .filter(([text, count]) => count >= 8)
  .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "ko"))
  .map(([text, count]) => ({ text, count, ids: uniq(questions.filter((q) => Array.isArray(q.options) && q.options.includes(text)).map((q) => q.externalId)) }));

const lines = [];
lines.push("# question-bank-1056 현재 이슈 전체 목록");
lines.push("");
lines.push(`- 생성 기준: ${new Date().toISOString()}`);
lines.push(`- JSON: ${path.basename(jsonPath)}`);
lines.push(`- Option report: ${path.basename(optionReportPath)}`);
lines.push(`- Semantic report: ${path.basename(semanticReportPath)}`);
lines.push("");
lines.push("> 주의: option-quality-report의 요약은 flagged question count 764로 되어 있지만, 본문에 ID와 flag가 상세 열거된 항목은 상위 80건입니다. 이 문서는 현재 JSON을 기준으로 재검출한 전체 후보와 원 리포트 상세 80건을 분리해 적었습니다.");
lines.push("");

lines.push("## 1. P0 정답 오류 후보 6건 반영 상태");
for (const id of p0Ids) {
  const q = byId.get(id);
  lines.push(`- ${id}: type=${q.type}, answer=${JSON.stringify(q.answer)}, question=${q.question}`);
  if (Array.isArray(q.options)) lines.push(`  - options: ${q.options.map((o, i) => `${i}:${o}`).join(" / ")}`);
  lines.push(`  - explanation: ${q.explanation}`);
}
lines.push("");

lines.push("## 2. S0104 명칭 변경 상태");
lines.push(`- 남은 기존 표현 ${code(oldPhrase)} 포함 문항 (${oldPhraseIds.length}): ${csv(oldPhraseIds)}`);
lines.push(`- 새 표현 ${code(newPhrase)} 포함/미션명 문항 (${newPhraseIds.length}): ${csv(newPhraseIds)}`);
lines.push(`- S0104 물체 인식과 소음/소리 표현이 함께 나오는 어색한 후보 (${awkwardS0104.length}): ${csv(awkwardS0104)}`);
lines.push("");

lines.push("## 3. 유형 분포 불일치 미션");
lines.push("- 기대값: mission당 OX 13 / MULTIPLE 20 / FILL 13 / SITUATION 20");
for (const item of typeMismatch) {
  lines.push(`- ${item.mission}: actual=${JSON.stringify(item.actual)}`);
}
lines.push("");

lines.push("## 4. 현재 JSON 기준 선택지 품질 재검출 전체 후보");
const bucketNames = {
  obvious: "오답이 너무 뻔한 표현 후보",
  absolute: "절대어/극단어 후보",
  repeatedOption: "반복 오답 후보",
  weakFill: "빈칸형 약한 오답 후보",
  veryShortFill: "빈칸형 매우 짧은 오답 후보",
  lengthBias: "정답 길이 편향 후보"
};
for (const [key, title] of Object.entries(bucketNames)) {
  const ids = issueBuckets[key];
  lines.push(`### 4-${Object.keys(bucketNames).indexOf(key) + 1}. ${title} (${ids.length})`);
  lines.push(groupByMission(ids));
  lines.push("");
}

lines.push("## 5. 선택지 이슈 상세: ID별 검출 사유");
const allOptionIssueIds = uniq(Object.values(issueBuckets).flat());
for (const id of allOptionIssueIds) {
  const q = byId.get(id);
  lines.push(`### ${id} ${q.missionCode} ${q.type} ${q.difficulty}`);
  lines.push(`- question: ${q.question}`);
  if (Array.isArray(q.options)) {
    const answer = Array.isArray(q.answer) ? q.answer : [q.answer];
    for (let i = 0; i < q.options.length; i++) {
      lines.push(`- option ${i}${answer.includes(i) ? " (answer)" : ""}: ${q.options[i]}`);
    }
  }
  for (const detail of issueDetails.get(id) || []) lines.push(`- issue: ${detail}`);
}
lines.push("");

lines.push("## 6. 원 option-quality-report가 상세 열거한 상위 80건");
for (const entry of optionTopEntries) {
  lines.push(`- ${entry.id}: score=${entry.score}, mission=${entry.mission}, type=${entry.type}, flags=${entry.flags.join(" / ")}`);
}
lines.push("");

lines.push("## 7. 8회 이상 반복되는 선택지 문자열");
for (const item of repeatedOptionStrings) {
  lines.push(`- ${item.count}x ${code(item.text)}: ${csv(item.ids)}`);
}
lines.push("");

lines.push("## 8. Semantic similarity report 전체 pair");
lines.push(`- same-mission duplicate count: ${semanticSummary["same-mission duplicate count"]}`);
lines.push(`- same-mission template repeat count: ${semanticSummary["same-mission template repeat count"]}`);
lines.push(`- review count: ${semanticSummary["review count"]}`);
lines.push(`- global duplicate/review count: ${semanticSummary["global duplicate/review count"]}`);
lines.push(`- verdict: ${semanticSummary.verdict}`);
lines.push("");
for (const pair of pairLines) {
  lines.push(`- ${pair.kind}: ${pair.a} vs ${pair.b} / core=${pair.core}, surface=${pair.surface}, template=${pair.template}`);
}
lines.push("");

lines.push("## 9. Semantic cluster 전체 목록");
for (const c of clusters) {
  lines.push(`### ${c.cluster} ${c.kind} size=${c.size} missions=${c.missions}`);
  lines.push(`- recommendedAction: ${c.action}`);
  lines.push(`- questionIds: ${csv(c.ids)}`);
}
lines.push("");

lines.push("## 10. 학교/수업 중심 상황문 잔존 후보");
lines.push(`- 중복 제거 전체 (${schoolAny.length}): ${csv(schoolAny)}`);
for (const term of schoolTerms) {
  lines.push(`- ${term} (${schoolByTerm[term].length}): ${csv(schoolByTerm[term])}`);
}
lines.push("");

lines.push("## 11. LOW 난이도 어휘 부담 후보");
lines.push(`- 기준: LOW 문항에서 ${lowHeavyTerms.map(code).join(", ")} 중 2개 이상 포함`);
for (const item of lowVocabulary) {
  const q = byId.get(item.id);
  lines.push(`- ${item.id}: terms=${item.matched.join(", ")} / ${q.question}`);
}

fs.writeFileSync(outPath, lines.join("\n") + "\n", "utf8");
console.log(outPath);
