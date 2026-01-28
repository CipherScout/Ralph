# Ralph Architecture Guide

This guide covers Ralph's internal architecture for developers who want to understand the system or contribute to the project.

## Table of Contents

1. [System Overview](#system-overview)
2. [Module Reference](#module-reference)
3. [Key Design Decisions](#key-design-decisions)
4. [Data Flow Diagrams](#data-flow-diagrams)
5. [Extension Points](#extension-points)
6. [Testing Architecture](#testing-architecture)

---

## System Overview

Ralph is a deterministic agentic coding loop built on the Claude Agent SDK. The key principle is **Python orchestration with LLM execution** - the orchestrator controls workflow progression while Claude handles implementation tasks.

### High-Level Architecture

```
                                    +---------------------------+
                                    |        User/CLI           |
                                    +-------------+-------------+
                                                  |
                                                  v
+------------------+              +---------------+---------------+
|                  |              |                               |
|   config.yaml    +------------->+           cli.py              |
|                  |              |     (Command Interface)       |
+------------------+              +---------------+---------------+
                                                  |
                                                  v
                                  +---------------+---------------+
                                  |                               |
                                  |          runner.py            |
                                  |     (Loop Orchestration)      |
                                  |                               |
                                  +-------+-------+-------+-------+
                                          |       |       |
                    +---------------------+       |       +---------------------+
                    |                             |                             |
                    v                             v                             v
        +-----------+-----------+   +-----------+-----------+   +-----------+-----------+
        |                       |   |                       |   |                       |
        |     phases.py         |   |    executors.py       |   |    context.py         |
        |  (Phase Management)   |   | (Phase Executors)     |   | (Context Handoff)     |
        |                       |   |                       |   |                       |
        +-----------+-----------+   +-----------+-----------+   +-----------+-----------+
                    |                           |                           |
                    +-------------+-------------+                           |
                                  |                                         |
                                  v                                         |
                    +-------------+-------------+                           |
                    |                           |                           |
                    |      sdk_client.py        |<--------------------------+
                    |   (Claude SDK Wrapper)    |
                    |                           |
                    +-------+-------+-----------+
                            |       |
              +-------------+       +-------------+
              |                                   |
              v                                   v
+-------------+-------------+       +-------------+-------------+
|                           |       |                           |
|       sdk_hooks.py        |       |      mcp_tools.py         |
|    (Safety Hooks)         |       |   (MCP Tool Definitions)  |
|                           |       |                           |
+---------------------------+       +-------------+-------------+
                                                  |
                                                  v
                                    +-------------+-------------+
                                    |                           |
                                    |        tools.py           |
                                    |   (Tool Implementations)  |
                                    |                           |
                                    +---------------------------+

                              STATE PERSISTENCE LAYER

+------------------+    +------------------+    +------------------+
|                  |    |                  |    |                  |
|   models.py      |    |  persistence.py  |    |  verification.py |
| (Data Models)    |    |  (State I/O)     |    | (Validation)     |
|                  |    |                  |    |                  |
+------------------+    +------------------+    +------------------+
```

### Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| **cli.py** | User interface, command parsing, session management |
| **runner.py** | Main loop orchestration, iteration control, recovery |
| **executors.py** | Phase-specific execution logic |
| **phases.py** | Phase definitions, transitions, prompts |
| **sdk_client.py** | Claude SDK integration, API calls |
| **sdk_hooks.py** | Pre/post tool execution safety hooks |
| **mcp_tools.py** | MCP tool schema definitions |
| **tools.py** | Tool implementations (task management, state) |
| **models.py** | Core data structures (State, Plan, Task) |
| **persistence.py** | JSON state save/load with atomic writes |
| **context.py** | Context window management, MEMORY.md generation |
| **memory.py** | Deterministic memory capture at phase/iteration/session boundaries |
| **config.py** | YAML configuration, cost limits |
| **verification.py** | Backpressure commands, validation reports |
| **iteration.py** | Single iteration execution logic |

### Data Flow Through the System

```
1. User invokes: ralph run --prompt "Build feature X"
                              |
                              v
2. CLI parses command, loads/creates state
                              |
                              v
3. LoopRunner initializes, checks circuit breaker
                              |
                              v
4. Phase executor prepares context (prompts, tools)
                              |
                              v
5. SDK client calls Claude with phase-specific configuration
                              |
                              v
6. Claude executes, calling MCP tools for state updates
                              |
                              v
7. Hooks intercept tool calls for safety validation
                              |
                              v
8. Results processed, state persisted atomically
                              |
                              v
9. Loop continues or triggers handoff/halt
```

---

## Module Reference

### cli.py - Command-Line Interface

**Purpose**: Entry point for all user interactions. Handles command parsing, session lifecycle, and output formatting.

**Key Classes/Functions**:

```python
# Main CLI group
@click.group()
def cli() -> None: ...

# Core commands
@cli.command()
def run(prompt: str, phase: str, max_iterations: int) -> None: ...

@cli.command()
def status() -> None: ...

@cli.command()
def init(project_path: Path) -> None: ...

@cli.command()
def reset() -> None: ...

@cli.command()
def inject(message: str, priority: int) -> None: ...
```

**Dependencies**:
- `runner.py` - LoopRunner for execution
- `persistence.py` - State loading/saving
- `config.py` - Configuration management
- `context.py` - Injection handling

---

### runner.py - Loop Orchestration

**Purpose**: Core orchestration logic that manages the deterministic loop. Controls iteration flow, recovery strategies, and halt conditions.

**Key Classes/Functions**:

```python
class LoopStatus(str, Enum):
    """Possible states of the loop."""
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    HALTED = "halted"

class RecoveryAction(str, Enum):
    """Actions to take on failure."""
    RETRY = "retry"
    SKIP_TASK = "skip_task"
    MANUAL_INTERVENTION = "manual_intervention"
    RESET_CIRCUIT_BREAKER = "reset_circuit_breaker"
    HANDOFF = "handoff"

class RecoveryStrategy:
    """Configurable retry logic with backoff."""
    action: RecoveryAction
    max_retries: int = 3
    current_retry: int = 0

    def should_retry(self) -> bool: ...
    def increment_retry(self) -> None: ...

class LoopRunner:
    """Main orchestration class."""

    def __init__(self, project_root: Path, config: RalphConfig | None = None): ...

    async def run(self, execute_fn: Callable, max_iterations: int = 100) -> LoopResult: ...

    def pre_iteration(self) -> dict[str, Any]: ...
    def post_iteration(self, result: RunnerIterationResult) -> None: ...
    def should_continue(self) -> bool: ...

def determine_recovery_action(error: str, state: RalphState) -> RecoveryAction: ...
def apply_recovery_action(action: RecoveryAction, state: RalphState, plan: ImplementationPlan) -> None: ...
```

**Dependencies**:
- `models.py` - RalphState, ImplementationPlan
- `persistence.py` - State I/O
- `phases.py` - Phase management
- `context.py` - Handoff logic
- `config.py` - Configuration

---

### executors.py - Phase Executors

**Purpose**: Phase-specific execution strategies. Each phase has different tool allocations, prompts, and success criteria.

**Key Classes/Functions**:

```python
class PhaseExecutor(Protocol):
    """Protocol for phase executors."""

    async def execute(self, context: IterationContext) -> ExecutionResult: ...
    def get_allowed_tools(self) -> list[str]: ...
    def get_system_prompt(self) -> str: ...

class DiscoveryExecutor(PhaseExecutor):
    """Interactive requirements gathering."""
    ...

class PlanningExecutor(PhaseExecutor):
    """Task decomposition and planning."""
    ...

class BuildingExecutor(PhaseExecutor):
    """Implementation with full tool access."""
    ...

class ValidationExecutor(PhaseExecutor):
    """Testing and verification."""
    ...

def get_executor_for_phase(phase: Phase) -> PhaseExecutor: ...
```

**Dependencies**:
- `phases.py` - Phase definitions
- `sdk_client.py` - SDK interaction
- `models.py` - State/Plan models

---

### phases.py - Phase Management

**Purpose**: Defines the four execution phases and their characteristics. Manages phase transitions and generates phase-specific prompts.

**Key Classes/Functions**:

```python
class Phase(str, Enum):
    """Execution phases."""
    DISCOVERY = "discovery"
    PLANNING = "planning"
    BUILDING = "building"
    VALIDATION = "validation"

def get_phase_prompt(
    phase: Phase,
    project_root: Path,
    task: Task | None = None,
    config: RalphConfig | None = None,
) -> str: ...

def can_transition(from_phase: Phase, to_phase: Phase) -> bool: ...

def get_next_phase(current: Phase) -> Phase | None: ...

# Phase-specific prompt builders
def build_discovery_prompt(project_root: Path, config: RalphConfig) -> str: ...
def build_planning_prompt(project_root: Path, config: RalphConfig) -> str: ...
def build_building_prompt(task: Task, project_root: Path, config: RalphConfig) -> str: ...
def build_validation_prompt(project_root: Path, config: RalphConfig) -> str: ...
```

**Dependencies**:
- `models.py` - Phase enum, Task
- `config.py` - Phase configuration
- `templates/` - Prompt templates

---

### sdk_client.py - Claude SDK Wrapper

**Purpose**: Wraps the Claude Agent SDK with Ralph-specific configuration. Handles model selection, tool allocation, and cost tracking.

**Key Classes/Functions**:

```python
# Model pricing for cost tracking
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
    "default": {"input": 3.0, "output": 15.0},
}

# Phase-specific tool allocation
PHASE_TOOLS: dict[Phase, list[str]] = {
    Phase.DISCOVERY: ["Read", "Glob", "Grep", "WebSearch", "AskUserQuestion"],
    Phase.PLANNING: ["Read", "Glob", "Grep", "Write", "ExitPlanMode"],
    Phase.BUILDING: ["Read", "Write", "Edit", "Bash", "BashOutput", "KillBash", ...],
    Phase.VALIDATION: ["Read", "Bash", "BashOutput", "Task", ...],
}

@dataclass
class IterationMetrics:
    """Metrics from a single iteration."""
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    session_id: str | None = None

@dataclass
class IterationResult:
    """Result from running one iteration."""
    success: bool
    task_completed: bool = False
    task_id: str | None = None
    tokens_used: int = 0
    cost_usd: float = 0.0
    needs_handoff: bool = False
    error: str | None = None
    metrics: IterationMetrics = field(default_factory=IterationMetrics)

class RalphSDKClient:
    """Claude SDK client configured for Ralph."""

    def __init__(
        self,
        state: RalphState,
        config: RalphConfig | None = None,
        hooks: dict[str, list[HookMatcher]] | None = None,
        mcp_servers: dict[str, Any] | None = None,
        auto_configure: bool = True,
    ): ...

    async def run_iteration(
        self,
        prompt: str,
        phase: Phase | None = None,
        system_prompt: str | None = None,
        max_turns: int | None = None,
    ) -> IterationResult: ...

    def _build_options(self, phase: Phase | None = None, max_turns: int | None = None) -> ClaudeAgentOptions: ...

    def reset_session(self) -> None: ...

def calculate_cost(input_tokens: int, output_tokens: int, model: str) -> float: ...
def get_tools_for_phase(phase: Phase) -> list[str]: ...
def get_model_for_phase(phase: Phase, config: RalphConfig | None = None) -> str: ...
def calculate_max_turns(phase: Phase) -> int: ...
def create_ralph_client(state: RalphState, config: RalphConfig | None = None, ...) -> RalphSDKClient: ...
```

**Dependencies**:
- `claude_agent_sdk` - External SDK
- `models.py` - RalphState, Phase
- `config.py` - RalphConfig
- `sdk_hooks.py` - Safety hooks
- `mcp_tools.py` - Tool definitions

---

### sdk_hooks.py - Safety Hooks

**Purpose**: Pre and post tool execution hooks for safety enforcement. Blocks dangerous operations and enforces phase constraints.

**Key Classes/Functions**:

```python
class RalphPreToolHook:
    """Pre-execution validation hook."""

    def __init__(self, state: RalphState, config: RalphConfig): ...

    async def __call__(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str | None,
        context: HookContext,
    ) -> HookResult: ...

    def _validate_bash_command(self, command: str) -> tuple[bool, str | None]: ...
    def _validate_tool_for_phase(self, tool_name: str) -> tuple[bool, str | None]: ...

class RalphPostToolHook:
    """Post-execution tracking hook."""

    async def __call__(
        self,
        tool_name: str,
        tool_result: Any,
        tool_use_id: str | None,
        context: HookContext,
    ) -> None: ...

def create_ralph_hooks(state: RalphState, config: RalphConfig) -> dict[str, list[HookMatcher]]: ...
```

**Dependencies**:
- `models.py` - RalphState, Phase
- `config.py` - SafetyConfig
- `sdk.py` - Blocked command lists

---

### mcp_tools.py - MCP Tool Definitions

**Purpose**: Defines MCP tool schemas that expose Ralph's state management capabilities to Claude.

**Key Classes/Functions**:

```python
# Tool schemas for MCP exposure
RALPH_TOOLS: list[dict[str, Any]] = [
    {
        "name": "ralph_get_next_task",
        "description": "Get the highest-priority incomplete task",
        "input_schema": {...},
    },
    {
        "name": "ralph_mark_task_complete",
        "description": "Mark a task as completed",
        "input_schema": {...},
    },
    {
        "name": "ralph_mark_task_blocked",
        "description": "Mark a task as blocked with reason",
        "input_schema": {...},
    },
    {
        "name": "ralph_append_learning",
        "description": "Record a learning for future iterations",
        "input_schema": {...},
    },
    {
        "name": "ralph_get_plan_summary",
        "description": "Get implementation plan summary",
        "input_schema": {...},
    },
    {
        "name": "ralph_get_state_summary",
        "description": "Get current Ralph state summary",
        "input_schema": {...},
    },
    {
        "name": "ralph_add_task",
        "description": "Add a new task to the plan",
        "input_schema": {...},
    },
]

def create_mcp_server(project_root: Path) -> MCPServer: ...
```

**Dependencies**:
- `tools.py` - Tool implementations
- `models.py` - Task, Plan schemas

---

### tools.py - Tool Implementations

**Purpose**: Implements the actual logic for MCP tools. Handles task state transitions and learning capture.

**Key Classes/Functions**:

```python
@dataclass
class ToolResult:
    """Result from a custom tool execution."""
    success: bool
    content: str
    data: dict[str, Any] | None = None
    error: str | None = None

class RalphTools:
    """Custom tools for Ralph state management."""

    def __init__(self, project_root: Path): ...

    def get_next_task(self) -> ToolResult: ...
    def mark_task_complete(self, task_id: str, verification_notes: str | None = None, tokens_used: int | None = None) -> ToolResult: ...
    def mark_task_blocked(self, task_id: str, reason: str) -> ToolResult: ...
    def mark_task_in_progress(self, task_id: str) -> ToolResult: ...
    def increment_retry(self, task_id: str) -> ToolResult: ...
    def append_learning(self, learning: str, category: str = "pattern") -> ToolResult: ...
    def get_plan_summary(self) -> ToolResult: ...
    def get_state_summary(self) -> ToolResult: ...
    def add_task(self, task_id: str, description: str, priority: int, ...) -> ToolResult: ...

def create_tools(project_root: Path) -> RalphTools: ...

# Tool definitions for MCP exposure
TOOL_DEFINITIONS: list[dict[str, Any]] = [...]
```

**Dependencies**:
- `models.py` - Task, ImplementationPlan, RalphState
- `persistence.py` - State I/O

---

### models.py - Data Models

**Purpose**: Core data structures that define Ralph's state. All models are dataclasses for immutability and serialization.

**Key Classes/Functions**:

```python
class Phase(str, Enum):
    """Execution phases."""
    DISCOVERY = "discovery"
    PLANNING = "planning"
    BUILDING = "building"
    VALIDATION = "validation"

class TaskStatus(str, Enum):
    """Task lifecycle states."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    BLOCKED = "blocked"

@dataclass
class Task:
    """A single implementation task."""
    id: str
    description: str
    priority: int
    status: TaskStatus = TaskStatus.PENDING
    dependencies: list[str] = field(default_factory=list)
    verification_criteria: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    estimated_tokens: int = 30_000
    actual_tokens_used: int | None = None
    completion_notes: str | None = None
    completed_at: datetime | None = None
    retry_count: int = 0

@dataclass
class ImplementationPlan:
    """Collection of tasks with dependency tracking."""
    tasks: list[Task] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_modified: datetime = field(default_factory=datetime.now)

    def get_next_task(self) -> Task | None: ...
    def get_task_by_id(self, task_id: str) -> Task | None: ...
    def mark_task_complete(self, task_id: str, notes: str | None = None, tokens: int | None = None) -> bool: ...
    def mark_task_blocked(self, task_id: str, reason: str) -> bool: ...

    @property
    def pending_count(self) -> int: ...
    @property
    def complete_count(self) -> int: ...
    @property
    def completion_percentage(self) -> float: ...

@dataclass
class CircuitBreakerState:
    """Circuit breaker for failure detection."""
    max_consecutive_failures: int = 3
    max_stagnation_iterations: int = 5
    max_cost_usd: float = 100.0
    state: str = "closed"  # closed, open, half-open
    failure_count: int = 0
    stagnation_count: int = 0
    last_failure_reason: str | None = None

    def record_failure(self, reason: str) -> None: ...
    def record_success(self) -> None: ...
    def is_open(self) -> bool: ...
    def should_trip(self) -> bool: ...

@dataclass
class RalphState:
    """Complete orchestrator state."""
    project_root: Path
    current_phase: Phase = Phase.BUILDING
    iteration_count: int = 0
    session_id: str | None = None
    total_cost_usd: float = 0.0
    total_tokens_used: int = 0
    started_at: datetime = field(default_factory=datetime.now)
    last_activity_at: datetime = field(default_factory=datetime.now)
    circuit_breaker: CircuitBreakerState = field(default_factory=CircuitBreakerState)
    session_cost_usd: float = 0.0
    session_tokens_used: int = 0
    tasks_completed_this_session: int = 0
    paused: bool = False

    def should_halt(self) -> tuple[bool, str | None]: ...
    def start_iteration(self) -> None: ...
    def end_iteration(self, cost_usd: float, tokens_used: int, task_completed: bool) -> None: ...
```

**Dependencies**: None (base layer)

---

### persistence.py - State I/O

**Purpose**: JSON serialization with atomic writes. Ensures state integrity even during crashes.

**Key Classes/Functions**:

```python
# Default file paths
STATE_FILE = ".ralph/state.json"
PLAN_FILE = ".ralph/implementation_plan.json"

class PersistenceError(Exception): ...
class StateNotFoundError(PersistenceError): ...
class CorruptedStateError(PersistenceError): ...

def save_state(state: RalphState, project_root: Path | None = None) -> Path: ...
def load_state(project_root: Path) -> RalphState: ...
def save_plan(plan: ImplementationPlan, project_root: Path) -> Path: ...
def load_plan(project_root: Path) -> ImplementationPlan: ...
def state_exists(project_root: Path) -> bool: ...
def plan_exists(project_root: Path) -> bool: ...
def initialize_state(project_root: Path) -> RalphState: ...
def initialize_plan(project_root: Path) -> ImplementationPlan: ...
def ensure_ralph_dir(project_root: Path) -> Path: ...

# Internal helpers
def _atomic_write(path: Path, data: dict[str, Any]) -> None: ...
def _serialize_dataclass(obj: Any) -> dict[str, Any]: ...
def _deserialize_ralph_state(data: dict[str, Any]) -> RalphState: ...
def _deserialize_implementation_plan(data: dict[str, Any]) -> ImplementationPlan: ...
```

**Dependencies**:
- `models.py` - All data models

---

### context.py - Context Management

**Purpose**: Manages context window budget and session hand-offs. Generates MEMORY.md for continuity.

**Key Classes/Functions**:

```python
@dataclass
class SessionArchive:
    """Archive of a completed session."""
    session_id: str
    iteration: int
    started_at: datetime
    ended_at: datetime
    tokens_used: int
    cost_usd: float
    tasks_completed: int
    phase: Phase
    handoff_reason: str

@dataclass
class ContextInjection:
    """User-provided context for next iteration."""
    timestamp: datetime
    content: str
    source: str  # user, system, test_failure
    priority: int = 0

@dataclass
class IterationContext:
    """Context assembled for a single iteration."""
    iteration: int
    phase: Phase
    session_id: str | None
    current_task: dict[str, Any] | None
    completed_tasks_this_session: int
    total_completed_tasks: int
    total_pending_tasks: int
    memory_content: str | None
    progress_learnings: list[str]
    injections: list[ContextInjection]
    remaining_tokens: int
    usage_percentage: float

@dataclass
class HandoffResult:
    """Result from executing a context hand-off."""
    success: bool
    reason: str
    memory_path: Path | None = None
    archive_path: Path | None = None
    next_session_id: str | None = None

def load_memory_file(project_root: Path) -> str | None: ...
def load_progress_file(project_root: Path, max_entries: int = 20) -> list[str]: ...
def load_injections(project_root: Path) -> list[ContextInjection]: ...
def clear_injections(project_root: Path) -> None: ...
def add_injection(project_root: Path, content: str, source: str = "user", priority: int = 0) -> None: ...
def build_iteration_context(state: RalphState, plan: ImplementationPlan, project_root: Path) -> IterationContext: ...
def generate_memory_content(state: RalphState, plan: ImplementationPlan, project_root: Path, ...) -> str: ...
def write_memory_file(content: str, project_root: Path) -> Path: ...
def archive_session(state: RalphState, handoff_reason: str, project_root: Path) -> Path: ...
def load_session_history(project_root: Path, limit: int = 50) -> list[SessionArchive]: ...
def execute_context_handoff(state: RalphState, plan: ImplementationPlan, project_root: Path, reason: str, ...) -> HandoffResult: ...
def should_trigger_handoff(state: RalphState) -> tuple[bool, str | None]: ...
```

**Dependencies**:
- `models.py` - RalphState, ImplementationPlan, Phase, TaskStatus
- `persistence.py` - For loading state (indirect)

---

### memory.py - Deterministic Memory System

**Purpose**: Provides harness-controlled memory capture at well-defined boundaries (phase transitions, iteration ends, session handoffs). Unlike LLM-dependent approaches, this ensures consistent memory capture regardless of LLM behavior.

**Key Classes/Functions**:

```python
@dataclass
class MemoryConfig:
    """Configuration for memory system."""
    max_active_memory_chars: int = 8000
    max_iteration_files: int = 20
    max_session_files: int = 10
    archive_retention_days: int = 30

@dataclass
class IterationMemory:
    """Memory snapshot from a single iteration."""
    iteration: int
    phase: Phase
    timestamp: datetime
    tasks_completed: list[str]
    tasks_blocked: list[str]
    progress_made: bool
    tokens_used: int
    cost_usd: float

@dataclass
class PhaseMemory:
    """Memory from a phase transition."""
    phase: Phase
    completed_at: datetime
    iterations_in_phase: int
    artifacts: dict[str, Any]
    summary: str

@dataclass
class SessionMemory:
    """Memory from a session handoff."""
    session_id: str
    ended_at: datetime
    iteration_count: int
    phase: Phase
    handoff_reason: str
    tasks_in_progress: list[str]
    tokens_used: int
    cost_usd: float

class MemoryManager:
    """Manages deterministic memory capture and retrieval."""

    def __init__(self, project_root: Path, config: MemoryConfig | None = None): ...

    # Capture methods (called by executors at boundaries)
    def capture_iteration_memory(self, state: RalphState, plan: ImplementationPlan, result: IterationResult) -> Path: ...
    def capture_phase_transition_memory(self, state: RalphState, plan: ImplementationPlan, old_phase: Phase, new_phase: Phase, artifacts: dict) -> Path: ...
    def capture_session_handoff_memory(self, state: RalphState, plan: ImplementationPlan, handoff_reason: str) -> Path: ...

    # Retrieval methods
    def build_active_memory(self, state: RalphState, plan: ImplementationPlan) -> str: ...
    def load_phase_memory(self, phase: Phase) -> str | None: ...
    def load_recent_iterations(self, limit: int = 5) -> list[IterationMemory]: ...

    # Cleanup methods
    def rotate_files(self) -> int: ...
    def cleanup_archive(self) -> int: ...

    # Directory management
    def _ensure_directories(self) -> None: ...
```

**Dependencies**:
- `models.py` - RalphState, ImplementationPlan, Phase, Task
- `sdk_client.py` - IterationResult

---

### config.py - Configuration

**Purpose**: YAML configuration loading with environment variable overrides. Defines cost limits and phase behavior.

**Key Classes/Functions**:

```python
@dataclass
class CostLimits:
    """Cost control limits."""
    per_iteration: float = 2.0
    per_session: float = 50.0
    total: float = 200.0

@dataclass
class PhaseConfig:
    """Configuration for a specific phase."""
    human_in_loop: bool = False
    max_questions: int = 10
    task_size_tokens: int = 30_000
    dependency_analysis: bool = True
    max_iterations: int = 100
    require_human_approval: bool = False
    backpressure: list[str] = field(default_factory=list)

@dataclass
class SafetyConfig:
    """Safety and sandboxing settings."""
    sandbox_enabled: bool = True
    blocked_commands: list[str] = field(default_factory=list)
    git_read_only: bool = True
    allowed_git_operations: list[str] = field(default_factory=list)

@dataclass
class BuildConfig:
    """Build system configuration."""
    tool: str = "uv"
    test_command: str = "uv run pytest"
    lint_command: str = "uv run ruff check ."
    typecheck_command: str = "uv run mypy ."

@dataclass
class RalphConfig:
    """Complete Ralph configuration."""
    project: ProjectConfig
    build: BuildConfig
    context: ContextConfig
    safety: SafetyConfig
    cost_limits: CostLimits
    discovery: PhaseConfig
    planning: PhaseConfig
    building: PhaseConfig
    validation: PhaseConfig
    primary_model: str = "claude-sonnet-4-20250514"
    planning_model: str = "claude-opus-4-20250514"
    max_iterations: int = 100
    circuit_breaker_failures: int = 3
    circuit_breaker_stagnation: int = 5

@dataclass
class CostController:
    """Controller for enforcing cost limits."""
    limits: CostLimits
    iteration_cost: float = 0.0
    session_cost: float = 0.0
    total_cost: float = 0.0

    def add_cost(self, cost: float) -> None: ...
    def check_limits(self) -> tuple[bool, str | None]: ...
    def get_remaining_budget(self) -> dict[str, float]: ...

def load_config(project_root: Path) -> RalphConfig: ...
def save_config(config: RalphConfig, project_root: Path) -> Path: ...
def create_default_config(project_root: Path, project_name: str = "") -> RalphConfig: ...
def create_cost_controller(config: RalphConfig) -> CostController: ...
```

**Dependencies**: None (configuration layer)

---

### verification.py - Validation Logic

**Purpose**: Runs backpressure commands and generates validation reports. Ensures code quality gates.

**Key Classes/Functions**:

```python
class VerificationStatus(str, Enum):
    """Status of a verification check."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"

@dataclass
class VerificationResult:
    """Result of a single verification check."""
    name: str
    status: VerificationStatus
    message: str | None = None
    output: str | None = None
    duration_seconds: float = 0.0

@dataclass
class TaskVerificationReport:
    """Complete verification report for a task."""
    task_id: str
    task_description: str
    overall_status: VerificationStatus
    checks: list[VerificationResult]
    total_duration_seconds: float = 0.0

    @property
    def all_passed(self) -> bool: ...

@dataclass
class ValidationReport:
    """Complete validation report for the project."""
    test_results: VerificationResult | None = None
    lint_results: VerificationResult | None = None
    typecheck_results: VerificationResult | None = None
    overall_status: VerificationStatus = VerificationStatus.PASSED

    @property
    def all_passed(self) -> bool: ...

def run_command(command: str, cwd: Path, timeout: int = 300) -> tuple[int, str, str]: ...
def verify_command(name: str, command: str, cwd: Path, timeout: int = 300) -> VerificationResult: ...
def run_tests(project_root: Path, config: RalphConfig | None = None) -> VerificationResult: ...
def run_linting(project_root: Path, config: RalphConfig | None = None) -> VerificationResult: ...
def run_typecheck(project_root: Path, config: RalphConfig | None = None) -> VerificationResult: ...
def run_backpressure(project_root: Path, commands: list[str] | None = None, config: RalphConfig | None = None) -> list[VerificationResult]: ...
def verify_task(task: Task, project_root: Path, config: RalphConfig | None = None) -> TaskVerificationReport: ...
def run_full_validation(project_root: Path, config: RalphConfig | None = None) -> ValidationReport: ...
def format_validation_report(report: ValidationReport) -> str: ...
```

**Dependencies**:
- `config.py` - RalphConfig, build commands
- `models.py` - Task

---

### iteration.py - Single Iteration Logic

**Purpose**: Connects the SDK client to LoopRunner. Manages single iteration execution lifecycle.

**Key Classes/Functions**:

```python
@dataclass
class IterationContext:
    """Context for a single iteration."""
    iteration: int
    phase: Phase
    system_prompt: str
    task: Task | None
    usage_percentage: float
    session_id: str | None

    def get_user_prompt(self) -> str: ...

def create_execute_function(project_root: Path, config: RalphConfig | None = None) -> Callable: ...

async def execute_single_iteration(project_root: Path, prompt: str | None = None, config: RalphConfig | None = None) -> IterationResult: ...

def run_iteration_sync(project_root: Path, prompt: str | None = None, config: RalphConfig | None = None) -> IterationResult: ...

async def execute_until_complete(project_root: Path, config: RalphConfig | None = None, max_iterations: int = 100, on_iteration: Callable | None = None) -> list[IterationResult]: ...
```

**Dependencies**:
- `sdk_client.py` - RalphSDKClient, IterationResult
- `phases.py` - get_phase_prompt
- `persistence.py` - State I/O
- `config.py` - RalphConfig
- `models.py` - Phase, Task

---

### sdk.py - SDK Utilities

**Purpose**: Utility functions and safety constants for SDK integration. Re-exports from sdk_client for API compatibility.

**Key Classes/Functions**:

```python
# Git operations that are blocked (read-only git)
BLOCKED_GIT_COMMANDS: list[str] = [
    "git commit", "git push", "git pull", "git merge",
    "git rebase", "git checkout", "git reset", ...
]

# Allowed git operations (read-only)
ALLOWED_GIT_COMMANDS: list[str] = [
    "git status", "git log", "git diff", "git show",
    "git ls-files", "git blame", "git branch",
]

# Package manager commands that are blocked (uv enforcement)
BLOCKED_PACKAGE_COMMANDS: list[str] = [
    "pip install", "pip uninstall", "python -m pip",
    "python -m venv", "virtualenv", "conda install",
    "poetry install", "pipenv install", ...
]

@dataclass
class CommandValidationResult:
    """Result of validating a bash command."""
    allowed: bool
    reason: str | None = None
    suggestion: str | None = None

def validate_bash_command(command: str) -> CommandValidationResult: ...
async def validate_tool_use_for_phase(tool_name: str, tool_input: dict, phase: Phase) -> CommandValidationResult: ...

# Re-exports from sdk_client
from ralph.sdk_client import (
    PHASE_TOOLS, IterationResult, RalphSDKClient,
    calculate_cost, calculate_max_turns,
    create_ralph_client, get_model_for_phase, get_tools_for_phase,
)
```

**Dependencies**:
- `sdk_client.py` - Core SDK functionality
- `models.py` - Phase

---

### templates/ - Prompt Templates

**Purpose**: Markdown templates for phase-specific system prompts. Supports variable substitution.

**Key Files**:
- `discovery.md` - Requirements gathering prompt
- `planning.md` - Task decomposition prompt
- `building.md` - Implementation prompt
- `validation.md` - Testing prompt

**Key Functions** (in `__init__.py`):

```python
TEMPLATES_DIR = Path(__file__).parent

def get_template_path(name: str) -> Path: ...
def load_template(name: str) -> str: ...
def render_template(name: str, **kwargs: Any) -> str: ...
```

**Dependencies**: None

---

## Key Design Decisions

### Why Python Orchestration Instead of LLM Control

**Decision**: Python code controls the loop, phases, and state transitions. The LLM executes within constraints.

**Rationale**:
1. **Determinism**: Python flow control is predictable; LLM behavior is not
2. **Auditability**: Every state change has a traceable code path
3. **Recovery**: Python can implement recovery strategies that LLMs cannot reliably self-execute
4. **Cost Control**: Hard limits can be enforced in code
5. **Safety**: Hooks can block operations before the LLM executes them

```
WRONG: Ask LLM "run the loop until done"
RIGHT: Python loop calls LLM per-iteration with explicit context
```

### Why JSON for State Persistence

**Decision**: State is persisted as human-readable JSON files.

**Rationale**:
1. **Debuggability**: Developers can inspect state with any text editor
2. **Version Control**: JSON diffs are meaningful in git
3. **Portability**: No database dependencies
4. **Recovery**: Manual state repair is possible
5. **Simplicity**: No ORM or migration overhead

**Trade-offs**:
- Performance: JSON parse/serialize on every operation (acceptable for iteration-level granularity)
- Concurrency: No built-in locking (Ralph is single-threaded by design)

### Why Atomic Writes for Data Integrity

**Decision**: State writes use temp file + rename pattern.

**Rationale**:
1. **Crash Safety**: Partial writes cannot corrupt state
2. **POSIX Guarantee**: `os.replace()` is atomic on same filesystem
3. **Recovery**: Either old state or new state exists, never partial

```python
# Implementation in persistence.py
def _atomic_write(path: Path, data: dict) -> None:
    fd, temp_path = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_path, path)  # Atomic!
    except:
        os.unlink(temp_path)
        raise
```

### Why MCP Tools for State Management

**Decision**: State mutations happen through MCP tools, not direct file access.

**Rationale**:
1. **Structured Interface**: LLM uses well-defined schemas
2. **Validation**: Tool implementations can reject invalid operations
3. **Tracking**: All state changes are logged
4. **Isolation**: LLM cannot bypass state management logic
5. **Extensibility**: New tools can be added without prompt changes

### Why Phase-Specific Tool Allocation

**Decision**: Each phase has a different set of available tools.

**Rationale**:
1. **Least Privilege**: Discovery phase cannot edit files
2. **Focus**: Validation phase cannot add new features
3. **Safety**: Planning phase cannot run arbitrary commands
4. **Guidance**: Tool availability shapes LLM behavior

```python
PHASE_TOOLS = {
    Phase.DISCOVERY: ["Read", "Glob", "WebSearch", "AskUserQuestion"],  # No edits
    Phase.PLANNING: ["Read", "Write", "ExitPlanMode"],                   # No bash
    Phase.BUILDING: ["Read", "Write", "Edit", "Bash", ...],              # Full access
    Phase.VALIDATION: ["Read", "Bash", "Task"],                          # No edits
}
```

---

## Data Flow Diagrams

### Iteration Execution Flow

```
                    +-------------------+
                    |   LoopRunner.run  |
                    +--------+----------+
                             |
                             v
                    +--------+----------+
                    | pre_iteration()   |
                    | - Load state      |
                    | - Build context   |
                    | - Get next task   |
                    +--------+----------+
                             |
                             v
                    +--------+----------+
                    |  execute_fn()     |
                    | (iteration.py)    |
                    +--------+----------+
                             |
                             v
              +--------------+--------------+
              |                             |
              v                             v
    +---------+---------+       +-----------+-----------+
    | Build SDK options |       | Build user prompt     |
    | - Phase tools     |       | - Task description    |
    | - Max turns       |       | - Verification criteria|
    | - Budget          |       | - Instructions        |
    +---------+---------+       +-----------+-----------+
              |                             |
              +-------------+---------------+
                            |
                            v
                  +---------+---------+
                  | sdk_client.run_   |
                  | iteration()       |
                  +---------+---------+
                            |
                            v
                  +---------+---------+
                  | Claude Agent SDK  |
                  | query()           |
                  +---------+---------+
                            |
            +---------------+---------------+
            |               |               |
            v               v               v
    +-------+-----+  +------+------+  +-----+-------+
    | Text output |  | Tool calls  |  | Metrics     |
    +-------------+  +------+------+  +-------------+
                            |
                            v
                    +-------+-------+
                    | Hooks validate|
                    | tool calls    |
                    +-------+-------+
                            |
            +---------------+---------------+
            |               |               |
            v               v               v
    +-------+-----+  +------+------+  +-----+-------+
    | Bash        |  | Edit/Write  |  | MCP Tools   |
    | commands    |  | file ops    |  | (state)     |
    +-------------+  +-------------+  +------+------+
                                             |
                                             v
                                    +--------+--------+
                                    | State persisted |
                                    | atomically      |
                                    +-----------------+
                            |
                            v
                    +-------+-------+
                    | post_iteration|
                    | - Track cost  |
                    | - Update state|
                    | - Check halt  |
                    +---------------+
```

### Phase Transition Flow

```
    +-------------+
    |  DISCOVERY  |
    | (Optional)  |
    +------+------+
           |
           | User provides requirements
           | OR exits discovery
           v
    +------+------+
    |  PLANNING   |
    | (Required)  |
    +------+------+
           |
           | Plan created with tasks
           | ExitPlanMode called
           v
    +------+------+
    |  BUILDING   |
    | (Main loop) |<-----------+
    +------+------+            |
           |                   |
           | Task completed    | More tasks
           v                   | remain
    +------+------+            |
    | All tasks   +---NO-------+
    | complete?   |
    +------+------+
           |
           | YES
           v
    +------+------+
    | VALIDATION  |
    +------+------+
           |
           | Tests pass?
           +---NO---> Back to BUILDING (fix issues)
           |
           | YES
           v
    +------+------+
    |  COMPLETE   |
    +-------------+
```

### Context Handoff Flow

```
    +------------------+
    | Iteration ends   |
    +--------+---------+
             |
             v
    +--------+---------+
    | Check handoff    |
    | trigger:         |
    | - Budget > 75%   |
    | - Phase change   |
    | - User request   |
    +--------+---------+
             |
             | Trigger detected
             v
    +--------+---------+
    | Generate MEMORY  |
    | - Completed tasks|
    | - Current task   |
    | - Decisions      |
    | - Files modified |
    +--------+---------+
             |
             v
    +--------+---------+
    | Archive session  |
    | to history.jsonl |
    +--------+---------+
             |
             v
    +--------+---------+
    | Clear injections |
    | (processed)      |
    +--------+---------+
             |
             v
    +--------+---------+
    | Reset context    |
    | budget           |
    +--------+---------+
             |
             v
    +--------+---------+
    | New session ID   |
    | Continue loop    |
    +------------------+
```

### Error Recovery Flow

```
    +------------------+
    | Iteration fails  |
    +--------+---------+
             |
             v
    +--------+---------+
    | Determine action:|
    | - API error?     |
    | - Tool failure?  |
    | - Cost exceeded? |
    +--------+---------+
             |
    +--------+--------+--------+--------+
    |        |        |        |        |
    v        v        v        v        v
+---+---+ +--+--+ +---+---+ +--+---+ +--+---+
| RETRY | | SKIP| |MANUAL | |RESET | |HAND- |
|       | | TASK| |INTERV.| |CIRCUIT| |OFF   |
+---+---+ +--+--+ +---+---+ +--+---+ +--+---+
    |        |        |        |        |
    v        v        v        |        v
+---+-------+--+  +---+---+    |    +---+---+
| Increment    |  | Pause |    |    | Save  |
| retry count  |  | loop  |    |    | state |
+---+----------+  +---+---+    |    +---+---+
    |                 |        |        |
    v                 v        |        v
+---+----------+  +---+---+    |    +---+---+
| Continue if  |  | Wait  |    |    | New   |
| < max_retry  |  | user  |    |    | session|
+---+----------+  +-------+    |    +-------+
    |                          |
    v                          v
+---+----------+         +-----+-----+
| Max retries? |         | Reset     |
| Mark BLOCKED |         | counters  |
+--------------+         | Continue  |
                         +-----------+
```

---

## Extension Points

### Adding New Phases

1. **Add Phase enum value** in `models.py`:

```python
class Phase(str, Enum):
    DISCOVERY = "discovery"
    PLANNING = "planning"
    BUILDING = "building"
    VALIDATION = "validation"
    DEPLOYMENT = "deployment"  # NEW
```

2. **Add tool allocation** in `sdk_client.py`:

```python
PHASE_TOOLS[Phase.DEPLOYMENT] = [
    "Read", "Bash", "BashOutput",
    "ralph_get_state_summary",
]
```

3. **Create executor** in `executors.py`:

```python
class DeploymentExecutor(PhaseExecutor):
    async def execute(self, context: IterationContext) -> ExecutionResult:
        ...
```

4. **Add prompt template** at `templates/deployment.md`

5. **Update phase transitions** in `phases.py`:

```python
def can_transition(from_phase: Phase, to_phase: Phase) -> bool:
    transitions = {
        Phase.VALIDATION: [Phase.DEPLOYMENT, Phase.BUILDING],
        Phase.DEPLOYMENT: [Phase.BUILDING],  # On failure
    }
    ...
```

6. **Add config section** in `config.py`:

```python
@dataclass
class RalphConfig:
    ...
    deployment: PhaseConfig = field(default_factory=lambda: PhaseConfig(
        require_human_approval=True,
    ))
```

### Adding New MCP Tools

1. **Define tool schema** in `mcp_tools.py`:

```python
RALPH_TOOLS.append({
    "name": "ralph_estimate_remaining",
    "description": "Estimate remaining work in tokens and cost",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
})
```

2. **Implement tool logic** in `tools.py`:

```python
class RalphTools:
    def estimate_remaining(self) -> ToolResult:
        plan = self._load_plan()
        pending = [t for t in plan.tasks if t.status == TaskStatus.PENDING]
        total_tokens = sum(t.estimated_tokens for t in pending)

        return ToolResult(
            success=True,
            content=f"Estimated {len(pending)} tasks, ~{total_tokens:,} tokens",
            data={
                "pending_tasks": len(pending),
                "estimated_tokens": total_tokens,
                "estimated_cost_usd": total_tokens * 0.00001,  # Rough estimate
            },
        )
```

3. **Add to tool definitions** in `tools.py`:

```python
TOOL_DEFINITIONS.append({
    "name": "ralph_estimate_remaining",
    "description": "Estimate remaining work in tokens and cost",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
})
```

4. **Wire up in MCP server** (if using MCP transport)

### Customizing Prompts

Prompts are loaded from `src/ralph/templates/`. To customize:

1. **Edit existing template** (e.g., `templates/building.md`):

```markdown
# Building Phase

You are implementing task: {task_description}

## Project Context
{project_context}

## Verification Criteria
{verification_criteria}

## Custom Instructions
{custom_instructions}
```

2. **Add new variables** in `phases.py`:

```python
def build_building_prompt(task: Task, project_root: Path, config: RalphConfig) -> str:
    return render_template(
        "building",
        task_description=task.description,
        project_context=load_project_context(project_root),
        verification_criteria="\n".join(task.verification_criteria),
        custom_instructions=config.building.custom_instructions,  # NEW
    )
```

3. **Update config** in `config.py`:

```python
@dataclass
class PhaseConfig:
    ...
    custom_instructions: str = ""
```

### Adding New CLI Commands

1. **Add command** in `cli.py`:

```python
@cli.command()
@click.argument("task_id")
@click.option("--notes", "-n", help="Completion notes")
def complete(task_id: str, notes: str | None) -> None:
    """Mark a task as complete manually."""
    from ralph.tools import create_tools

    project_root = Path.cwd()
    tools = create_tools(project_root)
    result = tools.mark_task_complete(task_id, notes)

    if result.success:
        click.echo(f"Task {task_id} marked complete")
    else:
        click.echo(f"Error: {result.error}", err=True)
```

2. **Add help text** to command group docstring

3. **Add tests** in `tests/test_cli.py`:

```python
def test_complete_command(project_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["complete", "task-1", "-n", "Done"])
    assert result.exit_code == 0
```

---

## Testing Architecture

### Test Organization

```
tests/
    __init__.py
    test_cli.py           # CLI command tests
    test_config.py        # Configuration tests
    test_context.py       # Context management tests
    test_executors.py     # Phase executor tests
    test_iteration.py     # Iteration logic tests
    test_mcp_tools.py     # MCP tool definition tests
    test_models.py        # Data model tests
    test_persistence.py   # State I/O tests
    test_phases.py        # Phase management tests
    test_runner.py        # Loop runner tests
    test_sdk.py           # SDK utility tests
    test_sdk_client.py    # SDK client tests
    test_sdk_hooks.py     # Safety hook tests
    test_templates.py     # Template rendering tests
    test_tools.py         # Tool implementation tests
    test_verification.py  # Verification tests
```

### Mocking Strategy for Claude SDK

The SDK client is mocked to avoid API calls during tests:

```python
from unittest.mock import MagicMock, patch

@patch("ralph.sdk_client._get_ralph_hooks")
@patch("ralph.sdk_client._get_mcp_server")
def test_client_initialization(mock_mcp: MagicMock, mock_hooks: MagicMock) -> None:
    """Test client can be created without API calls."""
    mock_hooks.return_value = {"PreToolUse": []}
    mock_mcp.return_value = MagicMock()

    state = create_mock_state()
    client = RalphSDKClient(state=state, auto_configure=True)

    assert client.hooks is not None
```

**Key Mocking Patterns**:

1. **Mock hooks and MCP server creation** - Avoids SDK initialization side effects
2. **Mock state with helper functions** - Consistent test fixtures
3. **Patch SDK query function** - Test iteration logic without API
4. **Use tmp_path fixture** - Isolated filesystem per test

```python
# Helper to create test state
def create_mock_state(
    phase: Phase = Phase.BUILDING,
    session_cost: float = 0.0,
    project_root: Path | None = None,
) -> RalphState:
    state = RalphState(project_root=project_root or Path("/tmp/test"))
    state.current_phase = phase
    state.session_cost_usd = session_cost
    return state
```

### Integration Test Patterns

Integration tests use pytest's `tmp_path` fixture for isolation:

```python
@pytest.fixture
def project_path(tmp_path: Path) -> Path:
    """Create an initialized project directory."""
    initialize_state(tmp_path)
    initialize_plan(tmp_path)
    return tmp_path

@pytest.fixture
def plan_with_tasks(project_path: Path) -> ImplementationPlan:
    """Create a plan with test tasks."""
    plan = ImplementationPlan(
        tasks=[
            Task(id="task-1", description="First task", priority=1),
            Task(id="task-2", description="Second task", priority=2, dependencies=["task-1"]),
        ]
    )
    save_plan(plan, project_path)
    return plan

def test_loop_runner_completes_tasks(project_path: Path, plan_with_tasks: ImplementationPlan) -> None:
    """Integration test for task completion."""
    runner = LoopRunner(project_path)

    # Mock execute function that completes tasks
    async def mock_execute(context: dict) -> tuple:
        tools = RalphTools(project_path)
        result = tools.mark_task_complete(context["task"]["id"])
        return (0.01, 1000, True, context["task"]["id"], None)

    result = asyncio.run(runner.run(mock_execute, max_iterations=5))

    assert result.status == LoopStatus.COMPLETED
    assert result.iterations_completed == 2
```

### Async Test Patterns

Async tests use `pytest.mark.asyncio`:

```python
import pytest

@pytest.mark.asyncio
async def test_run_iteration_handles_errors() -> None:
    """Test error handling in async iteration."""
    with patch("ralph.sdk_client.ClaudeSDKClient", side_effect=ConnectionError("Network error")):
        state = create_mock_state()
        client = RalphSDKClient(state=state, auto_configure=False)

        result = await client.run_iteration("test prompt")

        assert result.success is False
        assert "Connection error" in result.error
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=ralph --cov-report=html

# Run specific test file
uv run pytest tests/test_runner.py

# Run specific test
uv run pytest tests/test_runner.py::test_loop_completes

# Run with verbose output
uv run pytest -v

# Run type checking
uv run mypy .

# Run linting
uv run ruff check .
```

---

## File Locations Reference

| File | Purpose |
|------|---------|
| `src/ralph/cli.py` | CLI entry point |
| `src/ralph/runner.py` | Loop orchestration |
| `src/ralph/executors.py` | Phase executors |
| `src/ralph/phases.py` | Phase management |
| `src/ralph/sdk_client.py` | Claude SDK wrapper |
| `src/ralph/sdk_hooks.py` | Safety hooks |
| `src/ralph/mcp_tools.py` | MCP tool schemas |
| `src/ralph/tools.py` | Tool implementations |
| `src/ralph/models.py` | Data models |
| `src/ralph/persistence.py` | State I/O |
| `src/ralph/context.py` | Context management |
| `src/ralph/memory.py` | Deterministic memory capture |
| `src/ralph/config.py` | Configuration |
| `src/ralph/verification.py` | Validation logic |
| `src/ralph/iteration.py` | Iteration logic |
| `src/ralph/sdk.py` | SDK utilities |
| `src/ralph/templates/` | Prompt templates |
| `.ralph/state.json` | Runtime state |
| `.ralph/implementation_plan.json` | Task plan |
| `.ralph/config.yaml` | Project config |
| `.ralph/MEMORY.md` | Active memory for prompt injection |
| `.ralph/memory/` | Deterministic memory files |
| `progress.txt` | Learnings log |
