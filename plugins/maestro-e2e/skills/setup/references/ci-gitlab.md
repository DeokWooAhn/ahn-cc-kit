# GitLab CI에 smoke E2E 붙이기

> **이 문서의 구성은 실제 GitLab 파이프라인에서 검증하지 않았다.** GitHub Actions 구성
> (`ci-github-actions.md`)을 옮겨 적은 것이다. 처음 적용할 때는 사용자와 함께 러너 환경부터 확인한다.

## 먼저 정할 것: 에뮬레이터를 어디서 띄우나

GitLab 공유 러너나 일반 Docker 러너에서는 보통 `/dev/kvm`을 쓸 수 없어 Android 에뮬레이터가 뜨지
않는다(뜨더라도 소프트웨어 에뮬레이션이라 Flow 하나에 수 분씩 걸린다). 셋 중 하나를 사용자가 정해야 한다.
**인프라 결정이라 에이전트가 정하지 않는다.**

| 방법 | 필요한 것 | 장단점 |
| --- | --- | --- |
| KVM 되는 self-hosted 러너 | Linux 머신, `/dev/kvm`, Android SDK. Docker 실행기면 러너 설정에 `/dev/kvm` 장치 연결 | 비용 없음. 러너 관리가 필요하다 |
| 실기기 러너 | 러너 머신에 USB로 폰 연결 | 에뮬레이터 부담이 없다. 기기가 잠기거나 끊기면 실패한다 |
| Maestro Cloud | `MAESTRO_CLOUD_API_KEY`(Masked·Protected 변수) | 러너가 가볍다. 유료이고, 앱을 외부로 올린다 |

## KVM 러너일 때

GitHub 구성과 같은 순서로 script를 쓴다. 템플릿 스크립트는 GitLab에서도 그대로 쓸 수 있다
(`::warning::` 줄은 GitLab에서 그냥 로그로 찍힌다).

1. `sdkmanager`로 `system-images;android-34;google_apis;x86_64` 설치, `avdmanager`로 AVD 생성
   (`hw.cpu.ncore=4`, RAM 4GB)
2. 에뮬레이터를 `-no-window -no-snapshot-save`로 백그라운드 실행, `adb wait-for-device`
3. `emulator-settle.sh 120` → `maestro-smoke.sh`
4. `build/maestro/`를 `artifacts:`로 올리고 `report.xml`을 `reports: junit:`으로 지정
5. AVD는 `cache:`로 보관하면 다음 실행이 빨라진다

## Maestro Cloud일 때

```bash
maestro cloud --api-key "$MAESTRO_CLOUD_API_KEY" --app-file app-debug.apk --flows .maestro -e APP_ID=com.example.app --include-tags smoke --format JUNIT --output report.xml
```

- 템플릿 Flow는 `${APP_ID}`를 쓰므로 `-e APP_ID=`를 반드시 넘긴다.
- `--format JUNIT`을 빼면 `--output`을 줘도 리포트가 생기지 않는다(기본 형식이 `NOOP`).
- 에뮬레이터 안정화 스크립트는 필요 없다.
- debug APK를 외부 서비스로 올린다. 회사 정책을 확인한다.

## rules:changes 함정

- job을 `rules:changes`로 빼면, 그 job을 `needs:`로 기다리던 job 때문에 **파이프라인 생성 자체가
  실패**한다. `needs: [{ job: e2e_smoke, optional: true }]`로 쓴다. 단, 릴리스 관문이면 optional로 두지
  말고 릴리스 파이프라인에서는 항상 돌게 한다.
- 브랜치 파이프라인의 `changes`는 **직전 푸시와의 차이**만 본다. 새 브랜치의 첫 파이프라인은 항상 참이다.
  MR 파이프라인에서는 `compare_to`로 기준 브랜치를 지정하는 편이 의도와 맞다.
