"""호출마다 한 줄씩 남기는 장부.

**무엇을 재려는 것인가** — 왕복 하나에 어느 역할이 얼마를 쓰는가.
시작 등급을 낮출지 정하려면 먼저 지금 무엇이 비싼지 알아야 한다.
짐작으로 내리면 어설픈 결과가 왕복을 하나 더 부른다.

`state.json` 에 넣지 않는 이유는 그쪽이 한 작업의 **지금 상태**이기 때문이다.
장부는 지나간 일의 기록이라 덧붙이기만 하고 고치지 않는다. 작업마다 한 파일이고
`orch stats` 가 전부를 모아 읽는다.

**장부 때문에 호출이 실패하지는 않는다.** 쓰다 넘어지면 조용히 넘긴다.
재려다가 재는 대상을 망가뜨리면 안 된다.
"""

from __future__ import annotations

import json
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

LEDGER = "calls.jsonl"

AGENT = "agent"
VERIFY = "verify"

# 등급을 주지 않은 호출. 도구의 기본 설정으로 돈 것이라 런타임은 무엇이었는지 모른다.
TOOL_DEFAULT = "(기본)"


@dataclass(frozen=True)
class Call:
    at: str
    task_id: str
    role: str
    kind: str
    tool: str
    effort: str | None
    attempt: int
    outcome: str
    seconds: float
    log_bytes: int

    @property
    def rung(self) -> str:
        # 검증은 사람이 계획에 적은 셸 명령이다. 등급이라는 것이 없다.
        if self.kind == VERIFY:
            return "-"
        return self.effort or TOOL_DEFAULT

    def to_json_object(self) -> dict:
        return {
            "at": self.at,
            "task_id": self.task_id,
            "role": self.role,
            "kind": self.kind,
            "tool": self.tool,
            "effort": self.effort,
            "attempt": self.attempt,
            "outcome": self.outcome,
            "seconds": self.seconds,
            "log_bytes": self.log_bytes,
        }


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record(task_dir: Path, call: Call) -> None:
    """장부에 한 줄 덧붙인다. 실패해도 호출을 망가뜨리지 않는다."""
    try:
        task_dir = Path(task_dir)
        task_dir.mkdir(parents=True, exist_ok=True)
        with (task_dir / LEDGER).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(call.to_json_object(), ensure_ascii=False) + "\n")
    except OSError:
        return


def read(root: Path) -> list[Call]:
    """산출물 디렉터리 아래 모든 작업의 장부를 모은다."""
    root = Path(root)
    if not root.is_dir():
        return []
    calls: list[Call] = []
    for path in sorted(root.glob(f"*/{LEDGER}")):
        calls.extend(_read_one(path))
    return calls


def read_task(task_dir: Path) -> list[Call]:
    return _read_one(Path(task_dir) / LEDGER)


def _read_one(path: Path) -> list[Call]:
    if not path.is_file():
        return []
    calls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            # 손으로 건드렸거나 쓰다 끊긴 줄. 나머지까지 버리지는 않는다.
            continue
        calls.append(
            Call(
                at=str(raw.get("at", "")),
                task_id=str(raw.get("task_id", "")),
                role=str(raw.get("role", "")),
                kind=str(raw.get("kind", "")),
                tool=str(raw.get("tool", "")),
                effort=raw.get("effort"),
                attempt=int(raw.get("attempt", 0) or 0),
                outcome=str(raw.get("outcome", "")),
                seconds=float(raw.get("seconds", 0) or 0),
                log_bytes=int(raw.get("log_bytes", 0) or 0),
            )
        )
    return calls


@dataclass(frozen=True)
class Row:
    role: str
    tool: str
    rung: str
    count: int
    seconds: float
    failed: int

    @property
    def average(self) -> float:
        return self.seconds / self.count if self.count else 0.0


def summarize(calls: list[Call]) -> list[Row]:
    """역할·도구·등급으로 묶는다. 이 셋이 달라지면 다른 호출로 본다."""
    buckets: dict[tuple[str, str, str], list[Call]] = defaultdict(list)
    for call in calls:
        buckets[(call.role, call.tool, call.rung)].append(call)
    rows = [
        Row(
            role=role,
            tool=tool,
            rung=rung,
            count=len(group),
            seconds=sum(call.seconds for call in group),
            failed=sum(1 for call in group if call.outcome != "ok"),
        )
        for (role, tool, rung), group in buckets.items()
    ]
    rows.sort(key=lambda row: (-row.seconds, row.role))
    return rows


def spoken(seconds: float) -> str:
    total = int(round(seconds))
    if total < 60:
        return f"{total}초"
    minutes, rest = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}분 {rest}초" if rest else f"{minutes}분"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}시간 {minutes}분" if minutes else f"{hours}시간"


HEADERS = ("역할", "도구", "등급", "횟수", "합계", "평균", "실패")
RIGHT = (False, False, False, True, True, True, True)


def _width(text: str) -> int:
    """한글은 터미널에서 두 칸을 먹는다. 그걸 세지 않으면 표가 어긋난다."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int, *, right: bool = False) -> str:
    gap = " " * max(0, width - _width(text))
    return gap + text if right else text + gap


def table(rows: list[Row]) -> list[str]:
    cells = [list(HEADERS)]
    for row in rows:
        cells.append(
            [
                row.role,
                row.tool,
                row.rung,
                str(row.count),
                spoken(row.seconds),
                spoken(row.average),
                str(row.failed) if row.failed else "-",
            ]
        )
    widths = [max(_width(line[index]) for line in cells) for index in range(len(HEADERS))]
    return [
        "  ".join(_pad(cell, widths[index], right=RIGHT[index]) for index, cell in enumerate(line))
        for line in cells
    ]
