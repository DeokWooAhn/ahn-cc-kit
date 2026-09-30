# GitHub Actions에 smoke E2E 붙이기

`templates/github/e2e-jobs.yml`의 job 두 개를 기존 Android 워크플로에 붙이고, `templates/scripts/`의
스크립트 두 개를 `.github/scripts/`로 복사한다(실행 권한 포함).

## 구성

```text
PR ─┬─ build ───────────────┐
    └─ e2e_changes ─────────┴─ e2e_smoke ── (태그일 때) release_bundle ─ 스토어 업로드
```

- **`e2e_changes`**: 바뀐 파일이 `E2E_SKIP_PATHS`에만 걸리면 E2E를 건너뛴다. `build`와 동시에 돈다.
  목록에 없는 경로가 하나라도 있으면 돌린다. 모르는 경로는 돌리는 쪽이 안전하다.
- **`e2e_smoke`**: `build`가 올린 debug APK를 받아 에뮬레이터(API 34, `google_apis`, x86_64)에서 `smoke`를 돌린다.
- **릴리스 관문**: 릴리스 job의 `needs`에 `e2e_smoke`를 넣는다. 필요한 job이 실패하거나 건너뛰어지면
  뒤따르는 job도 실행되지 않는다.

## 바꿀 곳

| 값 | 내용 |
| --- | --- |
| `APP_ID` | debug 빌드의 applicationId. `applicationIdSuffix`가 있으면 붙인 값 |
| `E2E_SKIP_PATHS` | 앱 동작과 무관한 경로(문서, 서버 코드, 스토어 이미지 등) |
| artifact 이름·경로 | `build` job이 올리는 이름이 `debug-apk`가 아니면 맞춘다 |
| `UI_TESTING_EXTRA` | 앱의 테스트 모드 인자 이름이 다르면 `maestro-smoke.sh`에 환경 변수로 넘긴다 |

## 안정화 장치와 이유

모두 실제로 CI가 실패하거나 수 분씩 멈춘 뒤 넣은 것이다. 빼지 않는다.

| 장치 | 없으면 |
| --- | --- |
| `MAESTRO_VERSION` 고정 | Maestro 새 릴리스로 코드 변경 없이 CI가 깨진다 |
| 에뮬레이터 4코어·4GB | 기본값(2코어)에서는 부팅 후 작업만으로 앱 첫 프레임이 15초를 넘긴다 |
| 스냅샷을 조용해진 뒤 저장 | 밀린 dexopt·GMS 작업이 스냅샷에 담겨 매 실행마다 되풀이된다 |
| `emulator-settle.sh` | 패키지 매니저가 준비되기 전에 설치·`pm clear`가 돌아 막힌다 |
| 워밍업 실행 | 설치 직후 첫 실행이 느려 첫 Flow의 대기 시간을 넘긴다 |
| logcat 수집 | 실패 원인(프로세스가 죽었는지, 인자가 들어왔는지)을 되짚을 방법이 없다 |

## 실행 시간

캐시가 있으면 `e2e_smoke`는 3~4분 걸린다(Flow 3개 기준). 첫 실행은 AVD를 만드느라 몇 분 더 걸린다.
**두 번 이상 통과한 뒤** 릴리스 관문을 건다. 불안정한 smoke는 릴리스를 막는다.

## 이 구성에서 쓰는 외부 Action

`actions/checkout`, `actions/setup-java`, `actions/download-artifact`, `actions/upload-artifact`,
`actions/cache`, `reactivecircus/android-emulator-runner@v2`. 저장소 정책이 서드파티 Action을 제한하면
마지막 것을 승인받아야 한다.
