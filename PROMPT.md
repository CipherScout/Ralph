# Product Requirements Document: Ralph Agentic Coding Loop

## Python Implementation Using Claude Agent SDK

**Version:** 1.1 | **Target:** Python 3.14+ | **Date:** January 26, 2026

**Don't Stop until all the features are implemented.**
---

The Ralph pattern transforms AI-assisted coding from a single-shot context gamble into a deterministic, iterative workflow where an LLM operates in fresh context windows while persistent state lives in external files. This PRD specifies a Python implementation built on Claude Agent SDK that brings **predictability through Python-driven control flow** while leveraging the LLM's judgment for task execution—not orchestration.

**Core Philosophy:** "Sit on the loop, not in it." Ralph treats context windows as disposable compute resources that get garbage-collected after each iteration. Memory persists through git history, JSON state files, and markdown documents—never in LLM context.

**Don't Stop until all the features are implemented.**

---

## 1. System architecture and control flow

### Python as the orchestration layer

The fundamental architectural decision: **Python code controls all workflow transitions, state management, and decision points**. The LLM acts as an execution engine for individual tasks, not as the system's brain.

| Component | Controlled By | Rationale |
|-----------|--------------|-----------|
| Phase transitions | Python | Deterministic workflow progression |
| Task selection | Python (from JSON state) | Eliminates LLM task-filtering failures (70-80% reliability per Huntley) |
| Context budget tracking | Python | Precise token counting before each call |
| Exit conditions | Python + LLM confirmation | Dual-gate prevents premature exits |
| State persistence | Python (JSON/Markdown) | Survives context resets |
| Error recovery | Python (circuit breaker) | Deterministic retry/halt logic |

**Don't Stop until all the features are implemented.**

### Loop mechanics

Each iteration follows this Python-orchestrated sequence:

```python
async def ralph_iteration(state: RalphState, client: ClaudeSDKClient) -> IterationResult:
    # 1. Python reads current state from disk
    context = load_iteration_context(state)
    
    # 2. Python selects next task (deterministic)
    task = select_highest_priority_incomplete_task(state.implementation_plan)
    
    # 3. Python constructs prompt with precise token budget
    prompt = build_task_prompt(task, context, token_budget=estimate_available_tokens())
    
    # 4. LLM executes task with fresh context
    async for message in client.query(prompt):
        process_streaming_output(message)
    
    # 5. Python validates completion and updates state
    result = validate_task_completion(task, state)
    persist_state_to_disk(state)
    
    return result
```

The `ClaudeSDKClient` provides session continuity within a phase, while **phase transitions always start fresh sessions** to prevent context accumulation.

### Directory structure

```
project-root/
├── .ralph/                          # Ralph control directory
│   ├── state.json                   # Master state (current phase, iteration count, costs)
│   ├── implementation_plan.json     # Tasks with status, priority, dependencies
│   ├── context_budget.json          # Token tracking per iteration
│   ├── circuit_breaker.json         # Error counts, stagnation detection
│   └── session_history/             # Archived session summaries
├── specs/                           # Requirements (Markdown)
│   └── {feature_name}.md
├── AGENTS.md                        # Operational learnings (~60 lines max)
├── MEMORY.md                        # Current session context for hand-off
├── PROMPT_discovery.md              # Phase 1 instructions
├── PROMPT_plan.md                   # Phase 2 instructions  
├── PROMPT_build.md                  # Phase 3 instructions
├── progress.txt                     # Append-only learnings log
├── pyproject.toml                   # Project configuration (uv managed)
└── uv.lock                          # Locked dependencies (uv managed)
```

---

## 2. Build, environment, and package management with uv

### uv as the required toolchain

Ralph **exclusively uses `uv`** for all Python build, environment, and package management. This is a hard requirement—no fallback to `pip`, `venv`, `poetry`, `pipenv`, or other tools.

**Rationale:**
- **Speed:** uv is 10-100x faster than pip for dependency resolution and installation
- **Determinism:** Lock files ensure reproducible builds across environments
- **Simplicity:** Single tool replaces pip + venv + pip-tools + poetry
- **Modern:** Native support for Python 3.14+ and pyproject.toml standards

### Project initialization

```bash
# Initialize Ralph project with uv
uv init ralph --python 3.14

# Or add to existing project
cd existing-project
uv init --python 3.14
```

### pyproject.toml configuration

```toml
[project]
name = "ralph"
version = "0.1.0"
description = "Deterministic agentic coding loop using Claude Agent SDK"
readme = "README.md"
requires-python = ">=3.14"
license = { text = "MIT" }
authors = [
    { name = "Your Name", email = "you@example.com" }
]

dependencies = [
    "claude-agent-sdk>=0.1.0",
    "rich>=13.0.0",           # CLI formatting
    "typer>=0.12.0",          # CLI framework
    "pydantic>=2.0.0",        # Data validation
    "aiofiles>=24.0.0",       # Async file I/O
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.6.0",
    "mypy>=1.11.0",
]

[project.scripts]
ralph = "ralph.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py314"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "C4", "SIM"]

[tool.mypy]
python_version = "3.14"
strict = true
warn_return_any = true
warn_unused_ignores = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### uv commands for Ralph development

```bash
# Environment setup
uv sync                          # Install all dependencies from lock file
uv sync --dev                    # Include dev dependencies

# Dependency management
uv add claude-agent-sdk          # Add a dependency
uv add --dev pytest              # Add dev dependency
uv remove package-name           # Remove a dependency
uv lock                          # Update lock file without installing

# Running Ralph
uv run ralph                     # Run via entry point
uv run python -m ralph           # Run as module
uv run pytest                    # Run tests

# Environment info
uv python list                   # List available Python versions
uv python install 3.14           # Install Python 3.14 if needed
```

### Agent instructions for uv usage

Ralph's agent prompts must instruct Claude to use `uv` exclusively:

```markdown
## Build System Requirements

This project uses `uv` exclusively for Python environment and package management.

**CRITICAL RULES:**
1. NEVER use `pip install` - use `uv add <package>` instead
2. NEVER use `python -m venv` - uv manages environments automatically
3. NEVER use `pip freeze` - use `uv lock` for dependency locking
4. ALWAYS run Python commands via `uv run <command>`
5. ALWAYS add new dependencies via `uv add <package>`

**Common Commands:**
- Install dependencies: `uv sync`
- Add package: `uv add <package>`
- Add dev package: `uv add --dev <package>`
- Run tests: `uv run pytest`
- Run linting: `uv run ruff check .`
- Run type checking: `uv run mypy .`
- Run the project: `uv run ralph <args>`
```

### Integration with verification criteria

All task verification must use `uv run`:

```python
VERIFICATION_COMMANDS = {
    "tests": "uv run pytest",
    "typecheck": "uv run mypy .",
    "lint": "uv run ruff check .",
    "format_check": "uv run ruff format --check .",
    "all": "uv run pytest && uv run mypy . && uv run ruff check .",
}

async def verify_task_completion(task: Task, state: RalphState) -> VerificationResult:
    """Run verification commands using uv."""
    results = []
    for criterion in task.verification_criteria:
        if criterion in VERIFICATION_COMMANDS:
            cmd = VERIFICATION_COMMANDS[criterion]
        else:
            cmd = criterion  # Custom verification command
        
        # Ensure uv run prefix for Python commands
        if not cmd.startswith("uv run") and needs_python_env(cmd):
            cmd = f"uv run {cmd}"
        
        result = await run_bash_command(cmd, cwd=state.project_root)
        results.append(VerificationStepResult(
            criterion=criterion,
            command=cmd,
            passed=result.exit_code == 0,
            output=result.output
        ))
    
    return VerificationResult(
        all_passed=all(r.passed for r in results),
        steps=results
    )
```

---

## 3. Claude Agent SDK integration

### Complete tool inventory

The Claude Agent SDK provides a comprehensive set of built-in tools. Ralph leverages these across different phases:

| Tool | Category | Description | Ralph Usage |
|------|----------|-------------|-------------|
| **Read** | File I/O | Read file contents with optional line ranges | All phases - code analysis, spec review |
| **Write** | File I/O | Create new files or overwrite existing | Building phase - create new files |
| **Edit** | File I/O | Make precise edits to existing files | Building phase - modify code |
| **Bash** | Execution | Run terminal commands with timeout/background support | All phases - tests, linting, builds |
| **BashOutput** | Execution | Get output from background shell processes | Building phase - monitor long-running tasks |
| **KillBash** | Execution | Terminate background shell processes | Building phase - stop hung processes |
| **Glob** | Search | Find files by pattern matching | All phases - discover project structure |
| **Grep** | Search | Search file contents with regex | All phases - find implementations, patterns |
| **WebSearch** | Research | Search the web for information | Discovery/Planning - research best practices |
| **WebFetch** | Research | Fetch and analyze web page content | Discovery/Planning - read documentation |
| **Task** | Subagents | Spawn isolated subagents for complex operations | All phases - context isolation |
| **AskUserQuestion** | Interaction | Ask clarifying questions with structured options | Discovery - requirements gathering |
| **TodoWrite** | Tracking | Maintain task list with status tracking | Building - progress tracking |
| **NotebookEdit** | Specialized | Edit Jupyter notebook cells | Optional - data science projects |
| **ListMcpResources** | MCP | List available MCP server resources | Integration with external tools |
| **ReadMcpResource** | MCP | Read MCP resource content | Integration with external tools |
| **ExitPlanMode** | Control | Exit planning mode with user approval | Planning phase finalization |
| **Memory** | Persistence | Store/retrieve information across conversations | Session continuity (API-level tool) |
| **ToolSearch** | Discovery | Dynamically discover tools from large catalogs | Projects with many MCP tools |

### Tool allocation by phase

```python
from claude_agent_sdk import (
    ClaudeSDKClient, ClaudeAgentOptions, HookMatcher,
    tool, create_sdk_mcp_server
)

# Complete tool list organized by phase
DISCOVERY_TOOLS = [
    "Read", "Glob", "Grep",           # Analyze existing code
    "WebSearch", "WebFetch",          # Research best practices
    "Write",                          # Create spec files
    "Task",                           # Delegate research subtasks
    "AskUserQuestion",                # Clarify requirements
]

PLANNING_TOOLS = [
    "Read", "Glob", "Grep",           # Analyze codebase
    "WebSearch", "WebFetch",          # Research solutions
    "Write",                          # Create implementation plan
    "Task",                           # Parallel analysis via subagents
    "ExitPlanMode",                   # Finalize planning
]

BUILDING_TOOLS = [
    "Read", "Write", "Edit",          # Core file operations
    "Bash", "BashOutput", "KillBash", # Full command execution suite
    "Glob", "Grep",                   # Code search
    "Task",                           # Subagents for isolated work
    "TodoWrite",                      # Track task progress
    "WebSearch", "WebFetch",          # Look up documentation
    "NotebookEdit",                   # Optional: Jupyter support
]

VALIDATION_TOOLS = [
    "Read", "Glob", "Grep",           # Review implementation
    "Bash",                           # Run tests, linting (via uv run)
    "Task",                           # Delegate verification
    "WebFetch",                       # Visual verification (dev-browser)
]

def create_ralph_client(phase: Phase, state: RalphState) -> ClaudeAgentOptions:
    phase_tools = {
        Phase.DISCOVERY: DISCOVERY_TOOLS,
        Phase.PLANNING: PLANNING_TOOLS,
        Phase.BUILDING: BUILDING_TOOLS,
        Phase.VALIDATION: VALIDATION_TOOLS,
    }
    
    return ClaudeAgentOptions(
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            "append": load_phase_prompt(phase)
        },
        allowed_tools=phase_tools[phase],
        disallowed_tools=[],
        permission_mode='acceptEdits',
        cwd=state.project_root,
        max_turns=calculate_max_turns(phase),
        setting_sources=["project"],  # Load CLAUDE.md
        hooks={
            'PreToolUse': [HookMatcher(hooks=[validate_tool_use])],
            'PostToolUse': [HookMatcher(hooks=[track_tool_usage])]
        },
        mcp_servers={"ralph": create_ralph_mcp_server()}
    )
```

### Custom tools via MCP

Ralph exposes custom tools for structured state management:

```python
@tool("ralph_get_next_task", "Get the highest-priority incomplete task", {})
async def get_next_task(args: dict) -> dict:
    state = load_state()
    task = select_next_task(state.implementation_plan)
    return {"content": [{"type": "text", "text": json.dumps(task)}]}

@tool("ralph_mark_task_complete", "Mark a task as completed", {
    "task_id": str,
    "verification_notes": str
})
async def mark_complete(args: dict) -> dict:
    update_task_status(args["task_id"], "complete", args["verification_notes"])
    return {"content": [{"type": "text", "text": "Task marked complete"}]}

@tool("ralph_append_learning", "Record a learning for future iterations", {
    "learning": str,
    "category": str  # "pattern", "antipattern", "architecture", "debugging"
})
async def append_learning(args: dict) -> dict:
    append_to_progress_file(args["learning"], args["category"])
    return {"content": [{"type": "text", "text": "Learning recorded"}]}
```

### Hooks for deterministic control

Hooks intercept tool calls for validation, logging, and safety:

```python
async def validate_tool_use(input_data: dict, tool_use_id: str, context: HookContext) -> dict:
    tool_name = input_data.get('tool_name')
    tool_input = input_data.get('tool_input', {})
    
    # Block git operations that affect repository state
    if tool_name == 'Bash':
        command = tool_input.get('command', '')
        blocked_patterns = ['git commit', 'git push', 'git checkout', 'git merge', 
                          'git rebase', 'git reset', 'git stash']
        if any(pattern in command for pattern in blocked_patterns):
            return {
                'hookSpecificOutput': {
                    'hookEventName': 'PreToolUse',
                    'permissionDecision': 'deny',
                    'permissionDecisionReason': 'Git state operations blocked by Ralph'
                }
            }
        
        # Enforce uv usage - block pip/venv commands
        pip_patterns = ['pip install', 'pip uninstall', 'pip freeze', 'python -m pip']
        venv_patterns = ['python -m venv', 'virtualenv', 'conda create', 'conda install']
        
        if any(pattern in command for pattern in pip_patterns + venv_patterns):
            return {
                'hookSpecificOutput': {
                    'hookEventName': 'PreToolUse',
                    'permissionDecision': 'deny',
                    'permissionDecisionReason': 'Use uv instead: uv add <package> or uv sync'
                }
            }
    
    # Track token usage for context budgeting
    track_tool_tokens(tool_name, tool_input)
    return {}
```

---

## 4. Context window management

### The 80% threshold strategy

Research shows **token usage explains 80% of performance variance** in agent tasks. Ralph targets **40-60% context utilization** (the "smart zone") and triggers hand-off before reaching 80%.

```python
@dataclass
class ContextBudget:
    total_capacity: int = 200_000
    system_prompt_allocation: int = 5_000
    safety_margin: float = 0.20  # Keep 20% buffer
    
    @property
    def effective_capacity(self) -> int:
        return int(self.total_capacity * (1 - self.safety_margin))
    
    @property
    def smart_zone_max(self) -> int:
        return int(self.total_capacity * 0.60)

class TokenTracker:
    def __init__(self, budget: ContextBudget):
        self.budget = budget
        self.current_usage = 0
        self.tool_results_tokens = 0
    
    def should_handoff(self) -> bool:
        return self.current_usage >= self.budget.smart_zone_max
    
    def estimate_remaining(self) -> int:
        return self.budget.effective_capacity - self.current_usage
```

### Hand-off protocol

When approaching context limits, Ralph executes a structured hand-off:

```python
async def execute_context_handoff(client: ClaudeSDKClient, state: RalphState):
    # 1. Request session summary from LLM
    summary_prompt = """
    Summarize this session for the next iteration:
    - Tasks completed and their outcomes
    - Current task in progress and its state
    - Architectural decisions made
    - Unresolved issues or blockers
    - Files modified (5 most important)
    Format as structured MEMORY.md content.
    """
    
    summary = await get_completion(client, summary_prompt)
    
    # 2. Python writes memory file
    write_memory_file(summary, state.iteration_count)
    
    # 3. Archive session metrics
    archive_session({
        "iteration": state.iteration_count,
        "tokens_used": state.token_tracker.current_usage,
        "tasks_completed": count_completed_this_session(state),
        "duration_ms": state.session_duration_ms
    })
    
    # 4. Return control to main loop for fresh session
    return HandoffResult(reason="context_budget", summary_path="MEMORY.md")
```

### Subagents for context isolation

Claude Agent SDK's `Task` tool spawns subagents with isolated context windows. Ralph uses this pattern for expensive operations:

```python
SUBAGENT_PATTERNS = {
    "code_search": {
        "description": "Search codebase for patterns/implementations",
        "max_tokens": 50_000,
        "returns": "Summary of findings only"
    },
    "file_analysis": {
        "description": "Deep analysis of specific files",
        "max_tokens": 30_000,
        "returns": "Structured analysis, not raw content"
    },
    "test_execution": {
        "description": "Run tests and analyze failures",
        "max_tokens": 40_000,
        "returns": "Pass/fail status and failure summaries"
    }
}
```

**Critical constraint:** Only **one subagent at a time** for build/test operations to provide proper backpressure.

---

## 5. Development lifecycle phases

### Phase 1: Discovery and requirements

**Objective:** Transform user intent into structured specifications through interactive conversation.

```python
class DiscoveryPhase:
    """
    Interactive requirements gathering using JTBD framework.
    Human remains in-the-loop during this phase.
    """
    
    async def run(self, initial_request: str) -> DiscoveryResult:
        async with ClaudeSDKClient(options=discovery_options()) as client:
            # Structured conversation flow
            await client.query(f"""
            You are helping define requirements for: {initial_request}
            
            Follow this process:
            1. Identify Jobs to Be Done (JTBD) - what outcomes does the user need?
            2. For each JTBD, identify topics of concern
            3. Use WebSearch to gather relevant context and best practices
            4. Ask clarifying questions (use AskUserQuestion tool)
            5. Write specs/{topic}.md for each topic of concern
            
            Output format for each spec:
            - Problem statement
            - Success criteria (measurable)
            - Constraints and non-goals
            - Acceptance criteria (testable)
            
            BUILD SYSTEM: This project uses uv. When specifying dependencies,
            note they will be added via `uv add <package>`.
            """)
            
            # Collect all specs written
            specs = await self.collect_generated_specs()
            return DiscoveryResult(specs=specs, jtbd_count=len(specs))
```

**User interaction:** This is the primary human-in-the-loop phase. The LLM uses `AskUserQuestion` tool for clarifications.

### Phase 2: Planning

**Objective:** Gap analysis between specs and existing code, producing a prioritized implementation plan.

```python
class PlanningPhase:
    """
    Autonomous planning with no implementation.
    Reads specs and existing code, outputs structured plan.
    """
    
    async def run(self, specs: List[Path], project_root: Path) -> PlanningResult:
        async with ClaudeSDKClient(options=planning_options()) as client:
            await client.query(f"""
            PLANNING MODE - No implementation allowed.
            
            1. ORIENT: Use subagents to study each spec in specs/
            2. ANALYZE: Use subagents to study existing code in {project_root}
            3. GAP ANALYSIS: Compare specs against implementation
            4. PLAN: Create implementation_plan.json with:
               - Tasks sized for single context window (~30 min work each)
               - Clear dependencies between tasks
               - Priority ordering (critical path first)
               - Verification criteria for each task
            
            Task sizing rules:
            - GOOD: "Add database column and migration for user.email_verified"
            - GOOD: "Create UserProfile React component with props interface"
            - TOO BIG: "Build entire authentication system" → split into 5-10 tasks
            
            BUILD SYSTEM: All commands must use uv:
            - Tests: `uv run pytest`
            - Linting: `uv run ruff check .`
            - Type check: `uv run mypy .`
            - Add deps: `uv add <package>`
            
            Output implementation_plan.json when complete.
            """)
            
            plan = load_implementation_plan()
            return PlanningResult(plan=plan, task_count=len(plan.tasks))
```

**Key constraint:** Plan regeneration is cheap. If the plan diverges from reality, regenerate rather than patch.

### Phase 3: Building

**Objective:** Iterative implementation with verification after each task.

```python
class BuildingPhase:
    """
    Main Ralph loop - one task per iteration.
    Python controls task selection; LLM executes.
    """
    
    async def run(self, plan: ImplementationPlan, max_iterations: int) -> BuildResult:
        state = RalphState(plan=plan)
        
        for iteration in range(max_iterations):
            # Python selects task (deterministic)
            task = self.select_next_task(state)
            if task is None:
                break  # All tasks complete
            
            # Execute iteration with fresh or continued session
            result = await self.execute_iteration(task, state)
            
            # Python evaluates result
            if result.needs_handoff:
                await self.execute_context_handoff(state)
            
            if result.task_complete:
                self.mark_task_complete(task, state)
            
            # Circuit breaker check
            if self.circuit_breaker.should_halt(state):
                return BuildResult(status="halted", reason=self.circuit_breaker.reason)
        
        return BuildResult(status="complete", iterations=iteration)
    
    async def execute_iteration(self, task: Task, state: RalphState) -> IterationResult:
        async with ClaudeSDKClient(options=build_options(state)) as client:
            prompt = f"""
            BUILDING MODE - Iteration {state.iteration_count}
            
            Read MEMORY.md and progress.txt for context from previous sessions.
            
            YOUR SINGLE TASK: {task.description}
            
            VERIFICATION CRITERIA:
            {json.dumps(task.verification_criteria)}
            
            BUILD SYSTEM (CRITICAL):
            - Run tests: `uv run pytest`
            - Run linting: `uv run ruff check .`
            - Run typecheck: `uv run mypy .`
            - Add dependency: `uv add <package>`
            - Add dev dependency: `uv add --dev <package>`
            - NEVER use pip install or python -m venv
            
            PROCESS:
            1. INVESTIGATE - Use subagents to study relevant code
            2. IMPLEMENT - Make changes using Write/Edit tools
            3. VALIDATE - Run `uv run pytest && uv run mypy . && uv run ruff check .`
            4. VERIFY - Confirm all verification criteria pass
            5. DOCUMENT - Update AGENTS.md if you learned something reusable
            
            Use ralph_mark_task_complete tool when done.
            Use ralph_append_learning for discoveries.
            
            If task cannot be completed this iteration, document progress in MEMORY.md.
            """
            
            await client.query(prompt)
            return self.evaluate_iteration_outcome(client, task, state)
```

### Phase 4: Testing and validation

**Objective:** Comprehensive verification before marking work complete.

```python
class ValidationPhase:
    """
    Final verification phase with human approval checkpoint.
    """
    
    async def run(self, build_result: BuildResult) -> ValidationResult:
        # Automated verification using uv
        test_results = await self.run_command("uv run pytest --tb=short")
        lint_results = await self.run_command("uv run ruff check .")
        type_results = await self.run_command("uv run mypy .")
        
        # LLM-assisted verification for subjective criteria
        async with ClaudeSDKClient(options=validation_options()) as client:
            await client.query(f"""
            VALIDATION MODE
            
            Automated results:
            - Tests: {test_results.summary}
            - Lint: {lint_results.summary}
            - Types: {type_results.summary}
            
            For each spec in specs/:
            1. Verify implementation meets acceptance criteria
            2. For UI features, use dev-browser skill to visually verify
            3. Document any gaps or regressions
            
            Output validation_report.json with pass/fail for each spec.
            """)
        
        report = load_validation_report()
        
        # Human checkpoint
        if report.has_failures:
            return ValidationResult(status="needs_review", report=report)
        
        return ValidationResult(status="passed", report=report)
```

---

## 6. State management

### JSON state schema

```python
@dataclass
class RalphState:
    """Master state persisted to .ralph/state.json"""
    
    project_root: Path
    current_phase: Phase  # discovery | planning | building | validation
    iteration_count: int
    session_id: Optional[str]
    
    # Cost tracking
    total_cost_usd: float
    total_tokens_used: int
    
    # Timing
    started_at: datetime
    last_activity_at: datetime
    
    # Circuit breaker state
    consecutive_failures: int
    stagnation_count: int  # iterations without progress
    
    def to_json(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_json(cls, data: dict) -> 'RalphState':
        return cls(**data)

@dataclass 
class ImplementationPlan:
    """Persisted to .ralph/implementation_plan.json"""
    
    @dataclass
    class Task:
        id: str
        description: str
        priority: int  # 1 = highest
        status: str  # pending | in_progress | complete | blocked
        dependencies: List[str]  # task IDs
        verification_criteria: List[str]
        estimated_tokens: int
        actual_tokens_used: Optional[int]
        completion_notes: Optional[str]
        completed_at: Optional[datetime]
    
    tasks: List[Task]
    created_at: datetime
    last_modified: datetime
    
    def get_next_task(self) -> Optional[Task]:
        """Deterministic selection: highest priority incomplete task with met dependencies"""
        available = [t for t in self.tasks 
                    if t.status == "pending" 
                    and self._dependencies_met(t)]
        return min(available, key=lambda t: t.priority) if available else None
```

### Markdown memory format

**MEMORY.md** captures session context for hand-off:

```markdown
# Session Memory - Iteration 47

## Completed This Session
- [x] Added user.email_verified column migration
- [x] Updated User model with new field
- [x] Added email verification endpoint

## Current Task In Progress
Task ID: task-023
Description: Implement email verification flow
Progress: Email sending works, need to add token verification endpoint

## Architectural Decisions
- Using JWT for verification tokens (24h expiry)
- Storing verification state in users table, not separate table

## Files Modified
1. db/migrations/004_add_email_verified.py
2. models/user.py
3. routes/auth.py
4. services/email.py
5. tests/test_email_verification.py

## Blockers/Issues
- SMTP config needs environment variables (documented in .env.example)

## Notes for Next Session
- Token verification endpoint needs rate limiting
- Consider adding verification email resend endpoint

## Dependencies Added
- `uv add python-jose` for JWT handling
- `uv add --dev pytest-asyncio` for async test support
```

**progress.txt** is append-only operational learnings:

```
[2026-01-25 14:32:01] PATTERN: Use Pydantic models for all API responses - caught 3 bugs
[2026-01-25 15:45:22] ANTIPATTERN: Don't assume endpoint doesn't exist - always grep first
[2026-01-25 16:20:15] ARCHITECTURE: Rate limiting middleware goes in middleware/, not routes/
[2026-01-25 17:05:33] DEBUGGING: Test failures often mean missing fixture - check conftest.py
[2026-01-25 17:30:00] BUILD: Always use `uv run pytest` not `pytest` directly
```

---

## 7. CLI interface

### Command structure

```bash
# Initialize Ralph in a project (creates pyproject.toml with uv)
ralph init [--project-root PATH]

# Run full lifecycle
ralph run "Build a user authentication system with email verification"

# Run specific phase
ralph discover "User authentication requirements"
ralph plan
ralph build [--max-iterations 50]
ralph validate

# Monitoring and control
ralph status                    # Current state summary
ralph status --verbose          # Detailed iteration history
ralph pause                     # Graceful pause after current iteration
ralph resume                    # Resume paused session
ralph reset [--keep-specs]      # Reset to clean state

# State inspection
ralph tasks                     # List all tasks with status
ralph tasks --pending           # List incomplete tasks
ralph history                   # Session history with costs

# Manual intervention
ralph inject "Focus on the email sending functionality first"
ralph skip task-023             # Skip a problematic task
ralph regenerate-plan           # Discard plan and re-plan from specs

# Development helpers (all use uv internally)
ralph test                      # Run uv run pytest
ralph lint                      # Run uv run ruff check .
ralph typecheck                 # Run uv run mypy .
ralph deps add <package>        # Run uv add <package>
ralph deps sync                 # Run uv sync
```

### Interactive mode

```python
class RalphCLI:
    """
    CLI with real-time streaming output and interrupt handling.
    """
    
    async def run_interactive(self, request: str):
        console = Console()
        
        with Live(self.create_status_panel(), refresh_per_second=4) as live:
            async for event in self.ralph.run(request):
                if event.type == "iteration_start":
                    live.update(self.create_iteration_panel(event))
                elif event.type == "tool_use":
                    console.print(f"[dim]→ {event.tool_name}[/dim]")
                elif event.type == "task_complete":
                    console.print(f"[green]✓ {event.task_description}[/green]")
                elif event.type == "text_output":
                    console.print(event.text)
                elif event.type == "needs_input":
                    response = Prompt.ask(event.question)
                    await self.ralph.provide_input(response)
    
    def handle_interrupt(self, signum, frame):
        """Graceful Ctrl+C handling"""
        console.print("\n[yellow]Interrupt received. Completing current operation...[/yellow]")
        self.ralph.request_pause()
```

### User injection mechanism

Allow users to steer without entering the loop:

```python
async def inject_user_guidance(guidance: str, state: RalphState):
    """
    Inject guidance that will be included in next iteration's context.
    Does not interrupt current iteration.
    """
    injection = {
        "timestamp": datetime.now().isoformat(),
        "guidance": guidance,
        "injected_by": "user"
    }
    
    # Append to injection queue (read at iteration start)
    with open(state.project_root / ".ralph" / "injections.json", "a") as f:
        f.write(json.dumps(injection) + "\n")
    
    console.print(f"[blue]Guidance queued for next iteration[/blue]")
```

---

## 8. Error handling and recovery

### Circuit breaker implementation

```python
@dataclass
class CircuitBreaker:
    """
    Deterministic failure detection and recovery.
    """
    
    max_consecutive_failures: int = 3
    max_stagnation_iterations: int = 5
    max_cost_usd: float = 100.0
    
    state: str = "closed"  # closed | open | half_open
    failure_count: int = 0
    stagnation_count: int = 0
    total_cost: float = 0.0
    
    def record_iteration(self, result: IterationResult):
        if result.is_failure:
            self.failure_count += 1
        else:
            self.failure_count = 0
        
        if result.tasks_completed == 0:
            self.stagnation_count += 1
        else:
            self.stagnation_count = 0
        
        self.total_cost += result.cost_usd
    
    def should_halt(self) -> Tuple[bool, Optional[str]]:
        if self.failure_count >= self.max_consecutive_failures:
            return True, f"consecutive_failures:{self.failure_count}"
        if self.stagnation_count >= self.max_stagnation_iterations:
            return True, f"stagnation:{self.stagnation_count}"
        if self.total_cost >= self.max_cost_usd:
            return True, f"cost_limit:${self.total_cost:.2f}"
        return False, None
    
    def attempt_recovery(self) -> RecoveryAction:
        """
        Determine recovery action based on failure pattern.
        """
        if self.stagnation_count > 0:
            return RecoveryAction.REGENERATE_PLAN
        if self.failure_count > 0:
            return RecoveryAction.SKIP_CURRENT_TASK
        return RecoveryAction.NONE
```

### Recovery actions

```python
class RecoveryManager:
    """
    Automated recovery strategies.
    """
    
    async def handle_stagnation(self, state: RalphState):
        """When no progress is made for multiple iterations"""
        
        # Option 1: Regenerate plan (most common fix)
        if state.plan.completion_percentage < 0.5:
            await self.regenerate_plan(state)
            return
        
        # Option 2: Skip problematic task
        current_task = state.plan.get_current_task()
        if current_task and current_task.retry_count > 2:
            self.mark_task_blocked(current_task, "Stagnation after 2 retries")
            return
        
        # Option 3: Request human intervention
        self.request_human_review(state, "Stagnation detected - please review")
    
    async def handle_test_failures(self, state: RalphState, failures: List[TestFailure]):
        """When tests fail after implementation"""
        
        # Add failure context to next iteration
        state.context_injections.append({
            "type": "test_failures",
            "failures": [f.to_dict() for f in failures],
            "instruction": "Fix these test failures before proceeding"
        })
```

---

## 9. Safety and constraints

### Git operation restrictions

Ralph performs **read-only git operations** only. All state-changing git operations are blocked:

```python
BLOCKED_GIT_COMMANDS = [
    "git commit",
    "git push", 
    "git pull",
    "git merge",
    "git rebase",
    "git checkout",
    "git reset",
    "git stash",
    "git cherry-pick",
    "git revert",
]

ALLOWED_GIT_COMMANDS = [
    "git status",
    "git log",
    "git diff",
    "git show",
    "git ls-files",
    "git blame",
]

# .gitignore manipulation is allowed
ALLOWED_FILE_OPERATIONS = [
    ".gitignore",
    ".ralph/*",
]
```

### Build system enforcement

Ralph enforces `uv` usage and blocks alternative package managers:

```python
BLOCKED_PACKAGE_COMMANDS = [
    # pip commands
    "pip install", "pip uninstall", "pip freeze", "python -m pip",
    "pip3 install", "pip3 uninstall",
    
    # venv/virtualenv commands
    "python -m venv", "python3 -m venv", "virtualenv",
    
    # Other package managers
    "conda install", "conda create", "conda activate",
    "poetry install", "poetry add", "poetry remove",
    "pipenv install", "pipenv shell",
]

REQUIRED_UV_COMMANDS = {
    "install_package": "uv add {package}",
    "install_dev_package": "uv add --dev {package}",
    "remove_package": "uv remove {package}",
    "sync_deps": "uv sync",
    "run_python": "uv run python",
    "run_pytest": "uv run pytest",
    "run_script": "uv run {script}",
}
```

### Sandboxing recommendations

For production use, Ralph should run in a sandboxed environment:

```python
sandbox_settings = {
    "enabled": True,
    "autoAllowBashIfSandboxed": True,
    "excludedCommands": ["docker", "kubectl", "ssh"],
    "network": {
        "allowLocalBinding": True,
        "allowUnixSockets": False
    }
}

# Environment restrictions
RESTRICTED_ENV_VARS = [
    "AWS_SECRET_ACCESS_KEY",
    "DATABASE_PASSWORD",
    "API_SECRET_KEY",
]
```

### Cost controls

```python
class CostController:
    """
    Financial guardrails for autonomous operation.
    """
    
    def __init__(self, config: CostConfig):
        self.max_per_iteration = config.max_per_iteration_usd  # e.g., $2
        self.max_per_session = config.max_per_session_usd      # e.g., $50
        self.max_total = config.max_total_usd                  # e.g., $200
        
    def check_budget(self, state: RalphState) -> BudgetStatus:
        if state.iteration_cost > self.max_per_iteration:
            return BudgetStatus.ITERATION_EXCEEDED
        if state.session_cost > self.max_per_session:
            return BudgetStatus.SESSION_EXCEEDED
        if state.total_cost > self.max_total:
            return BudgetStatus.TOTAL_EXCEEDED
        return BudgetStatus.OK
```

---

## 10. Testing strategy

### Unit tests for orchestration

```python
class TestTaskSelection:
    def test_selects_highest_priority(self):
        plan = ImplementationPlan(tasks=[
            Task(id="a", priority=2, status="pending", dependencies=[]),
            Task(id="b", priority=1, status="pending", dependencies=[]),
            Task(id="c", priority=3, status="pending", dependencies=[]),
        ])
        assert plan.get_next_task().id == "b"
    
    def test_respects_dependencies(self):
        plan = ImplementationPlan(tasks=[
            Task(id="a", priority=1, status="pending", dependencies=["b"]),
            Task(id="b", priority=2, status="pending", dependencies=[]),
        ])
        assert plan.get_next_task().id == "b"
    
    def test_skips_completed(self):
        plan = ImplementationPlan(tasks=[
            Task(id="a", priority=1, status="complete", dependencies=[]),
            Task(id="b", priority=2, status="pending", dependencies=[]),
        ])
        assert plan.get_next_task().id == "b"
```

### Integration tests with mock LLM

```python
class TestRalphIteration:
    async def test_iteration_completes_task(self, mock_client):
        mock_client.set_responses([
            ToolUse(name="ralph_mark_task_complete", input={"task_id": "task-001"}),
        ])
        
        state = create_test_state()
        result = await execute_iteration(state.plan.tasks[0], state)
        
        assert result.task_complete
        assert state.plan.tasks[0].status == "complete"
    
    async def test_context_handoff_triggered(self, mock_client):
        state = create_test_state()
        state.token_tracker.current_usage = 120_000  # Above 60% threshold
        
        result = await execute_iteration(state.plan.tasks[0], state)
        
        assert result.needs_handoff
        assert Path("MEMORY.md").exists()
```

### End-to-end simulation

```python
class TestFullWorkflow:
    async def test_simple_feature_workflow(self, temp_project):
        """
        Full lifecycle test with a simple feature request.
        Uses real Claude API but constrained budget.
        """
        # Initialize with uv
        subprocess.run(["uv", "init", "--python", "3.14"], cwd=temp_project)
        
        ralph = Ralph(
            project_root=temp_project,
            cost_limit=5.0,
            max_iterations=10
        )
        
        result = await ralph.run("Add a /health endpoint that returns JSON {status: 'ok'}")
        
        assert result.status == "complete"
        assert (temp_project / "routes/health.py").exists()
        
        # Verify using uv
        test_result = subprocess.run(
            ["uv", "run", "pytest", "-v"],
            cwd=temp_project,
            capture_output=True
        )
        assert test_result.returncode == 0
```

---

## 11. Configuration

### Environment variables

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Optional - defaults shown
RALPH_MAX_ITERATIONS=100
RALPH_MAX_COST_USD=200
RALPH_CONTEXT_BUDGET_PERCENT=60
RALPH_CIRCUIT_BREAKER_FAILURES=3
RALPH_CIRCUIT_BREAKER_STAGNATION=5

# Model selection
RALPH_PRIMARY_MODEL=claude-sonnet-4-20250514
RALPH_PLANNING_MODEL=claude-opus-4-20250514  # Use stronger model for planning

# Build system (uv is required, these configure its behavior)
UV_SYSTEM_PYTHON=0           # Don't use system Python
UV_PYTHON_PREFERENCE=managed  # Prefer uv-managed Python
```

### Project configuration

`.ralph/config.yaml`:

```yaml
project:
  name: "my-awesome-app"
  root: "."
  python_version: "3.14"
  
build:
  tool: "uv"  # Required, no alternatives
  test_command: "uv run pytest"
  lint_command: "uv run ruff check ."
  typecheck_command: "uv run mypy ."
  
phases:
  discovery:
    human_in_loop: true
    max_questions: 10
  planning:
    task_size_tokens: 30000  # Target tokens per task
    dependency_analysis: true
  building:
    max_iterations: 100
    backpressure:
      - "uv run pytest"
      - "uv run mypy ."
      - "uv run ruff check ."
  validation:
    require_human_approval: true

context:
  budget_percent: 60
  handoff_threshold_percent: 75

safety:
  sandbox_enabled: true
  blocked_commands:
    - "rm -rf"
    - "docker rm"
    - "pip install"      # Enforce uv usage
    - "python -m venv"   # Enforce uv usage
  cost_limits:
    per_iteration: 2.0
    per_session: 50.0
    total: 200.0

git:
  read_only: true
  allowed_operations:
    - "status"
    - "log"
    - "diff"
```

---

## 12. Implementation phases

### Phase 1: Core loop (Week 1-2)

- [ ] Basic `ClaudeSDKClient` integration
- [ ] JSON state persistence
- [ ] Single-phase building loop
- [ ] Task selection logic
- [ ] Circuit breaker
- [ ] CLI scaffolding
- [ ] **uv integration for all build commands**

### Phase 2: Context management (Week 3)

- [ ] Token tracking
- [ ] Hand-off protocol
- [ ] MEMORY.md generation
- [ ] Session archival

### Phase 3: Full lifecycle (Week 4-5)

- [ ] Discovery phase with user interaction
- [ ] Planning phase with subagents
- [ ] Validation phase
- [ ] Phase transitions

### Phase 4: Safety and polish (Week 6)

- [ ] Git operation blocking
- [ ] **Package manager enforcement (block pip/venv, require uv)**
- [ ] Cost controls
- [ ] Comprehensive CLI
- [ ] Documentation
- [ ] Test coverage >80%

---

## 13. Success metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Task completion rate | >90% | Tasks completed / tasks attempted |
| Context efficiency | 40-60% utilization | Tokens used / capacity per iteration |
| False exit rate | <5% | Premature exits / total exits |
| Stagnation recovery | >80% | Stagnations recovered / stagnations total |
| Cost predictability | <20% variance | Actual cost / estimated cost |
| User intervention rate | <10% | Iterations requiring human input |
| Build reproducibility | 100% | Successful builds from uv.lock |

**Don't Stop until all the features are implemented.**
---

## Appendix A: Prompt templates

### PROMPT_build.md template

```markdown
# Ralph Building Mode - Iteration {{iteration}}

## Context Recovery
1. Read MEMORY.md for previous session context
2. Read progress.txt for operational learnings
3. Read AGENTS.md for project-specific patterns

## Your Single Task
{{task.description}}

## Verification Criteria
{{#each task.verification_criteria}}
- [ ] {{this}}
{{/each}}

## Build System (CRITICAL)
This project uses `uv` exclusively. NEVER use pip, venv, or other tools.

```bash
# Running commands
uv run pytest              # Run tests
uv run mypy .              # Type checking
uv run ruff check .        # Linting
uv run python script.py    # Run any Python

# Managing dependencies
uv add <package>           # Add dependency
uv add --dev <package>     # Add dev dependency
uv remove <package>        # Remove dependency
uv sync                    # Install from lock file
```

## Process
1. **INVESTIGATE** - Use parallel subagents to study relevant code
   - "don't assume not implemented" - always search first
   - Use Glob and Grep before writing
   
2. **IMPLEMENT** - Make changes using Write/Edit tools
   - Small, focused changes
   - Follow patterns in AGENTS.md
   
3. **VALIDATE** - Run via single subagent:
   ```bash
   uv run pytest && uv run mypy . && uv run ruff check .
   ```
   
4. **VERIFY** - Confirm all verification criteria pass

5. **DOCUMENT** - If you learned something reusable:
   - Use ralph_append_learning tool
   - Update AGENTS.md if pattern is project-wide

## Completion
When task is complete:
1. Use ralph_mark_task_complete with verification notes
2. Update MEMORY.md with session state

If task cannot complete this iteration:
1. Document progress in MEMORY.md
2. Note blockers clearly
```

### AGENTS.md template

```markdown
# Project Operations Guide

## Build System
This project uses `uv` for all Python operations.

```bash
# Setup
uv sync                    # Install all dependencies

# Development
uv run pytest              # Run tests (~30 seconds)
uv run mypy .              # Type checking
uv run ruff check .        # Linting
uv run ruff format .       # Auto-format

# Adding dependencies
uv add <package>           # Runtime dependency
uv add --dev <package>     # Dev dependency
```

## Architecture Patterns
- Routes in `routes/`, one file per resource
- Business logic in `services/`
- Database models in `models/`

## Testing Conventions
- Fixtures in `tests/conftest.py`
- Use `test_client` fixture for API tests
- Mock external services, never call real APIs

## Common Gotchas
- Always run migrations before testing new models
- Rate limiting middleware requires Redis (use REDIS_URL)
- Frontend expects API at /api/v1 prefix

## Learned Patterns
[Ralph will append discoveries here]
```

---

## Appendix B: Comparison with existing implementations

| Feature | snarktank/ralph | frankbria/ralph-claude-code | This Implementation |
|---------|-----------------|-----------------------------|--------------------|
| Control flow | Bash loop | Bash loop | **Python orchestration** |
| State format | JSON + Markdown | Custom files | **JSON + Markdown** |
| Task selection | LLM chooses | LLM chooses | **Python deterministic** |
| Context tracking | None | Basic | **Full token tracking** |
| Exit detection | String match | Dual-gate | **Dual-gate + validation** |
| Git operations | Full access | Full access | **Read-only** |
| Lifecycle phases | Build only | Build only | **Full: discovery→validate** |
| SDK used | Claude Code CLI | Claude Code CLI | **Claude Agent SDK** |
| Circuit breaker | Max iterations | Advanced | **Multi-signal** |
| Build system | System pip/venv | System pip/venv | **uv exclusively** |

This implementation addresses the core weaknesses identified in existing Ralph implementations: **lack of determinism** (Python control vs. LLM control), **forgetfulness** (structured state persistence), **context rot** (aggressive token budgeting with 60% threshold), and **build reproducibility** (uv lock files).

**Don't Stop until all the features are implemented.**