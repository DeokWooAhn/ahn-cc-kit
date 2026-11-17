from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .adapters import FAILED, MISSING_COMMAND, STALLED, TIMEOUT, AgentResult

PROVIDER = "provider"
ENVIRONMENT = "environment"
AGENT = "agent"
VERIFY = "verify"

LOG_TAIL_BYTES = 4000

PROVIDER_SIGNS = (
    (r"OAuth session expired", "로그인 세션이 만료됐다"),
    (r"Failed to authenticate", "인증에 실패했다"),
    (r"Not logged in", "로그인되어 있지 않다"),
    (r"Please run /login", "로그인되어 있지 않다"),
    (r"\b401\b|\bUnauthorized\b", "인증이 거부됐다"),
    (r"rate.?limit", "호출 한도에 걸렸다"),
    (r"\b429\b", "호출 한도에 걸렸다"),
    (r"\b5\d\d\b.*(error|Error)", "공급자 쪽 오류다"),
    (r"quota", "사용량 한도에 걸렸다"),
)

ENVIRONMENT_SIGNS = (
    (r"command not found|No such file or directory", "필요한 명령이 없다"),
    (r"Unable to find a destination|simulator.*not.*(found|available)", "시뮬레이터를 찾지 못했다"),
    (r"xcode-select|Xcode.*not.*(installed|found)", "Xcode 설정 문제다"),
    (r"SDK.*not.*(found|installed)|ANDROID_HOME", "SDK를 찾지 못했다"),
    (r"Could not resolve|Connection refused|Network is unreachable", "네트워크에 닿지 못했다"),
    (r"No space left on device", "디스크가 찼다"),
    (r"Permission denied", "권한이 없다"),
    (r"JAVA_HOME|Unsupported class file major version", "자바 환경 문제다"),
)

NEXT_STEPS = {
    PROVIDER: "공급자 문제다. 로그인·한도를 확인하거나 `--route <역할>=<다른 어댑터>`로 바꿔 `orch resume`.",
    ENVIRONMENT: "실행 환경 문제다. 코드를 고쳐도 풀리지 않는다. 환경을 고친 뒤 `orch resume`.",
    AGENT: "에이전트가 일을 끝내지 못했다. 로그를 읽고, 계획이 과하면 줄인 뒤 `orch resume`.",
    VERIFY: "검증이 실패했다. 로그를 읽고 코드 문제인지 테스트 문제인지 가른 뒤 수정 계획을 쓴다.",
}


@dataclass(frozen=True)
class Failure:
    kind: str
    retryable: bool
    summary: str
    evidence: str
    next_step: str

    def describe(self) -> str:
        lines = [f"{self.summary} ({self.kind})"]
        if self.evidence:
            lines.append(f"   근거: {self.evidence}")
        lines.append(f"   다음: {self.next_step}")
        return "\n".join(lines)

    def to_json_object(self) -> dict:
        return {
            "kind": self.kind,
            "retryable": self.retryable,
            "summary": self.summary,
            "evidence": self.evidence,
            "next_step": self.next_step,
        }


def read_tail(path: Path, *, limit: int = LOG_TAIL_BYTES) -> str:
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return ""
    return raw[-limit:].decode("utf-8", errors="replace")


def classify(result: AgentResult, *, role_failed: str = AGENT) -> Failure:
    tail = read_tail(result.log_file)

    if result.outcome == MISSING_COMMAND:
        return _make(ENVIRONMENT, False, "명령을 찾지 못했다", result.detail)

    matched = _match(tail)
    if matched is not None:
        kind, summary, evidence = matched
        return _make(kind, kind == PROVIDER, summary, evidence)

    if result.outcome == TIMEOUT:
        return _make(AGENT, True, "제한 시간 안에 끝나지 않았다", result.detail)
    if result.outcome == STALLED:
        return _make(AGENT, True, "로그가 자라지 않아 멈춘 것으로 봤다", result.detail)
    if result.outcome == FAILED:
        return _make(role_failed, role_failed != ENVIRONMENT, "비정상 종료했다", result.detail)

    return _make(role_failed, True, f"{result.outcome}로 끝났다", result.detail)


def _match(tail: str) -> tuple[str, str, str] | None:
    for kind, signs in ((PROVIDER, PROVIDER_SIGNS), (ENVIRONMENT, ENVIRONMENT_SIGNS)):
        for pattern, summary in signs:
            found = re.search(pattern, tail, re.IGNORECASE)
            if found:
                return kind, summary, found.group(0).strip()[:120]
    return None


def _make(kind: str, retryable: bool, summary: str, evidence: str) -> Failure:
    return Failure(
        kind=kind,
        retryable=retryable,
        summary=summary,
        evidence=evidence.strip()[:200],
        next_step=NEXT_STEPS.get(kind, NEXT_STEPS[AGENT]),
    )
