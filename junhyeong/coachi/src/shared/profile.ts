// 돕는 사람 프로필: 서버를 띄울 때 한 번 정한다(NOONCHI_PROFILE). 기본은 눈치모드(noonchi)다.
// care: 발달장애인 코치모드(코치모드 시나리오.txt). 눈치모드와 같은 집·같은 PAM을 쓰지만
//  - seed 사람 상태 FSM(src/brain/decision.ts CARE_FSM_MEMORY)과 행동 목록(src/act/tasks.ts CARE_TASKS)이 다르고,
//  - 가전 신호(냉장고 문 열림)·습관 시각(약 먹기)에서 관찰을 건너뛰고 바로 행동하며(src/brain/care/coach.ts),
//  - 계획이 끝나도 충전 자리로 돌아가지 않고 사용자 곁에서 지켜본다(src/act/robot/dock.ts).
// 프로필은 모듈을 읽을 때 정해진다: 시험은 setProfileForTest로 바꾼 뒤 그 값을 읽는 함수(isCare)만 쓴다.

export type Profile = "noonchi" | "care";

function read(env: Record<string, string | undefined>): Profile {
  const raw = env.NOONCHI_PROFILE?.trim().toLowerCase();
  if (!raw || raw === "noonchi") return "noonchi";
  if (raw === "care" || raw === "coach") return "care";
  throw new Error(`NOONCHI_PROFILE=${raw}: noonchi 또는 care여야 합니다`);
}

let current: Profile = read(typeof process !== "undefined" ? process.env : {});

/** 지금 프로필. */
export const profile = (): Profile => current;
/** 발달장애인 코치모드인가. */
export const isCare = (): boolean => current === "care";
/** 시험용: 프로필을 바꾼다(모듈을 읽을 때 정한 표는 바뀌지 않는다). */
export function setProfileForTest(p: Profile): void {
  current = p;
}
/** 모듈을 읽을 때 정해지는 표(행동 목록·seed 기억)가 쓰는 처음 프로필. */
export const BOOT_PROFILE: Profile = current;
