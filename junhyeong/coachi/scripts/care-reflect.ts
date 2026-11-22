// 코치모드 습관 시험 도우미(영상 시험용). 서버를 끈 채로 runtime/homes/<집>/care-habits.json을 다룬다.
//   npx tsx scripts/care-reflect.ts show [--home apartment]
//   npx tsx scripts/care-reflect.ts move --to 2026-11-20 [--home apartment]   오늘 기록을 그날로 옮긴다(같은 날 영상 여러 판으로 「반복된 날」을 흉내 낸다)
//   npx tsx scripts/care-reflect.ts reflect [--home apartment]              자기 반성: 습관과 중요도를 정해 저장한다
// reflect의 중요도 판단은 CARE_LLM_URL·CARE_LLM_MODEL·CARE_LLM_API_KEY(OpenAI 호환)로 부르고, 모델 답을 읽지 못하면 규칙으로 정한다(어느 쪽인지 찍는다).
import { join } from "node:path";
import { fileHabitStore } from "../src/brain/care/coach.js";
import { hhmm, llmImportance, reflectHabits, ruleImportance, type ImportanceJudge } from "../src/brain/care/habits.js";
import { historyTzMinutes } from "../src/brain/history/db.js";

const argv = process.argv.slice(2);
const arg = (k: string) => { const i = argv.indexOf(`--${k}`); return i >= 0 ? argv[i + 1] : undefined; };
const home = arg("home") ?? "apartment";
const path = join(process.env.RUNTIME_DIR ?? "runtime", "homes", home, "care-habits.json");
const store = fileHabitStore(path);
const data = store.load() ?? { habits: [], events: [] };
const today = new Date(Date.now() + historyTzMinutes(process.env) * 60_000).toISOString().slice(0, 10);

const show = () => {
  console.log(`기록 ${data.events.length}개`);
  for (const e of data.events) console.log(`  ${e.day} ${hhmm(e.minute)} ${e.activity}${e.afterMeal ? " (식사 뒤)" : ""}`);
  console.log(`습관 ${data.habits.length}개`);
  for (const h of data.habits) console.log(`  ${h.label} 평소 ${hhmm(h.minute)} · ${h.days}일 · ${h.afterMeal ? "식사 뒤" : "식사와 무관"} · ${h.importance === "essential" ? "필수" : "생략 가능"}`);
};

const cmd = argv[0];
if (cmd === "move") {
  const to = arg("to");
  if (!to || !/^\d{4}-\d{2}-\d{2}$/.test(to)) throw new Error("--to YYYY-MM-DD");
  let n = 0;
  data.events = data.events.map((e) => (e.day === today ? (n++, { ...e, day: to }) : e));
  store.save(data);
  console.log(`오늘(${today}) 기록 ${n}개를 ${to}로 옮김`);
  show();
} else if (cmd === "add") {
  // 손으로 넣는 기록(영상에서 약 먹기를 못 봤을 때 습관 경로를 시험한다): --day YYYY-MM-DD --at HH:MM [--after-meal]
  const day = arg("day"), at = arg("at");
  const m = /^(\d{1,2}):(\d{2})$/.exec(at ?? "");
  if (!day || !/^\d{4}-\d{2}-\d{2}$/.test(day) || !m) throw new Error("--day YYYY-MM-DD --at HH:MM");
  data.events = [...data.events, { day, minute: Number(m[1]) * 60 + Number(m[2]), activity: "taking_medicine", afterMeal: argv.includes("--after-meal") }];
  store.save(data);
  console.log(`손으로 넣은 기록: ${day} ${at} 약 먹기`);
  show();
} else if (cmd === "reflect") {
  const url = process.env.CARE_LLM_URL?.trim();
  let used = "규칙(ruleImportance)";
  let judge: ImportanceJudge = ruleImportance;
  if (url) {
    const model = process.env.CARE_LLM_MODEL?.trim() || "Qwen/Qwen3-8B";
    used = `생각 모델 ${model}`;
    judge = llmImportance({
      baseUrl: url, model, apiKey: process.env.CARE_LLM_API_KEY?.trim() || undefined,
      fallback: async (h, info) => { used = `생각 모델 ${model} 실패 → 규칙`; return ruleImportance(h, info); },
    });
  }
  const userInfo = process.env.CARE_USER_INFO ?? "";
  data.habits = await reflectHabits(data.events, userInfo, judge);
  store.save(data);
  console.log(`사용자 정보: ${userInfo || "(없음)"}`);
  console.log(`중요도 판단: ${used}`);
  show();
} else {
  show();
}
