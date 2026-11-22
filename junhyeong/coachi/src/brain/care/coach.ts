// 발달장애인 코치모드 규칙(코치모드 시나리오.txt). 판단(src/brain/decide.ts)이 PAM을 부르기 전에 묻는다:
// cue가 행동을 내면 PAM을 부르지 않고 그 행동으로 판단 기록을 만든다(관찰 과정을 건너뛴다). 사람 상태는 holdState로 보수적으로 바꾼다.
//
// 가전 트리거 시나리오
//  1. 냉장고 문 열림 → 바로 「컵과 접시 준비하기」(폰에 「주방 입구로 이동해 주세요」가 첫 명령으로 뜬다). 이미 먹는 중이면 하지 않는다.
//  2. 식사 중 자리 비움 → PAM FSM 화살표(식사 중 유지 + 「사용자 곁에서 지켜보기」, src/brain/decision.ts CARE_FSM_MEMORY). 음식이 남았으면 상태는 식사 중을 지킨다(holdState).
//  3. 남긴 채 TV → PAM FSM 화살표 「남은 음식 가져다주기」(마저 먹을지 묻고, 답은 다음 판단의 들은 말로 상태를 바꾼다).
//  4·5. 다 먹고 TV → PAM FSM 화살표 「컵 치우기」(묻지 않음, 눈치모드와 같은 정리).
//  6. 계획이 끝나도 충전 자리로 가지 않고 사용자 곁으로 간다(src/act/robot/dock.ts). 사용자가 방을 옮기면 따라간다(follow).
// 사용자 습관 기반 시나리오
//  1. 습관 활동(약 먹기)을 날마다 기록하고(observe), 날이 바뀌면 자기 반성으로 습관과 중요도를 정한다(src/brain/care/habits.ts).
//  2. 필수 습관은 시각이 되면 묻지 않고 돕고, 생략 가능 습관은 먼저 묻는다(눈치모드와 같다).
//  3. 식사를 마치고 약을 건너뛰고 방에 누우면 → 「약과 물 가져다주기」(사용자가 있는 방으로).
//  4. 약 먹을 시각인데 아직 식사를 하지 않았으면 → 약보다 먼저 「컵과 접시 준비하기」로 식사를 이끈다.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import type { FsmStep } from "../../contract/pam.js";
import type { WorldView } from "../../contract/world.js";
import { KINDS, type DeviceKind } from "../../devices/kinds.js";
import { hhmm, reflectHabits, ruleImportance, HABIT_ACTIVITIES, type ActivityEvent, type CareHabit, type ImportanceJudge } from "./habits.js";

/** 코치모드 규칙이 행동을 낸 까닭. */
export type CareReason = "fridge_open" | "habit_meal_first" | "habit_essential" | "habit_ask" | "follow";

/** 코치모드 규칙이 낸 행동: 행동 이름, 까닭, 판단 기록에 남길 관찰·생각 글. */
export interface CareCue { action: string; reason: CareReason; observation: string; reasoning: string }

/** 습관 저장소(없으면 메모리에만 둔다). */
export interface HabitStore { load(): { habits: CareHabit[]; events: ActivityEvent[] } | null; save(v: { habits: CareHabit[]; events: ActivityEvent[] }): void }

/** JSON 파일 습관 저장소. */
export function fileHabitStore(path: string): HabitStore {
  return {
    load: () => {
      try { return JSON.parse(readFileSync(path, "utf8")) as { habits: CareHabit[]; events: ActivityEvent[] }; } catch { return null; }
    },
    save: (v) => {
      mkdirSync(dirname(path), { recursive: true });
      writeFileSync(path, JSON.stringify(v, null, 2));
    },
  };
}

/** 사용자를 따라갈 때 두는 최소 간격(ms)과 기록을 두는 날 수, 습관 시각 뒤 도움을 그만두는 분. */
export const CARE = { followGapMs: 60_000, keepDays: 14, habitLateMin: 180 } as const;

/** 식사를 이끄는 행동과 사용자 곁에서 지켜보는 행동, 묻는 행동(행동 목록 이름). */
export const CARE_ACTIONS = { prepare: "컵과 접시 준비하기", follow: "사용자 곁에서 지켜보기", food: "남은 음식 가져다주기", ask: "사용자에게 물어보기" } as const;

export interface CareCoachOptions {
  /** 관찰 텍스트·기록 DB와 같은 시간대(분). */
  offsetMinutes: number;
  /** 사전 입력받은 사용자 정보(보호자가 적는다, CARE_USER_INFO). 습관 중요도 판단에 쓴다. */
  userInfo?: string;
  judge?: ImportanceJudge;
  store?: HabitStore;
  /** 반성 결과·규칙 사건 기록(없으면 버린다). */
  log?: (line: string) => void;
}

/** 남은 음식: 사라지지 않고 싱크대에 넣지 않은 그릇 가운데 비었다고 확인되지 않은 것이 있다. */
export function foodLeft(view: Pick<WorldView, "objects">): boolean {
  return view.objects.some((o) => o.cls === "bowl" && o.status !== "gone" && o.facts.place?.value !== "in_sink"
    && !(o.facts.contents?.value === "empty" && o.facts.contents.certainty === "confirmed"));
}

export class CareCoach {
  private habits: CareHabit[] = [];
  private events: ActivityEvent[] = [];
  private day: string | null = null;
  /** 오늘 식사: 먹는 것을 봤는가, 식사가 끝났는가. */
  private meal = { ate: false, ended: false };
  /** 오늘 이미 낸 규칙 행동(습관 id:종류). */
  private cued = new Set<string>();
  /** 오늘 한 습관 활동. */
  private done = new Set<string>();
  private prevState: string | null = null;
  private fridgeSeen = Number.NEGATIVE_INFINITY;
  private lastRoom: string | null = null;
  private followAt = Number.NEGATIVE_INFINITY;
  private reflecting: Promise<void> | null = null;

  constructor(private readonly o: CareCoachOptions) {
    const saved = o.store?.load();
    if (saved) {
      this.habits = saved.habits ?? [];
      this.events = saved.events ?? [];
    }
  }

  /** 지금 배운 습관. */
  habitsNow(): readonly CareHabit[] {
    return this.habits;
  }

  /** 시험·보호자 입력용: 습관을 바로 둔다. */
  setHabits(habits: CareHabit[]): void {
    this.habits = habits;
    this.save();
  }

  /** 판단 타이머마다(PAM 판단 전): 날 바뀜(반성), 식사, 습관 활동을 기록한다. state는 마지막 판단의 사람 상태다. */
  observe(view: WorldView, state: string | null, now: number): void {
    const { day, minute } = this.local(now);
    if (this.day !== day) {
      if (this.day !== null) this.reflect();
      this.day = day;
      this.meal = { ate: false, ended: false };
      this.cued.clear();
      this.done.clear();
    }
    const activity = view.person.visible ? (view.person.facts.activity?.value as string | undefined) : undefined;
    if (state === "drinking" || activity === "eating") this.meal = { ate: true, ended: false };
    // 식사 끝: 사람 상태가 식사 중에서 다른 상태로 넘어갔다(holdState를 지난 바뀜이라 실제 끝이다)
    if (this.prevState === "drinking" && state !== null && state !== "drinking") this.meal = { ate: true, ended: true };
    this.prevState = state;
    if (activity && HABIT_ACTIVITIES[activity] && !this.done.has(activity)) {
      this.done.add(activity);
      this.events = [...this.events, { day, minute, activity, afterMeal: this.meal.ended }].filter((e) => daysBetween(e.day, day) < CARE.keepDays);
      this.o.log?.(`코치모드 기록: ${day} ${hhmm(minute)} ${HABIT_ACTIVITIES[activity]!.label}`);
      this.save();
    }
  }

  /** PAM을 부르기 전 규칙: 행동을 내면 판단은 PAM 없이 그 행동을 고른다(관찰을 건너뛴다). 없으면 null(PAM이 FSM으로 정한다). */
  cue(view: WorldView, state: string | null, now: number): CareCue | null {
    const { day, minute } = this.local(now);
    // 가전 트리거 1: 냉장고 문이 새로 열렸다
    const fridge = view.devices.find((d) => mealCue(d.kind) && d.state.includes("door_open") && (d.event_ms ?? d.changed_ms) > this.fridgeSeen);
    if (fridge) {
      this.fridgeSeen = fridge.event_ms ?? fridge.changed_ms;
      if (state !== "drinking") {
        return {
          action: CARE_ACTIONS.prepare, reason: "fridge_open", observation: `${fridge.label} 문이 열렸다.`,
          reasoning: "코치모드: 냉장고 문 열림은 식사의 시작 신호라 관찰을 건너뛰고 바로 주방 입구로 가서 컵과 접시를 준비해 식사를 이끈다.",
        };
      }
    }
    // 습관
    for (const h of this.habits) {
      if (minute < h.minute || minute > h.minute + CARE.habitLateMin || this.done.has(h.activity)) continue;
      const key = `${day}:${h.id}`;
      if (h.importance === "essential") {
        // 돌발행동 4: 약 먹을 시각인데 식사를 아직 하지 않았다 → 식사부터 이끈다
        if (h.afterMeal && !this.meal.ended) {
          if (this.meal.ate || state === "drinking" || this.cued.has(`${key}:meal`)) continue;
          this.cued.add(`${key}:meal`);
          return {
            action: CARE_ACTIONS.prepare, reason: "habit_meal_first", observation: `${hhmm(minute)}, ${h.label} 시각인데 오늘 식사가 끝나지 않았다.`,
            reasoning: `코치모드: ${h.label}(필수)는 식사 뒤에 하는 습관이라, 먼저 컵과 접시를 사용자에게 전달해 식사를 이끈다.`,
          };
        }
        if (this.cued.has(`${key}:bring`)) continue;
        this.cued.add(`${key}:bring`);
        const where = view.person.room_label ?? "사용자가 있는 곳";
        return {
          action: h.action, reason: "habit_essential", observation: `${hhmm(minute)}, ${h.label} 시각(평소 ${hhmm(h.minute)})인데 아직 하지 않았다. 사용자는 ${where}에 있다.`,
          reasoning: `코치모드: ${h.label}는 필수 습관이라 묻지 않고 ${where}(으)로 가져다준다.`,
        };
      }
      // 생략 가능 습관: 눈치모드처럼 먼저 묻는다
      if (this.cued.has(`${key}:ask`)) continue;
      this.cued.add(`${key}:ask`);
      return {
        action: CARE_ACTIONS.ask, reason: "habit_ask", observation: `${hhmm(minute)}, 평소 ${h.label} 시각이다.`,
        reasoning: `코치모드: ${h.label}는 생략할 수 있는 습관이라 먼저 사용자에게 물어본다.`,
      };
    }
    // 사용자가 방을 옮겼다 → 따라가 지켜본다(식사 중 자리 비움은 PAM FSM 화살표가 본다)
    const room = view.person.visible ? view.person.room : null;
    const moved = room !== null && this.lastRoom !== null && room !== this.lastRoom;
    if (room !== null) this.lastRoom = room;
    if (moved && state !== "drinking" && now - this.followAt >= CARE.followGapMs) {
      this.followAt = now;
      return {
        action: CARE_ACTIONS.follow, reason: "follow", observation: `사용자가 ${view.person.room_label ?? room}(으)로 옮겼다.`,
        reasoning: "코치모드: 관찰에서 벗어나는 때를 줄이려고 사용자를 따라가 가까이에서 지켜본다.",
      };
    }
    return null;
  }

  /** 사람 상태를 보수적으로 바꾼다: 식사 중에서 화살표 없이 다른 상태로 보였는데 음식이 남았으면 식사 중을 지킨다
   *  (자리를 잠시 비우거나 TV를 켠 것은 식사 끝이 아닐 수 있다). 화살표가 있는 바뀜(다 먹음·그만 먹겠다는 답)은 받는다. */
  holdState(prev: string | null, step: Pick<FsmStep, "state" | "from">, view: Pick<WorldView, "objects">): string {
    if (prev === "drinking" && step.state !== "drinking" && step.from === null && foodLeft(view)) return "drinking";
    return step.state;
  }

  /** 자기 반성: 기록에서 습관을 다시 배우고 중요도를 정한다(날이 바뀔 때). */
  reflect(): Promise<void> {
    // 앞선 반성이 끝난 뒤 그때 기록으로 다시 한다(늦게 끝난 앞 반성이 새 습관을 덮지 않게)
    const run = (): Promise<void> => reflectHabits([...this.events], this.o.userInfo ?? "", this.o.judge ?? ruleImportance)
      .then((habits) => {
        this.habits = habits;
        this.o.log?.(`코치모드 반성: 습관 ${habits.map((h) => `${h.label} ${hhmm(h.minute)} ${h.importance === "essential" ? "필수" : "생략 가능"}`).join(", ") || "없음"}`);
        this.save();
      })
      .catch((e: unknown) => { this.o.log?.(`코치모드 반성 실패: ${(e as Error).message}`); });
    const job: Promise<void> = (this.reflecting ?? Promise.resolve()).then(run).finally(() => { if (this.reflecting === job) this.reflecting = null; });
    this.reflecting = job;
    return job;
  }

  private save(): void {
    this.o.store?.save({ habits: this.habits, events: this.events });
  }

  private local(now: number): { day: string; minute: number } {
    const d = new Date(now + this.o.offsetMinutes * 60_000);
    return { day: d.toISOString().slice(0, 10), minute: d.getUTCHours() * 60 + d.getUTCMinutes() };
  }
}

/** 등록부에서 식사 신호 가전(mealCue)인가. */
const mealCue = (kind: string): boolean => Object.hasOwn(KINDS, kind) && KINDS[kind as DeviceKind].mealCue === true;

const daysBetween = (a: string, b: string) => Math.round((Date.parse(b) - Date.parse(a)) / 86_400_000);
