#!/usr/bin/env bash
# debug APK를 설치하고 한 번 띄워 첫 실행 비용을 치른 뒤 Maestro Flow를 돌린다.
# android-emulator-runner의 script는 한 줄씩 따로 실행돼서 여러 줄짜리 로직은 이 파일에 둔다.
#
# 필요한 환경 변수: APP_ID, MAESTRO_TAGS
# 선택: APK_PATH(기본 artifacts/app-debug.apk), UI_TESTING_EXTRA(기본 UI_TESTING)
set -euo pipefail

APK="${APK_PATH:-artifacts/app-debug.apk}"
EXTRA="${UI_TESTING_EXTRA:-UI_TESTING}"
OUT=build/maestro
mkdir -p "$OUT"

# 실패를 되짚을 수 있게 테스트 내내 logcat을 남긴다(ActivityManager의 Displayed 줄에 실행 시간이 찍힌다).
adb logcat -v threadtime >"$OUT/logcat.txt" 2>&1 &
LOGCAT_PID=$!
trap 'kill "$LOGCAT_PID" 2>/dev/null || true' EXIT

adb install -r "$APK"

# 설치 직후 첫 실행은 dex 검증·파일 캐시 적재 때문에 유난히 느리다. Flow가 아니라 여기서 그 비용을 치른다.
# -W는 첫 프레임이 그려질 때까지 기다린다. 테스트 모드 인자는 Flow와 같게 넘긴다.
# 런처 Activity에 DEFAULT 카테고리가 없으면 암시적 인텐트로는 안 뜨므로 컴포넌트를 찾아 직접 지정한다.
LAUNCHER=$(adb shell cmd package resolve-activity --brief -c android.intent.category.LAUNCHER "$APP_ID" | tail -n 1 | tr -d '\r')
echo "Warming up $LAUNCHER..."
timeout 120 adb shell am start -W -n "$LAUNCHER" --ez "$EXTRA" true \
  || echo "::warning::Warm-up launch did not finish in time"
adb shell am force-stop "$APP_ID"

maestro test .maestro \
  --include-tags="$MAESTRO_TAGS" \
  -e APP_ID="$APP_ID" \
  --format=JUNIT \
  --output="$OUT/report.xml" \
  --test-output-dir="$OUT/output" \
  --debug-output="$OUT/debug" \
  --flatten-debug-output
