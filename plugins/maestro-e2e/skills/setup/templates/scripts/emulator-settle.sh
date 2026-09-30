#!/usr/bin/env bash
# 에뮬레이터가 부팅 직후 밀린 작업을 끝내고 조용해질 때까지 기다린다.
#
# sys.boot_completed=1은 "부팅이 끝났다"일 뿐 "한가하다"가 아니다. 그 직후에는 GMS 초기화와 dexopt가
# CPU와 패키지 매니저를 붙잡고 있어서, Maestro의 `pm clear`가 몇 분씩 막히거나 앱 첫 프레임이
# 늦게 그려진다. 스냅샷을 이 상태로 찍으면 스냅샷에서 뜰 때마다 같은 작업을 되풀이하게 된다.
#
# 사용법: emulator-settle.sh <부하가 내려가길 기다릴 최대 초>
set -euo pipefail

MAX_IDLE_WAIT_SECONDS="${1:-120}"
# 4코어 게스트 기준 1분 평균 부하. 이 아래로 내려오면 밀린 작업이 대부분 끝났다고 본다.
IDLE_LOAD_THRESHOLD=2.0

loadavg() {
  adb shell cat /proc/loadavg | cut -d' ' -f1
}

adb wait-for-device

# 스냅샷에서 뜬 직후에는 adb가 잠깐 offline이거나 패키지 매니저가 아직 응답하지 않는다.
echo "Waiting for package manager..."
for _ in $(seq 1 60); do
  if adb shell pm path android >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
adb shell pm path android >/dev/null

# 밀린 dexopt를 지금 끝낸다. 테스트 도중에 돌면 설치 잠금을 잡아 `pm clear`를 막는다.
echo "Running pending dexopt (load: $(loadavg))..."
timeout 600 adb shell cmd package bg-dexopt-job || echo "::warning::bg-dexopt-job did not finish cleanly"

echo "Waiting up to ${MAX_IDLE_WAIT_SECONDS}s for load < ${IDLE_LOAD_THRESHOLD}..."
start=$(date +%s)
while true; do
  load=$(loadavg)
  elapsed=$(( $(date +%s) - start ))
  if awk -v l="$load" -v t="$IDLE_LOAD_THRESHOLD" 'BEGIN { exit !(l < t) }'; then
    echo "Emulator settled after ${elapsed}s (load: ${load})."
    break
  fi
  if [ "$elapsed" -ge "$MAX_IDLE_WAIT_SECONDS" ]; then
    echo "::warning::Emulator still busy after ${elapsed}s (load: ${load}); continuing anyway."
    break
  fi
  echo "  ${elapsed}s load=${load}"
  sleep 10
done
