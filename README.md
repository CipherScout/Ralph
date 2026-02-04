# Ralph

Deterministic agentic coding loop using Claude Agent SDK.

Ralph is an autonomous coding agent that breaks down development work into discrete, trackable tasks and executes them iteratively. It maintains state across context window resets, enabling long-running development sessions with cost controls and circuit breakers.

## Documentation

📚 **[Full Documentation](docs/README.md)** - Comprehensive guides and references

| Guide | Description |
|-------|-------------|
| [Getting Started](docs/getting-started.md) | Installation, setup, and first workflow |
| [Core Concepts](docs/core-concepts.md) | Philosophy, phases, and state management |
| [CLI Reference](docs/cli-reference.md) | Complete command reference |
| [Configuration](docs/configuration.md) | All configuration options |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and solutions |
| [Architecture](docs/architecture.md) | Internal design for contributors |

## Features

- **Four-phase workflow**: Discovery → Planning → Building → Validation
- **Deterministic task execution**: Python controls task selection, not LLM
- **Context management**: Automatic handoffs at 60% context usage
- **Safety controls**: Circuit breakers, cost limits, read-only git
- **MCP integration**: Custom tools for task and state management
- **uv enforcement**: All Python commands routed through uv

## Installation

### Option 1: Run Directly (No Clone Required)

Run Ralph directly from GitHub using `uvx` (requires [uv](https://docs.astral.sh/uv/)):

```bash
# Run directly from GitHub (no installation needed)
uvx --from git+https://github.com/CipherScout/Ralph ralph-agent --help

# Run with a specific version/tag
uvx --from git+https://github.com/CipherScout/Ralph@v0.1.0 ralph-agent --help

# Install globally for repeated use
uv tool install git+https://github.com/CipherScout/Ralph
ralph-agent --help
```

### Option 2: Clone and Install (Development)

```bash
# Clone the repository
git clone https://github.com/CipherScout/Ralph.git
cd Ralph

# Install dependencies (including dev tools)
uv sync --extra dev

# Run via uv
uv run ralph-agent --help
```

## Quick Start

```bash
# Initialize Ralph in your project
ralph-agent init                    # If installed globally with uv tool install
# OR
uv run ralph-agent init             # If cloned locally

# Check status
ralph-agent status

# Run the full workflow with a goal
ralph-agent run --goal "Add user authentication"
```

> **Note**: Examples below use `ralph-agent` directly. If you cloned the repo instead of installing globally, prefix commands with `uv run` (e.g., `uv run ralph-agent status`).

## CLI Commands

### Core Commands

```bash
# Initialize Ralph in a project directory
uv run ralph-agent init [--project-root PATH] [--force]

# Show current state
uv run ralph-agent status [--verbose]

# List tasks in the implementation plan
uv run ralph-agent tasks [--pending] [--all]

# Reset state to initial values
uv run ralph-agent reset [--keep-plan]

# Clean up state files for a fresh start
uv run ralph-agent clean [--memory] [--force] [--dry-run]
```

### Phase Commands

```bash
# Run Discovery phase (JTBD requirements gathering)
uv run ralph-agent discover [--goal "description"]

# Run Planning phase (gap analysis, task creation)
uv run ralph-agent plan

# Run Building phase (iterative task implementation)
uv run ralph-agent build [--task TASK_ID]

# Run Validation phase (tests, lint, type check)
uv run ralph-agent validate

# Run full workflow (all phases)
uv run ralph-agent run [--phase PHASE] [--max-iterations N]
```

### Control Commands

```bash
# Pause the loop after current iteration
uv run ralph-agent pause

# Resume a paused loop
uv run ralph-agent resume

# Skip a task by marking it blocked
uv run ralph-agent skip TASK_ID [--reason "why"]

# Inject a message into next iteration's context
uv run ralph-agent inject "message" [--priority N]

# Manually trigger context handoff
uv run ralph-agent handoff [--reason "why"]

# Regenerate plan from specs
uv run ralph-agent regenerate-plan [--discard-completed]

# View and manage memory system
uv run ralph-agent memory [--show] [--stats] [--cleanup]
```

### Development Commands

```bash
# Run tests
uv run ralph-agent test [-- pytest args]

# Run linting
uv run ralph-agent lint [--fix]

# Run type checking
uv run ralph-agent typecheck

# Manage dependencies
uv run ralph-agent deps add PACKAGE [--dev]
uv run ralph-agent deps remove PACKAGE
uv run ralph-agent deps sync
```

## Workflow Phases

### 1. Discovery Phase
Uses the Jobs-to-be-Done (JTBD) framework to gather requirements through interactive questioning. Creates spec files in `specs/` directory.

**Tools available**: Read, Glob, Grep, WebSearch, WebFetch, Write, Task, AskUserQuestion

### 2. Planning Phase
Analyzes specs and existing codebase to create an implementation plan with sized, prioritized tasks. Each task is designed to fit within a single context window (~30 min work).

**Tools available**: Read, Glob, Grep, WebSearch, WebFetch, Write, Task, ExitPlanMode

### 3. Building Phase
Iteratively implements tasks from the plan using TDD approach:
1. Get next task (deterministic: highest priority with met dependencies)
2. Mark task in progress
3. Write failing tests
4. Implement feature
5. Make tests pass
6. Mark task complete

**Tools available**: Read, Write, Edit, Bash, Glob, Grep, Task, TodoWrite, WebSearch, WebFetch, NotebookEdit

### 4. Validation Phase
Comprehensive verification including:
- Running all tests
- Linting with ruff
- Type checking with mypy
- Verifying specs compliance

**Tools available**: Read, Glob, Grep, Bash, Task, WebFetch

## Subagents

Ralph includes specialized AI subagents that provide domain expertise during development. These subagents operate with read-only access and are automatically invoked through the `Task` tool based on the current phase.

### Available Subagents

| Subagent | Purpose | Available In |
|----------|---------|--------------|
| **Research Specialist** | Technology evaluation, pattern research, best practices | Discovery, Planning, Building |
| **Code Reviewer** | Security analysis, code quality assessment | Building, Validation |
| **Test Engineer** | Test strategy development, coverage analysis | Building, Validation |
| **Documentation Agent** | API docs, technical documentation | Discovery, Planning, Validation |
| **Product Analyst** | Requirements analysis, acceptance criteria validation | Discovery |

### Security Model

All subagents have read-only access and cannot:
- Modify files (`Write`, `Edit`, `NotebookEdit`)
- Execute commands (`Bash`)
- Spawn other subagents (`Task`)

Only the Research Specialist can access web resources (`WebSearch`, `WebFetch`) for gathering external information.

### Usage

Subagents are automatically available based on the current phase. Use the `Task` tool to delegate work:

```
Task(
    subagent_type="research-specialist",
    description="Evaluate authentication libraries",
    prompt="Compare JWT vs session-based auth for our API"
)
```

For complete documentation, see [docs/subagents.md](docs/subagents.md).

## Project Structure

```
.ralph/
├── state.json              # Master state (phase, iteration, costs)
├── implementation_plan.json # Task list with dependencies
├── MEMORY.md               # Active memory (injected into prompts)
├── session_history/        # Context handoff records
└── memory/                 # Deterministic memory capture
    ├── phases/             # Phase transition memories
    ├── iterations/         # Iteration boundary memories
    ├── sessions/           # Session handoff memories
    └── archive/            # Rotated old files

specs/                      # Requirement specifications (from Discovery)
progress.txt               # Operational learnings log
```

## Configuration

Ralph looks for `ralph.yml` in the project root:

```yaml
# ralph.yml
max_iterations: 100
primary_model: "claude-sonnet-4-20250514"
planning_model: "claude-opus-4-20250514"
cost_limits:
  per_iteration: 10.0
  per_session: 50.0
  total: 100.0
safety:
  max_retries: 3
  sandbox_enabled: true
  git_read_only: true
circuit_breaker_failures: 3
circuit_breaker_stagnation: 5
```

## Safety Controls

### Circuit Breaker
Halts execution when:
- 3 consecutive failures
- 5 iterations without progress (stagnation)
- Cost limit exceeded

### Command Blocking
- **Git operations**: commit, push, pull, merge, rebase, checkout, reset (read-only git only)
- **Package managers**: pip, conda, poetry, pipenv (uv only)

### Context Management
- Targets 40-60% context utilization ("smart zone")
- Automatic handoff before reaching 80%
- State persists across context window resets

## Error Recovery & Troubleshooting

Ralph includes robust error handling, but sometimes manual intervention is needed. This section explains how to recover from common failure scenarios.

### Understanding Circuit Breaker States

The circuit breaker protects against runaway failures and wasted resources:

| State | Meaning | Action |
|-------|---------|--------|
| **Closed** | Normal operation | Continue as usual |
| **Open** | Halted due to failures | Manual recovery required |
| **Half-Open** | Testing recovery | Automatic after successful iteration |

Check circuit breaker status with:
```bash
uv run ralph-agent status --verbose
```

### Recovery Scenarios

#### Scenario 1: Consecutive Failures (3+ failures)

**Symptoms**: Loop halts with "circuit breaker open" message.

**Diagnosis**:
```bash
# Check what went wrong
uv run ralph-agent status --verbose
uv run ralph-agent tasks --all
```

**Recovery Options**:

1. **Skip the problematic task** (most common fix):
   ```bash
   uv run ralph-agent skip TASK_ID --reason "Task requires manual intervention"
   uv run ralph-agent resume
   ```

2. **Provide guidance for the next attempt**:
   ```bash
   uv run ralph-agent inject "Focus on fixing the import error in auth.py first" --priority 1
   uv run ralph-agent resume
   ```

3. **Reset and retry** (if state is corrupted):
   ```bash
   uv run ralph-agent reset --keep-plan
   uv run ralph-agent run
   ```

#### Scenario 2: Stagnation (5+ iterations without progress)

**Symptoms**: Loop halts with "stagnation detected" message.

**Diagnosis**: The LLM may be stuck on a task that's too large or poorly defined.

**Recovery Options**:

1. **Regenerate the plan** with better task breakdown:
   ```bash
   uv run ralph-agent regenerate-plan
   uv run ralph-agent run
   ```

2. **Skip the stuck task** and continue:
   ```bash
   uv run ralph-agent skip TASK_ID --reason "Task too complex, needs manual breakdown"
   uv run ralph-agent resume
   ```

3. **Inject clarifying context**:
   ```bash
   uv run ralph-agent inject "The database schema is in db/models.py, not models/" --priority 1
   uv run ralph-agent resume
   ```

#### Scenario 3: Cost Limit Exceeded

**Symptoms**: Loop halts with "cost limit exceeded" message.

**Recovery**:
1. Review spending: `uv run ralph-agent status --verbose`
2. Increase limits in `ralph.yml` if appropriate
3. Resume: `uv run ralph-agent resume`

#### Scenario 4: Context Window Exhaustion

**Symptoms**: Handoff triggered frequently, slow progress.

**Recovery**: This is normal behavior. Ralph automatically:
- Writes session summary to `MEMORY.md`
- Archives session to `.ralph/session_history/`
- Starts fresh context with preserved state

If you need to force a handoff:
```bash
uv run ralph-agent handoff --reason "Starting fresh for clarity"
```

### Manual Task Management

#### Skip a Task
```bash
# Mark task as blocked and move on
uv run ralph-agent skip task-003 --reason "Requires API key not available"
```

#### Check Task Details
```bash
# List all tasks with status
uv run ralph-agent tasks --all

# List only pending tasks
uv run ralph-agent tasks --pending
```

#### Regenerate Plan
```bash
# Discard current plan and create new one from specs
uv run ralph-agent regenerate-plan

# Keep completed tasks, regenerate remaining
uv run ralph-agent regenerate-plan --discard-completed
```

### Useful Diagnostic Commands

```bash
# Full state overview
uv run ralph-agent status --verbose

# Session history (costs, iterations, handoffs)
uv run ralph-agent history

# Check what files were modified
git status

# Review recent learnings
cat progress.txt | tail -20
```

### When to Start Fresh

If recovery attempts fail, you can reset completely:

```bash
# Clean up all state files (recommended for fresh start)
uv run ralph-agent clean

# Clean up state files including memory
uv run ralph-agent clean --memory

# Preview what would be cleaned
uv run ralph-agent clean --dry-run

# Reset state but keep the plan (alternative to clean)
uv run ralph-agent reset --keep-plan

# Full reset (removes plan too)
uv run ralph-agent reset

# Then reinitialize
uv run ralph-agent init --force
```

## Development

```bash
# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=ralph

# Lint code
uv run ruff check .

# Auto-fix lint issues
uv run ruff check . --fix

# Type check
uv run mypy .
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI (cli.py)                         │
├─────────────────────────────────────────────────────────────┤
│                    LoopRunner (runner.py)                   │
├─────────────────────────────────────────────────────────────┤
│   DiscoveryExecutor │ PlanningExecutor │ BuildingExecutor │ ValidationExecutor
│                      (executors.py)                         │
├─────────────────────────────────────────────────────────────┤
│                  RalphSDKClient (sdk_client.py)             │
├─────────────────────────────────────────────────────────────┤
│  MCP Tools (mcp_tools.py)  │  Hooks (sdk_hooks.py)         │
├─────────────────────────────────────────────────────────────┤
│                   Claude Agent SDK                          │
└─────────────────────────────────────────────────────────────┘
```

## MCP Tools

Ralph exposes these tools via MCP for the LLM to manage state:

| Tool | Description |
|------|-------------|
| `ralph_get_next_task` | Get highest-priority incomplete task |
| `ralph_mark_task_complete` | Mark task as completed with notes |
| `ralph_mark_task_blocked` | Mark task as blocked with reason |
| `ralph_mark_task_in_progress` | Mark task as in progress |
| `ralph_append_learning` | Record a learning for future iterations |
| `ralph_get_plan_summary` | Get implementation plan summary |
| `ralph_get_state_summary` | Get current Ralph state summary |
| `ralph_add_task` | Add a new task to the plan |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | API key for Claude (optional if using Claude Code CLI authentication) |

### Authentication

Ralph supports two authentication methods:

1. **ANTHROPIC_API_KEY**: Set this environment variable with your Anthropic API key
2. **Claude Code CLI**: If you have Claude Code installed and are logged in with your subscription, no API key is required - the SDK authenticates automatically via the local Claude Code instance

## License

MIT
