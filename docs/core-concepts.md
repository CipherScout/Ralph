# Core Concepts

This guide explains the fundamental concepts behind Ralph, a deterministic agentic coding loop built on the Claude Agent SDK. Understanding these concepts will help you work effectively with Ralph and debug issues when they arise.

---

## Table of Contents

1. [The Ralph Philosophy](#the-ralph-philosophy)
2. [The Four Phases](#the-four-phases)
3. [State Management](#state-management)
4. [Context Window Management](#context-window-management)
5. [Memory System](#memory-system)
6. [Task Lifecycle](#task-lifecycle)
7. [Safety Controls](#safety-controls)
8. [MCP Tools](#mcp-tools)

---

## The Ralph Philosophy

### "Sit on the Loop, Not in It"

Ralph's core design principle is that **Python controls the workflow, while the LLM executes tasks**. This is fundamentally different from approaches where the LLM decides what to do next.

```
Traditional Agent Approach:
+------------------+
|       LLM        |  <-- LLM decides everything:
|  (orchestrator)  |      - What task to do
|                  |      - When to stop
+--------+---------+      - How to recover from errors
         |
         v
    [Execute Task]

Ralph's Approach:
+------------------+
|      Python      |  <-- Python decides:
|  (orchestrator)  |      - Which task to execute
|                  |      - When to hand off context
+--------+---------+      - When to halt (circuit breaker)
         |
         v
+------------------+
|       LLM        |  <-- LLM executes:
|    (executor)    |      - Implements the assigned task
|                  |      - Reports completion via tools
+------------------+
```

This separation provides several benefits:

| Aspect | LLM-Controlled | Ralph (Python-Controlled) |
|--------|---------------|---------------------------|
| Task selection | ~70-80% reliable | 100% deterministic |
| Exit detection | String matching, unreliable | Dual-gate: tool call + Python validation |
| State persistence | In-context (lost on reset) | JSON files (survives resets) |
| Cost control | Difficult to enforce | Precise tracking per iteration |
| Recovery | Unpredictable | Deterministic retry logic |

### Why Deterministic Orchestration Matters

When an LLM controls its own workflow, several problems emerge:

1. **Task Selection Failures**: LLMs can get confused about which task to work on, especially in complex projects with many dependencies.

2. **Premature Exits**: The LLM might declare "I'm done!" when work remains incomplete.

3. **Context Rot**: As the context fills up, the LLM's ability to reason about its own state degrades.

4. **Unpredictable Costs**: Without external control, costs can spiral unexpectedly.

Ralph solves these by moving control decisions to Python code that runs *outside* the LLM's context window.

### Context Windows as Disposable Compute Resources

Ralph treats each context window as a **disposable compute resource** that gets garbage-collected after use. This is a mindset shift:

```
Traditional: Preserve context at all costs
             (leads to bloated, confused sessions)

Ralph:       Context is cheap. Fresh context is better.
             Persist state in files, not in memory.
```

This approach means:

- Each iteration starts with a fresh, focused context
- State persists through `.ralph/` JSON files and markdown documents
- Session summaries in `MEMORY.md` bridge context resets
- The LLM gets clear, uncluttered instructions each time

---

## The Four Phases

Ralph's development lifecycle consists of four distinct phases, each with specific goals, tools, and transition criteria.

```
+-------------+     +------------+     +------------+     +--------------+
|  DISCOVERY  | --> |  PLANNING  | --> |  BUILDING  | --> |  VALIDATION  |
+-------------+     +------------+     +------------+     +--------------+
     |                   |                  |                    |
     v                   v                  v                    v
  Specs in           Task list         Implemented          Verified
  specs/             in plan           code                 deliverable
```

### Phase 1: Discovery

**Purpose**: Transform user intent into structured specifications through interactive conversation.

**Framework**: Jobs-to-be-Done (JTBD)
- **When** [situation occurs]
- **I want to** [motivation/action]
- **So I can** [expected outcome]

**Available Tools**:
| Tool | Purpose |
|------|---------|
| Read, Glob, Grep | Analyze existing codebase |
| WebSearch, WebFetch | Research best practices |
| Write | Create spec files |
| Task | Delegate research subtasks |
| AskUserQuestion | Clarify requirements with user |

**Artifacts Produced**:
- Specification files in `specs/` directory
- Each spec contains:
  - Problem statement
  - Success criteria (measurable)
  - Constraints and non-goals
  - Acceptance criteria (testable)

**Transition Criteria**:
- All JTBD questions answered
- Requirements documented in spec files
- User confirms requirements are complete

**Example Output** (`specs/authentication.md`):
```markdown
# Authentication System Specification

## Problem Statement
Users need secure access to their accounts with support for
email/password and OAuth providers.

## Success Criteria
- Users can register with email/password
- Users can log in with Google OAuth
- Sessions persist for 7 days
- Password reset works via email

## Constraints
- Must use existing PostgreSQL database
- No third-party auth services (self-hosted)

## Acceptance Criteria
- [ ] Registration creates user in database
- [ ] Login returns JWT token
- [ ] Protected routes reject invalid tokens
- [ ] Password reset sends email within 30s
```

---

### Phase 2: Planning

**Purpose**: Analyze gaps between specs and existing code, then produce a prioritized implementation plan.

**Key Principle**: Tasks should be sized for single context windows (~30 minutes of focused work each).

**Available Tools**:
| Tool | Purpose |
|------|---------|
| Read, Glob, Grep | Analyze existing codebase |
| WebSearch, WebFetch | Research solutions |
| Write | Create implementation plan |
| Task | Parallel analysis via subagents |
| ExitPlanMode | Finalize planning |

**Artifacts Produced**:
- `.ralph/implementation_plan.json` containing:
  - Prioritized task list
  - Dependencies between tasks
  - Verification criteria per task
  - Token estimates

**Task Sizing Guidelines**:
```
GOOD Task Sizes:
- "Add database column and migration for user.email_verified"
- "Create UserProfile React component with props interface"
- "Write unit tests for authentication middleware"

TOO BIG (needs splitting):
- "Build entire authentication system"
- "Implement all API endpoints"
- "Create the frontend"
```

**Transition Criteria**:
- All tasks defined with priorities
- Dependencies mapped
- Verification criteria specified for each task

**Example Plan** (`.ralph/implementation_plan.json`):
```json
{
  "tasks": [
    {
      "id": "auth-01",
      "description": "Create User model with password hashing",
      "priority": 1,
      "dependencies": [],
      "verification_criteria": [
        "User model exists in models/user.py",
        "Password is hashed using bcrypt",
        "uv run pytest tests/test_user_model.py passes"
      ],
      "estimated_tokens": 25000
    },
    {
      "id": "auth-02",
      "description": "Add registration endpoint",
      "priority": 2,
      "dependencies": ["auth-01"],
      "verification_criteria": [
        "POST /api/register creates user",
        "Returns 400 for duplicate email",
        "uv run pytest tests/test_registration.py passes"
      ],
      "estimated_tokens": 30000
    }
  ]
}
```

---

### Phase 3: Building

**Purpose**: Iteratively implement tasks from the plan using Test-Driven Development (TDD).

**The TDD Iteration Loop**:
```
    +-------------------+
    |  Get Next Task    |  <-- Python selects (deterministic)
    |  (ralph tool)     |
    +---------+---------+
              |
              v
    +-------------------+
    |  Mark In Progress |
    |  (ralph tool)     |
    +---------+---------+
              |
              v
    +-------------------+
    |  Write Failing    |
    |  Tests First      |
    +---------+---------+
              |
              v
    +-------------------+
    |  Implement        |
    |  Feature          |
    +---------+---------+
              |
              v
    +-------------------+
    |  Run Backpressure |  <-- uv run pytest && mypy && ruff
    |  Commands         |
    +---------+---------+
              |
        +-----+-----+
        |           |
    [PASS]      [FAIL]
        |           |
        v           v
    +-------+   +--------+
    | Mark  |   | Fix &  |
    |Complete|   | Retry  |
    +-------+   +--------+
```

**Available Tools**:
| Tool | Purpose |
|------|---------|
| Read, Write, Edit | Core file operations |
| Bash, BashOutput, KillBash | Command execution |
| Glob, Grep | Code search |
| Task | Subagents for isolated work |
| TodoWrite | Track task progress |
| WebSearch, WebFetch | Look up documentation |
| NotebookEdit | Jupyter notebook support |

**Backpressure Commands** (must pass before task completion):
```bash
uv run pytest          # All tests pass
uv run mypy .          # Type checking passes
uv run ruff check .    # Linting passes
```

**Transition Criteria**:
- All tasks marked COMPLETE or BLOCKED
- No tasks in PENDING or IN_PROGRESS state

---

### Phase 4: Validation

**Purpose**: Comprehensive verification that implementation meets requirements.

**Verification Checklist**:
1. All tests pass
2. Linting passes
3. Type checking passes
4. Each task's verification criteria met
5. Original requirements from specs satisfied

**Available Tools**:
| Tool | Purpose |
|------|---------|
| Read, Glob, Grep | Review implementation |
| Bash | Run tests, linting (via uv run) |
| Task | Delegate verification |
| WebFetch | Visual verification (dev-browser) |

**Artifacts Produced**:
- Validation report documenting:
  - Test results
  - Lint results
  - Type check results
  - Requirement verification status

**Transition Criteria**:
- All automated checks pass
- Human approval checkpoint (optional)
- If issues found, may return to Building phase

---

## State Management

Ralph maintains state across iterations and context window resets through a combination of JSON files and markdown documents.

### RalphState

The master state object, persisted to `.ralph/state.json`:

```python
@dataclass
class RalphState:
    project_root: Path
    current_phase: Phase          # discovery | planning | building | validation
    iteration_count: int          # Total iterations across all sessions
    session_id: str | None        # Current session identifier

    # Cost tracking
    total_cost_usd: float         # Cumulative cost
    total_tokens_used: int        # Cumulative tokens

    # Timing
    started_at: datetime
    last_activity_at: datetime

    # Nested state
    circuit_breaker: CircuitBreakerState

    # Session tracking
    session_cost_usd: float       # Cost this session only
    session_tokens_used: int      # Tokens this session only
    tasks_completed_this_session: int

    # Control
    paused: bool                  # Loop paused by user
```

**Example** (`.ralph/state.json`):
```json
{
  "project_root": "/path/to/project",
  "current_phase": "building",
  "iteration_count": 47,
  "session_id": "a1b2c3d4",
  "total_cost_usd": 12.34,
  "total_tokens_used": 1234567,
  "started_at": "2026-01-20T10:00:00",
  "last_activity_at": "2026-01-26T14:30:00",
  "session_cost_usd": 2.50,
  "session_tokens_used": 250000,
  "tasks_completed_this_session": 3,
  "paused": false,
  "circuit_breaker": {
    "state": "closed",
    "failure_count": 0,
    "stagnation_count": 0
  }
}
```

### ImplementationPlan

The task list, persisted to `.ralph/implementation_plan.json`:

```python
@dataclass
class Task:
    id: str                       # Unique identifier
    description: str              # What to implement
    priority: int                 # 1 = highest
    status: TaskStatus            # pending | in_progress | complete | blocked
    dependencies: list[str]       # Task IDs this depends on
    verification_criteria: list[str]  # How to verify completion
    blockers: list[str]           # Why it's blocked (if applicable)
    estimated_tokens: int         # Token budget for this task
    actual_tokens_used: int | None
    completion_notes: str | None
    completed_at: datetime | None
    retry_count: int              # How many times we've retried
```

**Task Selection Algorithm** (deterministic):
```python
def get_next_task(self) -> Task | None:
    """Select highest priority task with met dependencies."""
    completed_ids = {t.id for t in self.tasks if t.status == COMPLETE}
    available = [
        t for t in self.tasks
        if t.status == PENDING
        and all(dep in completed_ids for dep in t.dependencies)
    ]
    return min(available, key=lambda t: t.priority) if available else None
```

### How State Persists Across Context Resets

```
Session N                           Session N+1
+------------------+                +------------------+
|  LLM Context     |                |  LLM Context     |
|  (will be lost)  |                |  (fresh start)   |
+--------+---------+                +--------+---------+
         |                                   ^
         | save                              | load
         v                                   |
+------------------+                +------------------+
|  .ralph/         |  (persists)   |  .ralph/         |
|  state.json      | ============> |  state.json      |
|  plan.json       |                |  plan.json       |
+------------------+                +------------------+
         |                                   ^
         | write                             | read
         v                                   |
+------------------+                +------------------+
|  MEMORY.md       |  (persists)   |  MEMORY.md       |
|  progress.txt    | ============> |  progress.txt    |
+------------------+                +------------------+
```

### The Role of MEMORY.md

`MEMORY.md` is generated during context handoffs to preserve session context:

```markdown
# Session Memory - Iteration 47

## Completed This Session
- [x] Added user.email_verified column migration
- [x] Updated User model with new field
- [x] Added email verification endpoint

## Current Task In Progress
Task ID: task-023
Description: Implement email verification flow
Progress: Email sending works, need to add token verification

## Architectural Decisions
- Using JWT for verification tokens (24h expiry)
- Storing verification state in users table

## Files Modified
1. db/migrations/004_add_email_verified.py
2. models/user.py
3. routes/auth.py
4. services/email.py
5. tests/test_email_verification.py

## Blockers/Issues
- SMTP config needs environment variables

## Notes for Next Session
- Token verification endpoint needs rate limiting
- Consider adding verification email resend endpoint

## Session Metadata
- Phase: building
- Iteration: 47
- Session Cost: $2.5000
- Session Tokens: 250,000
- Total Progress: 65%
```

### The Role of progress.txt

`progress.txt` is an append-only log of operational learnings:

```
[2026-01-25 14:32:01] PATTERN: Use Pydantic models for all API responses
[2026-01-25 15:45:22] ANTIPATTERN: Don't assume endpoint doesn't exist - grep first
[2026-01-25 16:20:15] ARCHITECTURE: Rate limiting middleware goes in middleware/
[2026-01-25 17:05:33] DEBUGGING: Test failures often mean missing fixture
[2026-01-25 17:30:00] BUILD: Always use `uv run pytest` not `pytest` directly
```

---

## Context Window Management

### The "Smart Zone" (40-60% Utilization)

Research shows that token usage explains ~80% of performance variance in agent tasks. Ralph targets the "smart zone" of 40-60% context utilization.

```
Context Window Utilization:

0%        40%       60%       80%       100%
|---------|---------|---------|---------|
|         |/////////|         |         |
|  Under- |  SMART  |  Danger |  Over-  |
|  used   |  ZONE   |  Zone   |  loaded |
|         |/////////|         |         |

    ^           ^           ^
    |           |           |
    |           |           +-- Handoff triggered
    |           +-- Optimal performance
    +-- Context is being wasted
```

**Why 40-60%?**

- **Below 40%**: Not enough context for complex reasoning
- **40-60%**: Optimal balance of context and focus
- **Above 60%**: Performance degrades as context fills
- **Above 80%**: High risk of losing track of goals

### Automatic Handoff Protocol

When approaching context limits, Ralph executes a structured handoff:

```
+------------------------+
| Check Context Budget   |
| (after each iteration) |
+-----------+------------+
            |
      +-----+-----+
      |           |
   <60%        >=60%
      |           |
      v           v
  Continue    +-------------------+
              | Request Session   |
              | Summary from LLM  |
              +---------+---------+
                        |
                        v
              +-------------------+
              | Write MEMORY.md   |
              +---------+---------+
                        |
                        v
              +-------------------+
              | Archive Session   |
              | to history/       |
              +---------+---------+
                        |
                        v
              +-------------------+
              | Start Fresh       |
              | Session           |
              +-------------------+
```

### How MEMORY.md Preserves Context

Each new session starts by reading `MEMORY.md`:

```python
prompt = f"""
BUILDING MODE - Iteration {iteration}

Read MEMORY.md for context from previous sessions.
Read progress.txt for operational learnings.

YOUR SINGLE TASK: {task.description}

VERIFICATION CRITERIA:
{task.verification_criteria}
"""
```

This gives the fresh context window enough information to continue work effectively.

### Session Archival

Completed sessions are archived to `.ralph/session_history/sessions.jsonl`:

```json
{"session_id": "a1b2c3d4", "iteration": 47, "tokens_used": 250000, "cost_usd": 2.50, "tasks_completed": 3, "phase": "building", "handoff_reason": "phase_complete"}
{"session_id": "e5f6g7h8", "iteration": 52, "tokens_used": 180000, "cost_usd": 1.80, "tasks_completed": 2, "phase": "building", "handoff_reason": "manual_handoff"}
```

This provides a full audit trail of all sessions.

---

## Memory System

Ralph includes a **deterministic memory system** that automatically captures context at well-defined boundaries. Unlike approaches that rely on the LLM to decide when and what to remember, Ralph's memory capture is **harness-controlled** (Python code), ensuring consistent and predictable memory management.

### Why Deterministic Memory?

| Approach | Reliability | Consistency |
|----------|-------------|-------------|
| LLM-controlled memory | ~70-80% | Variable |
| Ralph's deterministic memory | 100% | Always captured |

When memory capture is left to the LLM:
- Important context may be forgotten
- Memory updates are inconsistent
- Format varies between sessions
- No guarantee of capture at critical moments

Ralph solves this by capturing memory at three deterministic boundaries.

### Memory Capture Boundaries

```
+-------------------+
|    Iteration N    |
|     (work done)   |
+---------+---------+
          |
          | Automatic capture
          v
+-------------------+
| Iteration Memory  | --> .ralph/memory/iterations/iter-NNN.md
+-------------------+

+-------------------+     +-------------------+
|   Phase A         | --> |   Phase B         |
|   (discovery)     |     |   (planning)      |
+---------+---------+     +-------------------+
          |
          | Automatic capture
          v
+-------------------+
|   Phase Memory    | --> .ralph/memory/phases/discovery.md
+-------------------+

+-------------------+     +-------------------+
|   Session N       | --> |   Session N+1     |
|   (context full)  |     |   (fresh start)   |
+---------+---------+     +-------------------+
          |
          | Automatic capture
          v
+-------------------+
| Session Memory    | --> .ralph/memory/sessions/session-NNN.md
+-------------------+
```

### Memory Directory Structure

```
.ralph/
├── MEMORY.md                 # Active memory (injected into prompts)
└── memory/
    ├── phases/               # Phase transition memories
    │   ├── discovery.md      # What was learned during discovery
    │   ├── planning.md       # Planning decisions and rationale
    │   └── building.md       # Build progress and patterns
    ├── iterations/           # Per-iteration snapshots
    │   ├── iter-001.md
    │   ├── iter-002.md
    │   └── ...
    ├── sessions/             # Session handoff summaries
    │   └── session-001.md
    └── archive/              # Rotated old files
```

### What Gets Captured

**Iteration Memory** (at end of each iteration):
- Phase and iteration number
- Tasks completed/blocked this iteration
- Progress made (yes/no)
- Token usage and cost
- Timestamp

**Phase Memory** (at phase transitions):
- Phase being completed
- Key artifacts produced (specs, tasks, code)
- Decisions made during the phase
- Metrics (iterations, cost, tokens)

**Session Memory** (at context handoffs):
- Session ID and duration
- Tasks in progress when handoff occurred
- Reason for handoff
- Cumulative session metrics
- Notes for next session

### Active Memory Construction

When a new iteration starts, Ralph builds **active memory** from multiple sources:

```python
def build_active_memory(state, plan) -> str:
    sections = []

    # 1. Previous phase context (if recently transitioned)
    if recent_phase_transition:
        sections.append(load_phase_memory(previous_phase))

    # 2. Recent iterations (last 3)
    recent = load_recent_iterations(limit=3)
    sections.append(format_iteration_summaries(recent))

    # 3. Current task state
    sections.append(format_task_state(plan))

    # 4. Session metrics
    sections.append(format_session_metrics(state))

    # Truncate to 8000 chars max
    return truncate_and_combine(sections)
```

This ensures each iteration has relevant context without bloating the context window.

### Memory Rotation and Cleanup

To prevent unbounded storage growth:

| File Type | Max Files | Rotation Action |
|-----------|-----------|-----------------|
| Iteration memories | 20 | Move oldest to archive |
| Session memories | 10 | Move oldest to archive |
| Archive files | 30 days | Delete |

Use `ralph-agent memory --cleanup` to manually trigger rotation.

### Viewing Memory

```bash
# View active memory (what gets injected into prompts)
ralph-agent memory --show

# View memory statistics
ralph-agent memory --stats

# Run cleanup manually
ralph-agent memory --cleanup
```

### Backwards Compatibility

The `ralph_update_memory` MCP tool remains available for the LLM to explicitly request memory updates. These are additive to the deterministic captures—the harness-controlled system ensures baseline capture even if the LLM never calls the tool.

---

## Task Lifecycle

### Task States

```
                    +-------------------+
                    |      PENDING      |
                    |  (waiting to be   |
                    |   picked up)      |
                    +---------+---------+
                              |
                              | ralph_mark_task_in_progress
                              v
                    +-------------------+
                    |   IN_PROGRESS     |
                    |  (being worked    |
                    |   on)             |
                    +---------+---------+
                              |
            +-----------------+-----------------+
            |                                   |
            | ralph_mark_task_complete          | ralph_mark_task_blocked
            v                                   v
+-------------------+                 +-------------------+
|     COMPLETE      |                 |     BLOCKED       |
|  (successfully    |                 |  (cannot be       |
|   finished)       |                 |   completed)      |
+-------------------+                 +-------------------+
```

### Dependency Resolution

Tasks can only start when all dependencies are COMPLETE:

```
Task A (no deps)     -----> COMPLETE
                              |
                              | (dependency met)
                              v
Task B (depends: A)  -----> Can now start
                              |
Task C (depends: A)  -----> Can now start (parallel OK)
                              |
                              | (both must complete)
                              v
Task D (depends: B,C) ----> Waiting...
```

**Example**:
```json
{
  "tasks": [
    {"id": "db-01", "dependencies": [], "status": "complete"},
    {"id": "api-01", "dependencies": ["db-01"], "status": "complete"},
    {"id": "api-02", "dependencies": ["db-01"], "status": "in_progress"},
    {"id": "frontend-01", "dependencies": ["api-01", "api-02"], "status": "pending"}
  ]
}
```

In this case:
- `db-01`: Complete (had no dependencies)
- `api-01`: Complete (db-01 was complete)
- `api-02`: In progress (db-01 was complete)
- `frontend-01`: **Waiting** (api-02 not yet complete)

### Verification Criteria

Each task has verification criteria that must pass:

```json
{
  "id": "auth-03",
  "verification_criteria": [
    "POST /api/login returns JWT token",
    "Invalid credentials return 401",
    "Token contains user_id claim",
    "uv run pytest tests/test_login.py passes"
  ]
}
```

The LLM must verify these before calling `ralph_mark_task_complete`.

### Retry Handling

When a task fails, Ralph handles retries:

```
Attempt 1: Failed
    |
    v
retry_count = 1, status -> PENDING
    |
    v
Attempt 2: Failed
    |
    v
retry_count = 2, status -> PENDING
    |
    v
Attempt 3: Failed
    |
    v
retry_count >= 3, status -> BLOCKED
(requires manual intervention)
```

**Stale In-Progress Recovery**:

If Ralph crashes during task execution, tasks may be left in IN_PROGRESS state. At session start, Ralph resets these to PENDING:

```python
def start_session(self):
    # Reset stale IN_PROGRESS tasks
    plan = load_plan(self.project_root)
    stale_count = plan.reset_stale_in_progress_tasks()
    if stale_count > 0:
        save_plan(plan, self.project_root)
```

---

## Safety Controls

### Circuit Breaker

The circuit breaker halts execution when problems are detected:

```
+------------------+
|     CLOSED       |  <-- Normal operation
| (running)        |
+--------+---------+
         |
         | Failures >= 3 OR
         | Stagnation >= 5 OR
         | Cost >= limit
         v
+------------------+
|      OPEN        |  <-- Halted
| (needs recovery) |
+--------+---------+
         |
         | Manual reset OR
         | Successful recovery
         v
+------------------+
|    HALF_OPEN     |  <-- Testing recovery
| (one attempt)    |
+--------+---------+
         |
    +----+----+
    |         |
 Success   Failure
    |         |
    v         v
 CLOSED     OPEN
```

**Trigger Conditions**:

| Condition | Threshold | Reason |
|-----------|-----------|--------|
| Consecutive failures | 3 | Something is fundamentally broken |
| Stagnation | 5 iterations | No progress being made |
| Cost limit | Configurable | Financial protection |

**Recovery Actions**:
- `RETRY`: Try again (for transient failures)
- `SKIP_TASK`: Mark current task blocked, move on
- `HANDOFF`: Fresh context might help
- `MANUAL_INTERVENTION`: Human needs to help

### Command Blocking

Ralph blocks dangerous commands to prevent accidents:

**Blocked Git Operations** (Ralph uses read-only git):
```
git commit     git push       git pull
git merge      git rebase     git checkout
git reset      git stash      git cherry-pick
git revert     git branch -D  git branch -d
```

**Allowed Git Operations** (read-only):
```
git status     git log        git diff
git show       git ls-files   git blame
git branch     (listing only)
```

**Blocked Package Managers** (uv enforcement):
```
pip install         pip uninstall      pip freeze
python -m pip       conda install      conda create
poetry install      poetry add         pipenv install
virtualenv          python -m venv
```

**Required Alternatives**:
| Blocked Command | Use Instead |
|-----------------|-------------|
| `pip install X` | `uv add X` |
| `pip uninstall X` | `uv remove X` |
| `pip freeze` | `uv lock` |
| `python -m venv` | (uv manages automatically) |
| `pytest` | `uv run pytest` |

### Cost Tracking and Limits

Ralph tracks costs at multiple levels:

```python
# Configuration (ralph.yml)
cost_limits:
  per_iteration: 2.0    # Max $2 per iteration
  per_session: 50.0     # Max $50 per session
  total: 200.0          # Max $200 total
```

**Cost Tracking**:
```
                     Total Cost
                    ($12.34 so far)
                          |
        +-----------------+-----------------+
        |                                   |
   Session Cost                        Previous
   ($2.50 this session)                Sessions
        |                              ($9.84)
        +--+--+--+--+
        |  |  |  |  |
       It It It It It
       1  2  3  4  5
      $0.50 each (example)
```

If any limit is exceeded, the circuit breaker opens.

---

## MCP Tools

### What Are MCP Tools?

MCP (Model Context Protocol) tools are structured interfaces that allow the LLM to interact with Ralph's state. Instead of parsing text output, the LLM calls specific tools that Python code handles.

**Why MCP?**
- **Structured**: Clear input/output schemas
- **Reliable**: No parsing ambiguity
- **Traceable**: Every action is logged
- **Controllable**: Python validates before executing

### Ralph's MCP Tools

| Tool | Description | When to Use |
|------|-------------|-------------|
| `ralph_get_next_task` | Get highest-priority incomplete task | Start of each work cycle |
| `ralph_mark_task_in_progress` | Mark task as being worked on | Before starting implementation |
| `ralph_mark_task_complete` | Mark task as done with notes | After verification passes |
| `ralph_mark_task_blocked` | Mark task as blocked with reason | When task cannot be completed |
| `ralph_append_learning` | Record operational learning | When discovering useful patterns |
| `ralph_get_plan_summary` | Get plan overview | To understand progress |
| `ralph_get_state_summary` | Get current state | To check context/cost status |
| `ralph_add_task` | Add new task to plan | During planning phase |
| `ralph_increment_retry` | Increment retry count | After failed attempt |

### Tool Workflow Example

```
LLM: "Let me start the next task"
     |
     v
+----------------------------------+
| ralph_get_next_task()            |
+----------------------------------+
     |
     v
Response: {
  "task": {
    "id": "auth-03",
    "description": "Add login endpoint",
    "verification_criteria": [...]
  }
}
     |
     v
+----------------------------------+
| ralph_mark_task_in_progress(     |
|   task_id="auth-03"              |
| )                                |
+----------------------------------+
     |
     v
[LLM implements the feature...]
     |
     v
[LLM runs: uv run pytest - PASSES]
     |
     v
+----------------------------------+
| ralph_mark_task_complete(        |
|   task_id="auth-03",             |
|   verification_notes="All tests  |
|     pass, endpoint returns JWT"  |
| )                                |
+----------------------------------+
     |
     v
Response: {
  "task_id": "auth-03",
  "completion_percentage": 0.75,
  "remaining_tasks": 5
}
```

### How MCP Enables Deterministic Control

The key insight is that Ralph tools **modify state files**, not LLM context:

```
+------------------+
|       LLM        |
|                  |
| "I'll mark this  |
|  task complete"  |
+--------+---------+
         |
         | MCP tool call
         v
+------------------+
|  ralph_mark_     |
|  task_complete   |
+--------+---------+
         |
         | Modifies
         v
+------------------+
| .ralph/          |
| implementation_  |
| plan.json        |
+------------------+
         |
         | Persists across
         v
+------------------+
|  Next Session    |
|  (fresh context) |
+------------------+
```

This means:
- State changes persist even if context is lost
- Python can validate tool inputs before execution
- Actions are auditable and reversible
- The LLM cannot accidentally corrupt state through text manipulation

---

## Summary

Ralph's core concepts work together to provide reliable, deterministic agentic workflows:

1. **Python Controls, LLM Executes**: Clear separation of concerns
2. **Four Phases**: Structured progression from requirements to validation
3. **Persistent State**: Survives context resets via JSON/markdown files
4. **Smart Context Management**: Stay in the 40-60% zone, handoff before degradation
5. **Clear Task Lifecycle**: Deterministic selection and dependency resolution
6. **Safety First**: Circuit breaker, command blocking, cost limits
7. **MCP Tools**: Structured state management, no text parsing

Together, these concepts make Ralph a predictable, cost-effective, and recoverable coding agent.
