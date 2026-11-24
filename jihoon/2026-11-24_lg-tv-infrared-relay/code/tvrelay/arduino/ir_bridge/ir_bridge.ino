// 적외선 브리지: 노트북(USB 시리얼 115200)이 시키는 대로 적외선을 쏘고, 리모컨 신호를 받으면 알려 준다.
// 보드: 아두이노 우노·나노(호환보드 OK). 라이브러리: IRremote 5.x (Arduino IDE → 라이브러리 매니저 → "IRremote").
//
// 배선
//   적외선 송신 모듈(DAT/S → D3, VCC/+ → 5V, GND/- → GND)
//   적외선 수신 모듈(S/OUT → D2, + → 3.3V 또는 5V, - → GND)
//
// 명령 (한 줄씩, 끝에 줄바꿈)
//   NEC <주소> <명령> [반복]      예) NEC 0x4 0xC4 0   → "ok sent NEC 0x4 0xC4"   (LG TV 등)
//   ON / OFF / PWR                LG TV 켜기 전용(0xC4) / 끄기 전용(0xC5) / 전원 토글(0x08)
//   RAW <kHz> <n> <t1> ... <tn>    원본 신호 재생. t는 50us 단위 길이, 켜짐(mark)부터 번갈아. → "ok sent RAW n"
//   RAWON / RAWOFF                 받은 신호를 원본(RXRAW)으로도 알릴지 (구형 에어컨·셋톱처럼 방식을 모르는 리모컨 녹음용)
//   PING                           → "ok pong"
// 알림
//   "ready ir_bridge raw=<버퍼 칸 수>"
//   "RX NEC 0x4 0x8"               해석한 신호(반복 신호·모르는 방식은 뺌)
//   "RXRAW <n> <t1> ... <tn>"      RAWON일 때 원본(50us 단위). 버퍼를 넘치면 "RXOVF"
//
// 메모리(우노 2KB): 받는 원본 버퍼 750칸(바이트)을 보낼 때도 같이 쓴다(보내는 동안 받기를 멈춤).

#define RAW_BUFFER_LENGTH 750      // 에어컨 리모컨 길이(라이브러리 권장값)
#define RECORD_GAP_MICROS 12000    // 에어컨 신호 안의 긴 쉼(8ms 넘음)에서 끊기지 않게. 8비트 칸 최대(12.75ms)보다 작게
#define IR_SEND_PIN 3
#define IR_RECEIVE_PIN 2
#include <IRremote.hpp>

const uint16_t LG_ADDR = 0x04;
bool rawReport = false;
char line[40];                     // 짧은 명령 한 줄(RAW는 줄을 모으지 않고 바로 읽는다)
uint8_t lineLen = 0;

void sendNec(uint16_t addr, uint8_t cmd, uint8_t rep) {
  IrSender.sendNEC(addr, cmd, rep);
  Serial.print(F("ok sent NEC 0x"));
  Serial.print(addr, HEX);
  Serial.print(F(" 0x"));
  Serial.println(cmd, HEX);
}

// 시리얼에서 숫자 하나를 읽는다(공백 건너뜀). 줄 끝이면 -1, 시간 초과면 -2.
long readNumber() {
  long v = 0;
  bool any = false;
  unsigned long t0 = millis();
  while (millis() - t0 < 500) {
    int c = Serial.peek();
    if (c < 0) continue;
    if (c == '\r' || c == '\n') {
      if (!any) { Serial.read(); return -1; }
      return v;
    }
    Serial.read();
    t0 = millis();
    if (c >= '0' && c <= '9') { v = v * 10 + (c - '0'); any = true; }
    else if (any) return v;                 // 공백 = 숫자 끝
  }
  return any ? v : -2;
}

void skipLine() {
  unsigned long t0 = millis();
  while (millis() - t0 < 500) {
    int c = Serial.read();
    if (c == '\n') return;
    if (c >= 0) t0 = millis();
  }
}

// "RAW " 뒤를 바로 읽어 받는 버퍼에 채우고 쏜다
void handleRaw() {
  long khz = readNumber();
  long n = readNumber();
  if (khz < 30 || khz > 60 || n < 1 || n > RAW_BUFFER_LENGTH) { skipLine(); Serial.println(F("err bad raw header")); return; }
  IrReceiver.stop();
  uint8_t *buf = IrReceiver.irparams.rawbuf;
  for (long i = 0; i < n; i++) {
    long t = readNumber();
    if (t < 1 || t > 255) { skipLine(); IrReceiver.start(); Serial.println(F("err bad raw value")); return; }
    buf[i] = (uint8_t)t;
  }
  skipLine();
  IrSender.sendRaw(buf, (uint_fast16_t)n, (uint_fast8_t)khz);
  IrReceiver.start();
  Serial.print(F("ok sent RAW "));
  Serial.println(n);
}

void handleLine() {
  line[lineLen] = 0;
  char *s = line;
  while (*s == ' ') s++;
  if (!*s) return;
  if (!strcmp(s, "PING")) { Serial.println(F("ok pong")); return; }
  if (!strcmp(s, "ON"))  { sendNec(LG_ADDR, 0xC4, 0); return; }
  if (!strcmp(s, "OFF")) { sendNec(LG_ADDR, 0xC5, 0); return; }
  if (!strcmp(s, "PWR")) { sendNec(LG_ADDR, 0x08, 0); return; }
  if (!strcmp(s, "RAWON"))  { rawReport = true;  Serial.println(F("ok raw on")); return; }
  if (!strcmp(s, "RAWOFF")) { rawReport = false; Serial.println(F("ok raw off")); return; }
  if (!strncmp(s, "NEC ", 4)) {
    char *p = s + 4, *end;
    long addr = strtol(p, &end, 0);
    if (end == p) { Serial.println(F("err bad address")); return; }
    p = end;
    long cmd = strtol(p, &end, 0);
    if (end == p) { Serial.println(F("err bad command")); return; }
    p = end;
    long rep = strtol(p, &end, 0);
    if (end == p) rep = 0;
    sendNec((uint16_t)addr, (uint8_t)cmd, (uint8_t)constrain(rep, 0, 5));
    return;
  }
  Serial.println(F("err unknown"));
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') { handleLine(); lineLen = 0; continue; }
    if (lineLen < sizeof(line) - 1) line[lineLen++] = c;
    // "RAW "까지 왔으면 숫자는 줄에 모으지 않고 바로 읽는다(수천 글자라 줄 버퍼에 안 들어감)
    if (lineLen == 4 && !strncmp(line, "RAW ", 4)) { handleRaw(); lineLen = 0; }
  }
}

void reportRaw() {
  if (IrReceiver.decodedIRData.flags & IRDATA_FLAGS_WAS_OVERFLOW) { Serial.println(F("RXOVF")); return; }
  uint16_t n = IrReceiver.irparams.rawlen;  // rawbuf[0]은 비어 있음(옛 호환), 1부터 켜짐·꺼짐 번갈아
  if (n < 4) return;
  Serial.print(F("RXRAW "));
  Serial.print(n - 1);
  for (uint16_t i = 1; i < n; i++) {
    Serial.print(' ');
    Serial.print(IrReceiver.irparams.rawbuf[i]);
  }
  Serial.println();
}

void setup() {
  Serial.begin(115200);
  IrReceiver.begin(IR_RECEIVE_PIN, DISABLE_LED_FEEDBACK);
  IrSender.begin();
  Serial.print(F("ready ir_bridge raw="));
  Serial.println(RAW_BUFFER_LENGTH);
}

void loop() {
  readSerial();
  if (IrReceiver.decode()) {
    IRData &d = IrReceiver.decodedIRData;
    if (rawReport) reportRaw();
    if (!(d.flags & IRDATA_FLAGS_IS_REPEAT) && d.protocol != UNKNOWN) {
      Serial.print(F("RX "));
      Serial.print(getProtocolString(d.protocol));
      Serial.print(F(" 0x"));
      Serial.print(d.address, HEX);
      Serial.print(F(" 0x"));
      Serial.println(d.command, HEX);
    }
    IrReceiver.resume();
  }
}
