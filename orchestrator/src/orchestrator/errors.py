class OrchestratorError(Exception):
    pass


class NotAGitRepository(OrchestratorError):
    def __init__(self, path):
        super().__init__(f"git 저장소가 아니다: {path}")
        self.path = path


class GitCommandFailed(OrchestratorError):
    def __init__(self, args, returncode, stderr):
        super().__init__(f"git {' '.join(args)} 실패 (종료 코드 {returncode}): {stderr.strip()}")
        self.args = args
        self.returncode = returncode
        self.stderr = stderr


class StateFileError(OrchestratorError):
    pass


class SnapshotFileError(OrchestratorError):
    pass


class PlanFormatError(OrchestratorError):
    pass


class InvalidTransition(OrchestratorError):
    def __init__(self, current, target):
        super().__init__(f"{current}에서 {target}으로 갈 수 없다")
        self.current = current
        self.target = target


class PromptFileError(OrchestratorError):
    pass


class UnknownAdapter(OrchestratorError):
    def __init__(self, name):
        super().__init__(f"모르는 어댑터: {name}")
        self.name = name


class PluginDocsMissing(OrchestratorError):
    def __init__(self, looked):
        joined = ", ".join(str(path) for path in looked)
        super().__init__(f"플러그인 문서를 찾지 못했다. 찾아본 곳: {joined}")
        self.looked = tuple(looked)


class PipelineError(OrchestratorError):
    pass
