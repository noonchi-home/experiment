// 발달장애인 코치모드(코치모드 시나리오.txt): 프로필 care로 띄운 표(행동 목록·seed 기억)와 코치모드 규칙(src/brain/care/), 판단에 붙인 모습을 본다.
import { TOPICS } from "../src/bus/topics.js";
import { describe, expect, it, vi } from "vitest";

// 행동 목록·seed 기억은 모듈을 읽을 때 프로필로 정해진다: import보다 먼저 프로필을 정한다
vi.hoisted(() => { process.env.NOONCHI_PROFILE = "care"; });

import { CARE_FSM_MEMORY, CUP_FSM_MEMORY, validateMemory, validateFsmPrediction } from "../src/brain/decision.js";
import { CareCoach, foodLeft } from "../src/brain/care/coach.js";
import { learnHabits, llmImportance, reflectHabits, ruleImportance, type ActivityEvent, type CareHabit } from "../src/brain/care/habits.js";
import { Decider } from "../src/brain/decide.js";
import { TASKS, TASK_NAMES, tasksFor } from "../src/act/tasks.js";
import { modeNow, pamTasks } from "../src/manage/mode.js";
import { userSpot } from "../src/act/robot/dock.js";
import { Trigger } from "../src/world/trigger.js";
import { isCare } from "../src/shared/profile.js";
import type { DecisionRecord } from "../src/contract/events.js";
import type { WorldDevice, WorldObject, WorldView } from "../src/contract/world.js";
import type { PamClient } from "../src/brain/pam/index.js";

const OFFSET = 540; // KST
/** 그날(KST) 그 시각의 ms. */
const at = (day: string, hh: number, mm = 0) => Date.parse(`${day}T${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}:00+09:00`);

const fact = (value: string, atMs = 0) => ({ value, at_ms: atMs, since_ms: atMs, certainty: "confirmed" as const });

function bowl(contents: "empty" | "has_contents", place = "on_table"): WorldObject {
  return {
    id: "bowl_1", cls: "bowl", position: [1, 0.8, 1], surface: "table_1", surface_label: "식탁", room: "kitchen", error_m: null, status: "present",
    first_seen_ms: 0, last_seen_ms: 0, last_in_view_ms: 0, facts: { contents: fact(contents), place: fact(place) }, answered_ms: null, devices: [], closer_hold: false, followed_by: null,
  } as WorldObject;
}

function fridge(open: boolean, eventMs: number): WorldDevice {
  return {
    id: "fridge_1", kind: "fridge", label: "냉장고", status: open ? "문 열림" : "문 닫힘", state: [open ? "door_open" : "door_closed"], active: open,
    changed_ms: eventMs, event_ms: eventMs, started_ms: null, remaining_min: null, history: [],
  } as WorldDevice;
}

interface Scene { now: number; activity?: string; room?: string; roomLabel?: string; posture?: string; visible?: boolean; objects?: WorldObject[]; devices?: WorldDevice[] }
function view(s: Scene): WorldView {
  const visible = s.visible ?? true;
  return {
    at_ms: s.now, objects: s.objects ?? [], fixtures: [], devices: s.devices ?? [], eye: null, frame_ms: s.now, vlm_missing: 0, yolo_missing: 0,
    person: {
      visible, since_ms: 0, last_seen_ms: s.now, count: visible ? 1 : 0, position: visible ? [2, 3] : null, position_ms: s.now, room: s.room ?? "living_room",
      room_label: s.roomLabel ?? "거실", near: [], holding: [],
      facts: { ...(s.activity ? { activity: fact(s.activity, s.now) } : {}), ...(s.posture ? { posture: fact(s.posture, s.now) } : {}) },
      answered_ms: null,
    },
  } as WorldView;
}

const MEDS: CareHabit = { id: "habit:taking_medicine", activity: "taking_medicine", action: "약과 물 가져다주기", label: "약 먹기", minute: 20 * 60 + 5, windowMin: 30, days: 3, afterMeal: true, importance: "essential" };

describe("코치모드 표", () => {
  it("프로필 care로 띄우면 코치모드 행동과 seed 기억을 쓴다", () => {
    expect(isCare()).toBe(true);
    expect(CUP_FSM_MEMORY).toBe(CARE_FSM_MEMORY);
    for (const n of ["컵과 접시 준비하기", "사용자 곁에서 지켜보기", "남은 음식 가져다주기", "약과 물 가져다주기"]) expect(TASK_NAMES).toContain(n);
    // seed 기억이 지금 행동 목록으로 모양 검사를 지난다
    expect(() => validateMemory(CARE_FSM_MEMORY, "fsm")).not.toThrow();
    // 늘 코치 모드, PAM 목록은 코치모드 행동과 눈치 행동(라면 알려 주기는 말로 부탁할 때만)
    expect(modeNow({ world: null, offNotices: [], coaching: false })).toBe("coach");
    expect(pamTasks("coach", false)).toEqual(tasksFor("coach"));
    expect(pamTasks("coach", false)).toContain("컵 치우기");
    expect(pamTasks("coach", false)).not.toContain("라면 끓이기 알려 주기");
    expect(pamTasks("coach", true)).toContain("라면 끓이기 알려 주기");
    expect(TASKS["컵과 접시 준비하기"]!.care).toBe(true);
  });

  it("시나리오 3·4: 식사 중 화살표 — 남긴 채 TV면 식사 중을 지키며 음식을 가져다주고, 다 먹고 TV면 TV 시청 중으로 바꾸고 치운다", () => {
    const tasks = pamTasks("coach", false);
    const drinking = CARE_FSM_MEMORY.states.find((s) => s.id === "drinking")!;
    const food = drinking.next.findIndex((e) => e.action === "남은 음식 가져다주기");
    const done = drinking.next.findIndex((e) => e.action === "컵 치우기" && e.to === "watching_tv");
    const p1 = validateFsmPrediction({ observation: "o", reasoning: "r", state: "drinking", from: "drinking", next_index: food }, CARE_FSM_MEMORY, tasks, "drinking");
    expect(tasks[p1.task_index]).toBe("남은 음식 가져다주기");
    const p2 = validateFsmPrediction({ observation: "o", reasoning: "r", state: "watching_tv", from: "drinking", next_index: done }, CARE_FSM_MEMORY, tasks, "drinking");
    expect(tasks[p2.task_index]).toBe("컵 치우기");
  });
});

describe("가전 트리거 시나리오", () => {
  const day = "2026-11-23";

  it("1. 냉장고 문이 열리면 관찰 없이 바로 컵과 접시를 준비한다(먹는 중이면 하지 않는다)", () => {
    const c = new CareCoach({ offsetMinutes: OFFSET });
    const now = at(day, 18);
    const v = view({ now, room: "kitchen", roomLabel: "주방", devices: [fridge(true, now)] });
    c.observe(v, "away", now);
    expect(c.cue(v, "away", now)).toMatchObject({ action: "컵과 접시 준비하기", reason: "fridge_open" });
    // 같은 열림은 한 번만
    expect(c.cue(v, "away", now + 250)).toBeNull();
    const c2 = new CareCoach({ offsetMinutes: OFFSET });
    expect(c2.cue(v, "drinking", now)).toBeNull();
  });

  it("2·3. 음식이 남은 채 자리를 비우면 화살표 없는 상태 바뀜을 받지 않고 식사 중을 지킨다", () => {
    const c = new CareCoach({ offsetMinutes: OFFSET });
    const left = { objects: [bowl("has_contents")] };
    expect(foodLeft(left)).toBe(true);
    expect(c.holdState("drinking", { state: "watching_tv", from: null }, left)).toBe("drinking");
    // 화살표가 있는 바뀜(다 먹음·그만 먹겠다는 답)은 받는다
    expect(c.holdState("drinking", { state: "watching_tv", from: "drinking" }, left)).toBe("watching_tv");
    // 다 먹었으면(그릇이 비었거나 싱크대 안) 받는다
    expect(c.holdState("drinking", { state: "watching_tv", from: null }, { objects: [bowl("empty")] })).toBe("watching_tv");
    expect(c.holdState("drinking", { state: "watching_tv", from: null }, { objects: [bowl("has_contents", "in_sink")] })).toBe("watching_tv");
  });

  it("6. 계획이 끝나면 충전 자리 대신 사용자 곁(발 자리)으로 간다", () => {
    expect(userSpot(view({ now: 0 }))).toEqual([2, 0, 3]);
    expect(userSpot(view({ now: 0, visible: false }))).toBeNull();
  });

  it("사용자가 방을 옮기면 따라가 지켜본다(식사 중은 PAM 화살표가 보고, 1분에 한 번)", () => {
    const c = new CareCoach({ offsetMinutes: OFFSET });
    const t = at(day, 19);
    expect(c.cue(view({ now: t, room: "living_room" }), "watching_tv", t)).toBeNull();
    expect(c.cue(view({ now: t + 1000, room: "bedroom", roomLabel: "침실" }), "watching_tv", t + 1000)).toMatchObject({ action: "사용자 곁에서 지켜보기", reason: "follow" });
    expect(c.cue(view({ now: t + 2000, room: "living_room" }), "watching_tv", t + 2000)).toBeNull();
    expect(c.cue(view({ now: t + 3000, room: "kitchen" }), "drinking", t + 3000)).toBeNull();
  });
});

describe("사용자 습관 기반 시나리오", () => {
  it("1·2. 사흘 약 먹기(8:00·8:05·8:10)를 습관으로 배우고, 사용자 정보로 중요도를 정한다", async () => {
    const events: ActivityEvent[] = [
      { day: "2026-11-20", minute: 20 * 60, activity: "taking_medicine", afterMeal: true },
      { day: "2026-11-21", minute: 20 * 60 + 5, activity: "taking_medicine", afterMeal: true },
      { day: "2026-11-22", minute: 20 * 60 + 10, activity: "taking_medicine", afterMeal: true },
    ];
    expect(learnHabits(events.slice(0, 1))).toEqual([]);
    const [h] = await reflectHabits(events, "저녁 식후 약을 꼭 먹어야 함");
    expect(h).toMatchObject({ activity: "taking_medicine", minute: 20 * 60 + 5, days: 3, afterMeal: true, importance: "essential", action: "약과 물 가져다주기" });
    expect(await ruleImportance(h!, "")).toBe("essential");
  });

  it("관찰한 약 먹기를 날마다 기록하고 날이 바뀌면 반성으로 습관을 세운다", async () => {
    const c = new CareCoach({ offsetMinutes: OFFSET, userInfo: "식후 약 복용" });
    for (const [d, m] of [["2026-11-20", 0], ["2026-11-21", 5], ["2026-11-22", 10]] as const) {
      const t = at(d, 20, m);
      c.observe(view({ now: t, activity: "eating" }), "drinking", t - 60_000);
      c.observe(view({ now: t }), "watching_tv", t - 30_000);
      c.observe(view({ now: t, activity: "taking_medicine" }), "taking_medicine", t);
    }
    const next = at("2026-11-23", 7);
    c.observe(view({ now: next }), "away", next);
    await c.reflect();
    expect(c.habitsNow()).toMatchObject([{ activity: "taking_medicine", minute: 20 * 60 + 5, importance: "essential", afterMeal: true }]);
  });

  it("2. 필수 습관은 묻지 않고 돕고, 생략 가능 습관은 먼저 묻는다", () => {
    const day = "2026-11-23";
    const t = at(day, 20, 5);
    const ate = (c: CareCoach) => { c.observe(view({ now: t - 120_000, activity: "eating" }), "drinking", t - 120_000); c.observe(view({ now: t - 60_000 }), "watching_tv", t - 60_000); };
    const c = new CareCoach({ offsetMinutes: OFFSET });
    c.setHabits([MEDS]);
    ate(c);
    expect(c.cue(view({ now: t }), "watching_tv", t)).toMatchObject({ action: "약과 물 가져다주기", reason: "habit_essential" });
    expect(c.cue(view({ now: t + 250 }), "watching_tv", t + 250)).toBeNull();
    const o = new CareCoach({ offsetMinutes: OFFSET });
    o.setHabits([{ ...MEDS, importance: "optional" }]);
    ate(o);
    expect(o.cue(view({ now: t }), "watching_tv", t)).toMatchObject({ action: "사용자에게 물어보기", reason: "habit_ask" });
  });

  it("3. 식사를 마치고 약을 건너뛰고 방에 누우면 그 방으로 약과 물을 가져다준다", () => {
    const day = "2026-11-23";
    const c = new CareCoach({ offsetMinutes: OFFSET });
    c.setHabits([MEDS]);
    const t = at(day, 20, 6);
    c.observe(view({ now: t - 300_000, activity: "eating", room: "kitchen" }), "drinking", t - 300_000);
    const bed = view({ now: t, activity: "resting", posture: "lying", room: "bedroom", roomLabel: "침실" });
    c.observe(bed, "resting", t);
    const cue = c.cue(bed, "resting", t);
    expect(cue).toMatchObject({ action: "약과 물 가져다주기", reason: "habit_essential" });
    expect(cue!.observation).toContain("침실");
  });

  it("4. 약 먹을 시각인데 아직 식사를 하지 않았으면 식사부터 이끈다(컵과 접시 준비하기)", () => {
    const day = "2026-11-23";
    const c = new CareCoach({ offsetMinutes: OFFSET });
    c.setHabits([MEDS]);
    const t = at(day, 20, 5);
    const v = view({ now: t });
    c.observe(v, "watching_tv", t);
    expect(c.cue(v, "watching_tv", t)).toMatchObject({ action: "컵과 접시 준비하기", reason: "habit_meal_first" });
    // 이미 오늘 이끌었으면 같은 날 다시 이끌지 않는다
    expect(c.cue(v, "watching_tv", t + 250)).toBeNull();
    // 습관 시각 전에는 아무것도 하지 않는다
    const early = new CareCoach({ offsetMinutes: OFFSET });
    early.setHabits([MEDS]);
    expect(early.cue(view({ now: at(day, 19) }), "watching_tv", at(day, 19))).toBeNull();
  });

  it("중요도 생각 모델: 답의 importance를 읽고, 부르지 못하면 규칙으로 정한다", async () => {
    const ok = llmImportance({
      baseUrl: "http://qwen.test/v1", model: "qwen",
      fetch: (async () => new Response(JSON.stringify({ choices: [{ message: { content: '<think>…</think>{"importance": "optional", "reason": "x"}' } }] }))) as typeof fetch,
    });
    expect(await ok(MEDS, "")).toBe("optional");
    const down = llmImportance({ baseUrl: "http://qwen.test/v1", model: "qwen", fetch: (async () => { throw new Error("down"); }) as typeof fetch });
    expect(await down(MEDS, "")).toBe("essential");
  });
});

describe("판단에 붙인 코치모드", () => {
  it("냉장고 문이 열리면 PAM을 부르지 않고 그 판단으로 「컵과 접시 준비하기」를 고른다", async () => {
    let t = at("2026-11-23", 18);
    const clock = { now: () => t };
    const devices: WorldDevice[] = [];
    let calls = 0;
    const pam = { predict: async () => { calls++; return { observation: "o", reasoning: "r", task_index: -1, state: "away", from: null, next_index: -1 }; } } as unknown as PamClient;
    const decisions: DecisionRecord[] = [];
    const d = new Decider({
      pam, world: { view: (now) => view({ now, room: "kitchen", roomLabel: "주방", devices }) },
      trigger: new Trigger({ mode: "periodic", minGapMs: 3000, periodMs: 5000, idleStopMs: 1_800_000, liveMs: 10_000, maxInflight: 1 }, t),
      tasks: (heard) => pamTasks("coach", heard), memory: () => ({ memory: CARE_FSM_MEMORY, kind: "fsm", version: 1 }), emit: () => {}, offsetMinutes: OFFSET, clock,
      onDecision: (r) => decisions.push(r), care: new CareCoach({ offsetMinutes: OFFSET }),
    });
    d.onFrame();
    d.tick();
    await d.idle();
    expect(calls).toBe(1);
    t += 250;
    devices.push(fridge(true, t));
    d.onFrame();
    d.tick();
    await d.idle();
    expect(calls).toBe(1);
    const last = decisions.at(-1)!;
    expect(last).toMatchObject({ status: "valid", action: "컵과 접시 준비하기", care: "fridge_open", fsm: null });
    expect(last.tasks![last.prediction!.task_index]).toBe("컵과 접시 준비하기");
    // 버스 판단 메시지(/brain/decision 엄격한 모양)가 코치모드 까닭을 받는다(영상 시험에서 「Unrecognized key: care」로 판단이 사라졌다)
    const msg = TOPICS["/brain/decision"].body.safeParse({ decision: last, rev: 1, check: { ok: true }, assist: "coach", at_ms: t });
    expect(msg.success, JSON.stringify(msg.error?.issues)).toBe(true);
  });
});
