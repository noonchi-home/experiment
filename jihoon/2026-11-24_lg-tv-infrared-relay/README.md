# 실제 LG TV를 적외선으로 켜고 끄기, 와이파이로 상태 읽기 (2026-11-21 ~ 11-24)

## 요약

최종 시연 시나리오 1(6·10·11단계)에서는 동료 집의 실제 TV(LG 47LM6700, 2012년 NetCast 3.0)를 켜고 끄고, 리모컨으로 켠 것도 알아채야 한다. 조사해 보니 이 TV는 ThinQ·Matter로는 조종할 수 없었다.

그래서 아래 구조를 만들었다.
- **켜기·끄기:** 아두이노 적외선
- **켜짐·꺼짐 확인:** TV 와이파이 응답(NetCast 8080 포트)

가짜 TV·가짜 아두이노로 시험 22개가 통과했고, 눈치서버와도 이어 봤다. 11-24에는 실제 부품을 조립했고, 노트북 → 아두이노 → 적외선 쏘기와 리모컨 신호 받기가 둘 다 됐다.

그 사이 눈치서버 main에 허정오의 적외선 TV 경로(`901c6602`)가 들어갔다. 그래서 **이 실험은 그 경로에 "와이파이로 전원 확인"을 더하는 쪽으로 합치기를 권한다.** 방법은 아래 [눈치서버 main에 합치는 법](#눈치서버-main에-합치는-법)에 적었다.

## 왜 했나

- 시나리오 문서에는 "ThinQ API로 TV를 끈다/켠다"고 적혀 있었다. 실제로 되는지 확인해야 했다.
- 확인 결과
  - **ThinQ:** ThinQ Connect 공개 API에는 TV 기기 종류가 없다(`pythinqconnect` 소스로 확인).
  - **Matter:** LG·삼성 TV는 Matter 컨트롤러(조종하는 쪽)이고, 조종받는 기기로 나오지 않는다.
  - **와이파이(NetCast ROAP):** 끄기와 상태 읽기는 된다. **켜기는 안 된다.** TV가 대기 상태가 되면 와이파이 칩도 꺼지기 때문이다.
  - **적외선:** 대기 중에도 수신부가 살아 있어서 켜기·끄기가 다 된다. 다만 상태는 읽지 못한다.
- 그래서 **적외선(쏘기) + 와이파이(확인)** 를 묶었다.

## 한 것

### 1. 동료 TV 확인 (11-22, 장비 없이 팀원이 직접)
| # | 확인할 것 | 결과 |
|---|---|---|
| 1 | 리모컨이 적외선인지 (폰 카메라) | 적외선 |
| 2 | TV 적외선 수신부 위치 | 오른쪽 아래 |
| 3 | 대기 상태에서 리모컨으로 켜지는지 | 켜짐 |
| 4 | 셋톱 리모컨으로 TV가 켜지는지 | 켜짐 → 표준 LG 적외선 신호(NEC 주소 0x04)를 받는다 |
| 5 | TV를 켜면 셋톱도 켜지는지 | 안 켜짐 → 셋톱 전원 신호도 따로 쏴야 한다 |
| 6 | 켜지는 데 걸리는 시간 | 화면까지 5~6초 |
| 7 | 모델 스티커 | 47LM6700, 2012.10 |

### 2. 부품 (디바이스마트, 약 8,000원 + 배송비)
| 부품 | 모델 |
|---|---|
| 보드 | 우노 R3 호환 USB-C CH340 [CMODULE-39]. **받아 보니 칩이 LGT8F328** |
| 송신 모듈 | YwRobot 더블헤드 적외선 송신 [ELB030103] (DAT·VCC·GND, 5V) |
| 수신 모듈 | KEYES 적외선 수신 [KY0022] (S·+·-, 38kHz) |
| 점퍼선 | KEYES M/F 20cm [CH254] |

배선은 아래와 같다. 허정오 펌웨어(`hardware/ir-tv`)와 핀이 같다.
```
송신  DAT → D3   VCC → 5V    GND → GND
수신  S   → D2   +   → 3.3V  -   → GND
```

### 3. 중계 노트북 프로그램 (`code/tvrelay/`, Python, 의존성은 pyserial만)
| 파일 | 하는 일 |
|---|---|
| `netcast.py` | NetCast ROAP(8080, 예비 60128). 페어링(TV 화면 번호), 끄기, 볼륨, 기기 정보(UDAP). `reachable()`: TCP 연결이 되면 켜짐 |
| `monitor.py` | 0.5초마다 `reachable()`. **2번 연속 실패하면 꺼짐.** 바뀐 시각을 남기고, 원하는 상태가 될 때까지 기다린다(`wait_for`) |
| `ir.py` | 아두이노 시리얼 브리지. `power_to()`: 켜기 전용 0xC4 / 끄기 전용 0xC5를 쏘고 와이파이로 확인한다. 안 바뀌면 토글 0x08로 다시 쏜다 |
| `codes.py` | 방식을 모르는 리모컨(구형 에어컨·셋톱)을 **원본 길이 그대로** 녹음·저장한다(50us 단위, 최대 750칸) |
| `server.py` | 중계 HTTP 서버(Bearer 토큰). `GET /api/devices/tv`, `POST /api/devices/tv/command {type: on/off}` → `done / unverified / failed / not_sent` |
| `fake.py` | 가짜 TV(꺼지면 포트를 닫는다)와 가짜 아두이노 |
| `arduino/ir_bridge/ir_bridge.ino` | IRremote 5.x. `NEC`·`ON`·`OFF`·`PWR`·`RAW`·`RAWON/RAWOFF`·`PING` |

### 4. 눈치서버 쪽 중계 연결 (`code/noonchi-relay/feat-tv-relay.diff`)
- 눈치서버 `76f26a1a` 위에 만든 브랜치 `feat/tv-relay`의 전체 diff다(16개 파일, +708/-43).
- `src/devices/relay/`(`RelayClient`, `RelayLink`)와 신호 출처 `relay`를 더했다. `ThinqLink`와 같은 모양이다.
- 설정: `TV_RELAY_URL`, `TV_RELAY_TOKEN`, `TV_RELAY_DEVICE`
- 시험 15개를 더했다. 전체 2,937개가 통과했고, `shared-paths`의 Windows 대소문자 시험 1개만 원래부터 실패한다.

## 결과

| 시험 | 결과 |
|---|---|
| 가짜 TV·가짜 아두이노 단위 시험 (`code/tests`) | 22개 통과 |
| 중계 서버(`--fake`) + 눈치서버 `RelayLink` 이어 보기 | 켜기 3.5초, 끄기 1.5초 만에 `done`. 트윈 TV 상태도 따라 바뀜 |
| 실제 보드에 스케치 올리기 (11-24) | 컴파일·업로드 됨. `ready ir_bridge raw=750` |
| 실제 쏘기 (11-24) | `PWR` → `ok sent NEC 0x4 0x8` |
| 실제 받기 (11-24) | `python -m tvrelay learn`에서 리모컨 신호가 찍힘 |
| 동료 집 TV | **아직 안 함** |

## 알게 된 것

- **호환 보드 칩이 LGT8F328일 수 있다.** "Arduino Uno"로 고르면 안 올라가거나 박자가 틀어질 수 있다.
  - 보드 관리자 URL: `https://raw.githubusercontent.com/dbuezas/lgt8fx/master/package_lgt8fx_index.json`
  - 보드 `LGT8F328`, Clock Source `Internal 32MHz`, Clock Divider `2`(16MHz), Upload `57600`, Variant `328P-LQFP32`
  - 핀·메모리(2KB)는 우노와 같아서 코드와 배선은 그대로 쓴다.
- 맥에서 포트가 안 보이면 대개 선 문제(충전 전용 선, 허브)다. 다시 꽂아 바로 연결하니 `/dev/cu.usbserial-*`로 잡혔다.
- 아이폰 **뒷면** 카메라는 적외선을 걸러서 송신 LED가 안 보인다. NEC 한 번은 약 0.07초이기도 하다. 셀카 카메라나 수신 모듈 불빛으로 확인하는 게 낫다.
- 2012 NetCast는 꺼지면 포트가 닫히고, 켜지면 몇 초 뒤 열린다. **밝기 센서 없이도 와이파이만으로 전원 확인이 된다.** 단, 화면보다 늦게 열린다(시간은 실제 TV에서 재야 함).

## 눈치서버 main에 합치는 법

main(`365f0353` 기준)에는 이미 허정오의 적외선 TV 경로가 있다.
- 서버가 집 노트북에서 아두이노를 직접 잡는다.
- 코드: `src/devices/hub/ir.ts`의 `IrTv`, `ir-config.ts`, `ir-serial.ts`, `hardware/ir-tv/ir_tv.ino`
- 확인 수단: 밝기 센서 또는 카메라 근거

`feat-tv-relay.diff`를 그대로 합치면 5개 파일이 충돌한다(`signals.ts`, `contract/devices.ts`, `start.ts`, `home/devices.ts`, `home/index.ts`). 합쳐도 TV 경로가 둘이 된다. 그래서 **diff는 합치지 말고, main 경로에 아래만 더하기를 권한다.**

### 1. 와이파이 응답을 전원 확인 수단으로 (밝기 센서 대신)
우리 장비에는 밝기 센서가 없다. 대신 이 TV는 켜져 있을 때만 8080 포트가 열린다.
- **`ir-config.ts`:** `irSettings`에 선택 필드 `net: { host: string, ports?: number[] }`를 더한다. 기본 포트는 `[8080, 60128]`이다.
- **새 파일 `ir-net.ts`:** 0.5초마다 `node:net`으로 포트에 연결해 본다.
  - 연결되면 `on`이다.
  - **2번 연속 실패하면** `off`다.
  - 규칙은 `code/tvrelay/monitor.py`, `netcast.reachable()`와 같다.
- **`ir.ts`:** `IrTv`에 `net(power, at)`를 더한다.
  - `light()`처럼 `confirm(power, since, at)`를 부른다.
  - 토글 조건 `lightKnown`을 "밝기 **또는** 와이파이로 최근에 아는 상태"로 넓힌다.
- **확인 시간:** 와이파이는 화면보다 늦게 열린다(화면 5~6초 + 네트워크). 그래서 이 집 `ir.json`의 `confirmOnMs`는 15000(최댓값)을 권한다.

```ts
// ir-net.ts 초안 (시험 전). monitor.py와 같은 규칙.
import { Socket } from "node:net";
export function probeNet(host: string, ports: number[], report: (p: "on" | "off", at: number) => void) {
  let misses = 0, stopped = false;
  const tryPort = (port: number) => new Promise<boolean>(ok => {
    const s = new Socket(); const done = (v: boolean) => { s.destroy(); ok(v); };
    s.setTimeout(400); s.once("connect", () => done(true)); s.once("timeout", () => done(false)); s.once("error", () => done(false));
    s.connect(port, host);
  });
  const tick = async () => {
    if (stopped) return;
    let up = false; for (const p of ports) if ((up = await tryPort(p))) break;
    misses = up ? 0 : misses + 1;
    if (up) report("on", Date.now()); else if (misses >= 2) report("off", Date.now());
    setTimeout(tick, 500);
  };
  void tick();
  return () => { stopped = true; };
}
```

### 2. 펌웨어와 리모컨 코드
- 펌웨어는 main의 `hardware/ir-tv/ir_tv.ino`를 쓴다. `HAS_LIGHT_SENSOR = false`로 올린다. LGT8F328이면 위의 보드 설정을 쓴다.
- 이 TV의 코드를 `ir_tv.ino` 형식으로 쓰면 아래와 같다. `ir-learn.ts`로 배워서 맞는지 확인한다.

| 키 | 코드 | 상태 |
|---|---|---|
| 토글 | `NEC:0004:08` | 확인됨(LG 공통) |
| 켜기 전용 | `NEC:0004:C4` | 이 TV에서 먹는지는 아직 모름 |
| 끄기 전용 | `NEC:0004:C5` | 이 TV에서 먹는지는 아직 모름 |

### 3. 맥에서 서버를 돌릴 경우 (선택)
- `ir-serial.ts`는 `win32` 전용이고, `ir-config.ts`의 포트 규칙은 `^COM\d+$`만 받는다.
- 동료 집 노트북이 Windows면 그대로 쓴다.
- 맥에서 돌리려면 아래처럼 바꾸면 의존성 없이 된다.
  - darwin에서 `stty -f <port> 115200 raw -echo`를 실행한다.
  - `/dev/cu.*`를 `fs` 읽기·쓰기 스트림으로 연다.
  - 포트 규칙에 `/dev/cu.*`를 더한다.

### 4. 셋톱
- TV를 켜도 셋톱은 같이 안 켜진다(확인 5번). main 경로는 TV 전원 키만 다룬다.
- 시나리오는 TV 전원만 보면 되니 이번엔 빼고 팀과 정한다.
- 셋톱 리모컨이 해석되지 않는 방식이면 `code/tvrelay/codes.py`처럼 원본 녹음이 필요하다.

### 서버가 EC2에 있고 TV가 다른 집에 있을 때
그때는 `feat-tv-relay.diff`의 중계 방식(Tailscale + `tvrelay serve`)이 맞다. 지금 main은 서버가 집 노트북에서 도는 방식이라 필요 없다.

## 한계와 다음 할 일
- 동료 집 TV로는 아직 시험하지 않았다. 할 일:
  1. `learn`으로 TV 신호를 본다.
  2. 켜기·끄기 전용 코드가 먹는지 본다.
  3. 와이파이 연결 여부를 확인하고 페어링한다.
  4. 와이파이가 몇 초 만에 열리는지 잰다.
- TV가 와이파이에 연결돼 있지 않으면 와이파이 확인은 못 쓴다. 그때는 밝기 센서(main 경로)나 카메라로 확인한다.
- 원본 녹음은 750칸까지이고, 한 칸은 최대 12.75ms다. 그보다 긴 쉼은 잘린다.

## 파일
| 경로 | 내용 |
|---|---|
| `code/tvrelay/` | 중계 노트북 프로그램(Python)과 아두이노 스케치 |
| `code/tests/` | 가짜 TV·가짜 아두이노 시험 22개 (`pip install -r code/requirements.txt` 뒤 `cd code && python -m pytest -q tests`) |
| `code/noonchi-relay/feat-tv-relay.diff` | 눈치서버 `76f26a1a` 기준 중계 연결 diff (참고용) |

실행 예 (`code/` 안에서):
```bash
python -m tvrelay learn  --ir-port /dev/cu.usbserial-XXXX          # 리모컨 신호 보기
python -m tvrelay record --ir-port /dev/cu.usbserial-XXXX stb_power  # 원본 녹음
python -m tvrelay send   --ir-port /dev/cu.usbserial-XXXX stb_power  # 녹음한 신호 쏘기
python -m tvrelay pair   --tv-host <TV IP>                           # 와이파이 페어링
TV_RELAY_TOKEN=<16자 이상> python -m tvrelay serve --fake            # 가짜 장비로 중계 서버
```
