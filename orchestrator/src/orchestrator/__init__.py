from .adapters import (
    Adapter,
    AgentRequest,
    AgentResult,
    ClaudeAdapter,
    CodexAdapter,
    adapter_for,
)
from .errors import (
    GitCommandFailed,
    InvalidTransition,
    NotAGitRepository,
    OrchestratorError,
    PlanFormatError,
    PromptFileError,
    SnapshotFileError,
    StateFileError,
    UnknownAdapter,
)
from .errors import PipelineError, PluginDocsMissing
from .guards import GitSnapshot, GitViolation
from .policy import CommandVerdict, check_command
from .pipeline import Settings, StepResult, TaskPaths
from .scope import ScopeResult, Snapshot
from .state import RunState, StateStore, TaskState

__all__ = [
    "Adapter",
    "AgentRequest",
    "AgentResult",
    "ClaudeAdapter",
    "CommandVerdict",
    "CodexAdapter",
    "GitCommandFailed",
    "PipelineError",
    "PluginDocsMissing",
    "Settings",
    "StepResult",
    "TaskPaths",
    "GitSnapshot",
    "GitViolation",
    "InvalidTransition",
    "NotAGitRepository",
    "OrchestratorError",
    "PlanFormatError",
    "PromptFileError",
    "RunState",
    "ScopeResult",
    "Snapshot",
    "SnapshotFileError",
    "StateFileError",
    "StateStore",
    "TaskState",
    "UnknownAdapter",
    "adapter_for",
    "check_command",
]

__version__ = "0.5.0"
