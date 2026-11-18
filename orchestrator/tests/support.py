from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from orchestrator.adapters import Adapter


class TempRepo:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="orchestrator-test-")
        self.path = Path(self._tmp.name)

    def __enter__(self) -> TempRepo:
        self.git("init", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        self.git("config", "commit.gpgsign", "false")
        self.write("README.md", "시작\n")
        self.git("add", "README.md")
        self.commit("첫 커밋")
        return self

    def __exit__(self, *exc_info) -> None:
        self._tmp.cleanup()

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=str(self.path),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} 실패: {result.stderr.strip()}")
        return result.stdout

    def write(self, relative: str, content: str) -> Path:
        target = self.path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def remove(self, relative: str) -> None:
        (self.path / relative).unlink()

    def commit(self, message: str) -> str:
        self.git("commit", "-m", message, "--allow-empty")
        return self.head()

    def head(self) -> str:
        return self.git("rev-parse", "HEAD").strip()


class TempBareRepo:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="orchestrator-remote-")
        self.path = Path(self._tmp.name)

    def __enter__(self) -> TempBareRepo:
        result = subprocess.run(
            ["git", "init", "--bare", "-b", "main", str(self.path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise AssertionError(f"bare 저장소를 만들지 못했다: {result.stderr.strip()}")
        return self

    def __exit__(self, *exc_info) -> None:
        self._tmp.cleanup()


def plan_text(
    paths: list[str], *, heading: str = "## 건드릴 파일", verify: str = "true"
) -> str:
    listed = "\n".join(paths)
    return f"""# 시험용 계획

## 목적

시험한다.

{heading}

```
{listed}
```

## 검증

```
{verify}
```
"""


class ScriptedAdapter(Adapter):
    name = "scripted"

    def __init__(self, script: str = "true") -> None:
        self.script = script
        self.prompts: list[str] = []
        self.read_only: list[bool] = []
        self.attempts: list[int] = []

    def build_command(self, request, prompt: str) -> list[str]:
        self.prompts.append(prompt)
        self.read_only.append(request.read_only)
        self.attempts.append(request.attempt)
        return ["sh", "-c", self.script]
