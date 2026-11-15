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
