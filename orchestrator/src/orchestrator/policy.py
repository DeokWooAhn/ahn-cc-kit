from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

DENIED = (
    (r"\brm\s+-[a-zA-Z]*[rR]", "재귀 삭제"),
    (r"\bgit\s+push\b", "원격에 밀기"),
    (r"\bgit\s+reset\s+--hard\b", "작업 트리를 되돌리기"),
    (r"\bgit\s+clean\b", "추적되지 않은 파일 삭제"),
    (r"\bgit\s+checkout\s+--\s", "파일 변경 버리기"),
    (r"\bgit\s+restore\b", "파일 변경 버리기"),
    (r"\bgit\s+branch\s+-[a-zA-Z]*D", "브랜치 강제 삭제"),
    (r"\b(curl|wget)\b[^|;&]*\|\s*(sudo\s+)?(sh|bash|zsh)\b", "내려받아 바로 실행"),
    (r"\bprintenv\b", "환경 변수 전체 출력"),
    (r"(^|[\s|;&<])env\s*(\||$|;|&)", "환경 변수 전체 출력"),
    (r"\.env\b", "비밀 파일 다루기"),
    (r"\.(pem|p8|p12|jks|keystore)\b", "서명·인증 파일 다루기"),
    (r"\bsudo\b", "권한 상승"),
    (r"\bfastlane\b", "배포 도구"),
    (r"\b(kubectl|terraform|helm)\b", "인프라 조작"),
    (r"\bnpm\s+publish\b", "패키지 배포"),
    (r"\bgh\s+(pr\s+merge|release)\b", "병합·릴리스"),
    (r"\bshutdown\b|\breboot\b", "시스템 종료"),
    (r":\(\)\s*\{.*\};\s*:", "포크 폭탄"),
    (r">\s*/dev/(sd|disk|nvme)", "디스크에 직접 쓰기"),
)

COMPILED = tuple((re.compile(pattern), reason) for pattern, reason in DENIED)


@dataclass(frozen=True)
class CommandVerdict:
    command: str
    allowed: bool
    reason: str = ""
    pattern: str = ""

    def describe(self) -> str:
        if self.allowed:
            return f"{self.command} — 통과"
        return f"{self.command}\n   막힌 이유: {self.reason} (`{self.pattern}`)"


def check_command(command: str, *, allow: Iterable[str] = ()) -> CommandVerdict:
    for exact in allow:
        if command.strip() == exact.strip():
            return CommandVerdict(command, True)
    for compiled, reason in COMPILED:
        found = compiled.search(command)
        if found:
            return CommandVerdict(command, False, reason, found.group(0).strip())
    return CommandVerdict(command, True)


def check_all(commands: Iterable[str], *, allow: Iterable[str] = ()) -> tuple[CommandVerdict, ...]:
    return tuple(check_command(command, allow=allow) for command in commands)


def blocked(verdicts: Iterable[CommandVerdict]) -> tuple[CommandVerdict, ...]:
    return tuple(verdict for verdict in verdicts if not verdict.allowed)
