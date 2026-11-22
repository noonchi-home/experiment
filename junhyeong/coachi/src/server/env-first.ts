// .env를 다른 모듈보다 먼저 읽는다(main.ts의 첫 import). 모듈을 읽을 때 정하는 값(NOONCHI_PROFILE → src/shared/profile.ts BOOT_PROFILE,
// 코치모드 행동 목록·seed 기억)이 .env 값을 보게 한다. 셸 값이 .env보다 앞선다(dotenv 기본).
import dotenv from "dotenv";

dotenv.config({ quiet: true });
