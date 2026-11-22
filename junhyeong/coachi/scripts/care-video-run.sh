#!/bin/bash
# 코치모드 영상 시험 한 묶음: 새 서버(9200·폰 9210, 이 PC는 8035~8534 포트가 막혀 있다)를 띄우고 이어진 영상들을 한 서버에서 차례로 돌린 뒤 서버를 끈다.
#   bash scripts/care-video-run.sh <묶음 이름> <영상1(.mp4 빼고)> [영상2 ...]
#   영상마다 video-check 옵션을 붙이려면 "영상|옵션들"(예: "appliance_part1|--twin 3:fridge_1:door=open"). RATE=0.5는 모든 영상 빠르기, CONTINUE_FIRST=1은 첫 영상도 --continue
# 기록: runtime/test-logs/server-<묶음>.log, check-<영상>.log. 시각표·대시보드 사진은 runtime/videos/<영상>.<시각>.timeline.md·twin.png
set -u
cd "$(dirname "$0")/.."
name=$1; shift
log=runtime/test-logs
mkdir -p "$log"
stop_server() {
  for p in $(netstat -ano | grep -E ":(9200|9210) .*LISTENING" | awk '{print $NF}' | sort -u); do taskkill //PID "$p" //T //F >/dev/null 2>&1; done
}
stop_server
PORT=9200 PHONE_PORT=9210 REFLECT_AT=off npx tsx src/server/main.ts > "$log/server-$name.log" 2>&1 &
ok=0
for i in $(seq 1 60); do curl -s -m 2 http://127.0.0.1:9200/api/health >/dev/null && { ok=1; break; }; sleep 2; done
if [ $ok = 0 ]; then echo "서버가 뜨지 않음"; stop_server; exit 3; fi
first=1
for spec in "$@"; do
  clip=${spec%%|*}; extra=(); [ "$spec" != "$clip" ] && read -r -a extra <<< "${spec#*|}"
  more=(); { [ $first = 0 ] || [ -n "${CONTINUE_FIRST:-}" ]; } && more=(--continue)
  NOONCHI_PROFILE=care npx tsx scripts/video-check.ts --clip "$clip.mp4" --api http://127.0.0.1:9200 --phone http://127.0.0.1:9210 --home apartment ${RATE:+--rate $RATE} "${more[@]}" "${extra[@]}" > "$log/check-$clip.log" 2>&1
  echo "$clip exit $?"
  grep -E "^판정|^VLM|timeline.md|기억" "$log/check-$clip.log"
  first=0
done
sleep 2
stop_server
echo "--- 서버 코치모드 줄"
grep -E "코치모드" "$log/server-$name.log" | head -30
