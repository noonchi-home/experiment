// 발달장애인 코치모드의 시각 습관(코치모드 시나리오.txt 「사용자 습관 기반 시나리오」).
// - 관찰 빈도가 높아 사용자에게 묻지 않고, 날마다 비슷한 시각에 늘 일어나는 활동(약 먹기)을 습관으로 기록한다(learnHabits).
// - 자기 반성(밤) 때 습관마다 중요도(필수·생략 가능)를 정한다(reflectHabits). 필수는 사전 입력받은 사용자 정보를 바탕으로
//   생각 모델(Qwen, OpenAI 호환 API)이 정하고(llmImportance), 모델이 없거나 실패하면 규칙(ruleImportance)으로 정한다.
// - 필수 습관은 시각이 되면 묻지 않고 돕고, 생략 가능한 습관은 눈치모드처럼 먼저 묻는다(src/brain/care/coach.ts).

/** 습관 중요도: essential 필수(묻지 않고 돕는다), optional 생략 가능(눈치모드처럼 묻는다). */
export type Importance = "essential" | "optional";

/** 하루 기록에서 본 활동 하나: 날(YYYY-MM-DD), 그날 몇 분(0~1439), World State 사람 하는 일 값, 그 앞에 식사가 끝났는가. */
export interface ActivityEvent { day: string; minute: number; activity: string; afterMeal?: boolean }

/** 배운 시각 습관. */
export interface CareHabit {
  id: string;
  /** 습관 활동(World State 사람 하는 일 값). */
  activity: string;
  /** 습관을 놓쳤을 때 돕는 행동(행동 목록 이름). */
  action: string;
  /** 화면 글(「약 먹기」). */
  label: string;
  /** 평소 시각(그날 몇 분, 본 날들의 평균). */
  minute: number;
  /** 평소 시각에서 이만큼(분) 안이면 같은 습관으로 본다. */
  windowMin: number;
  /** 본 날 수. */
  days: number;
  /** 식사가 끝난 뒤에 하는 습관인가(본 날 모두 식사 뒤). */
  afterMeal: boolean;
  importance: Importance;
}

/** 습관이 되는 활동과 놓쳤을 때 돕는 행동. 표에 없는 활동은 습관으로 배우지 않는다(행동 목록에 돕는 행동이 없다). */
export const HABIT_ACTIVITIES: Readonly<Record<string, { action: string; label: string }>> = {
  taking_medicine: { action: "약과 물 가져다주기", label: "약 먹기" },
};

/** 습관으로 보는 최소 날 수와 시각 폭(분). 시나리오: 8:00·8:05·8:10 사흘. */
export const HABIT_RULE = { minDays: 2, windowMin: 30 } as const;

/** 하루 기록들에서 시각 습관을 찾는다: 같은 활동이 서로 다른 minDays일 이상, 그 평균 시각 windowMin 안에 있었다. 중요도는 아직 정하지 않았다(optional). */
export function learnHabits(events: readonly ActivityEvent[], rule: { minDays: number; windowMin: number } = HABIT_RULE): CareHabit[] {
  const out: CareHabit[] = [];
  for (const [activity, spec] of Object.entries(HABIT_ACTIVITIES)) {
    // 날마다 그 활동의 첫 시각
    const byDay = new Map<string, ActivityEvent>();
    for (const e of events) if (e.activity === activity && (!byDay.has(e.day) || e.minute < byDay.get(e.day)!.minute)) byDay.set(e.day, e);
    const firsts = [...byDay.values()];
    if (firsts.length < rule.minDays) continue;
    const mean = Math.round(firsts.reduce((s, e) => s + e.minute, 0) / firsts.length);
    const near = firsts.filter((e) => Math.abs(e.minute - mean) <= rule.windowMin);
    if (near.length < rule.minDays) continue;
    const minute = Math.round(near.reduce((s, e) => s + e.minute, 0) / near.length);
    out.push({
      id: `habit:${activity}`, activity, action: spec.action, label: spec.label, minute, windowMin: rule.windowMin, days: near.length,
      afterMeal: near.every((e) => e.afterMeal === true), importance: "optional",
    });
  }
  return out;
}

/** 중요도 판단: 습관과 사전 입력받은 사용자 정보로 필수·생략 가능을 정한다. */
export type ImportanceJudge = (habit: CareHabit, userInfo: string) => Promise<Importance>;

/** 늘 필수인 활동(건강에 바로 닿는다). */
const ALWAYS_ESSENTIAL: ReadonlySet<string> = new Set(["taking_medicine"]);
/** 사용자 정보에 이 말이 있으면 그 습관은 필수다. */
const ESSENTIAL_WORDS: Readonly<Record<string, readonly string[]>> = { taking_medicine: ["약", "복용", "복약", "처방", "투약"] };

/** 규칙 중요도(모델이 없을 때): 늘 필수인 활동이거나 사용자 정보가 그 습관을 말하면 필수. */
export const ruleImportance: ImportanceJudge = async (habit, userInfo) =>
  ALWAYS_ESSENTIAL.has(habit.activity) || (ESSENTIAL_WORDS[habit.activity] ?? []).some((w) => userInfo.includes(w)) ? "essential" : "optional";

/** 생각 모델(OpenAI 호환 chat/completions, 기본 Qwen) 중요도. 답에서 essential·optional을 읽지 못하거나 부르지 못하면 fallback을 쓴다. */
export function llmImportance(o: { baseUrl: string; model: string; apiKey?: string; timeoutMs?: number; fallback?: ImportanceJudge; fetch?: typeof fetch }): ImportanceJudge {
  const fallback = o.fallback ?? ruleImportance;
  return async (habit, userInfo) => {
    const prompt = [
      "You decide how important a daily habit is for a person with a developmental disability.",
      "essential: skipping it can harm health or safety, so the robot must help without asking.",
      "optional: it can be skipped, so the robot should ask first.",
      `User information (entered in advance by a caregiver):\n${userInfo || "(none)"}`,
      `Habit: ${habit.label} (activity ${habit.activity}) around ${hhmm(habit.minute)}, seen on ${habit.days} days${habit.afterMeal ? ", after meals" : ""}.`,
      'Answer with JSON only: {"importance": "essential" | "optional", "reason": "..."}',
    ].join("\n\n");
    try {
      const res = await (o.fetch ?? fetch)(`${o.baseUrl.replace(/\/+$/, "")}/chat/completions`, {
        method: "POST",
        headers: { "content-type": "application/json", ...(o.apiKey ? { authorization: `Bearer ${o.apiKey}` } : {}) },
        body: JSON.stringify({ model: o.model, messages: [{ role: "user", content: prompt }], temperature: 0 }),
        signal: AbortSignal.timeout(o.timeoutMs ?? 60_000),
      });
      if (!res.ok) return fallback(habit, userInfo);
      const body = (await res.json()) as { choices?: { message?: { content?: string } }[] };
      // 생각 모델은 <think>…</think> 뒤에 답한다
      const text = (body.choices?.[0]?.message?.content ?? "").replace(/<think>[\s\S]*?<\/think>/g, "");
      const m = /"importance"\s*:\s*"(essential|optional)"/.exec(text) ?? /\b(essential|optional)\b/.exec(text);
      return m ? (m[1] as Importance) : fallback(habit, userInfo);
    } catch {
      return fallback(habit, userInfo);
    }
  };
}

/** 환경 변수로 중요도 판단을 고른다: CARE_LLM_URL·CARE_LLM_MODEL(기본 Qwen/Qwen3-8B)이 있으면 생각 모델, 없으면 규칙. */
export function importanceFromEnv(env: Record<string, string | undefined>): ImportanceJudge {
  const baseUrl = env.CARE_LLM_URL?.trim();
  if (!baseUrl) return ruleImportance;
  return llmImportance({ baseUrl, model: env.CARE_LLM_MODEL?.trim() || "Qwen/Qwen3-8B", apiKey: env.CARE_LLM_API_KEY?.trim() || undefined });
}

/** 자기 반성: 하루 기록들에서 습관을 배우고 습관마다 중요도를 정한다. */
export async function reflectHabits(events: readonly ActivityEvent[], userInfo: string, judge: ImportanceJudge = ruleImportance): Promise<CareHabit[]> {
  const habits = learnHabits(events);
  return Promise.all(habits.map(async (h) => ({ ...h, importance: await judge(h, userInfo) })));
}

/** 그날 몇 분 → 「20:05」. */
export const hhmm = (minute: number): string => `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
