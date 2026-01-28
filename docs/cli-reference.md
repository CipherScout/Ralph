# Ralph CLI Reference

Ralph is a deterministic agentic coding loop using Claude Agent SDK. This document provides comprehensive documentation for all CLI commands.

## Quick Reference

| Command | Description |
|---------|-------------|
| `ralph-agent version` | Show Ralph version |
| `ralph-agent init` | Initialize Ralph in a project directory |
| `ralph-agent status` | Show current Ralph state |
| `ralph-agent tasks` | List tasks in the implementation plan |
| `ralph-agent reset` | Reset Ralph state to initial values |
| `ralph-agent clean` | Clean up Ralph state files for a fresh start |
| `ralph-agent run` | Run the full Ralph loop |
| `ralph-agent discover` | Run the Discovery phase with JTBD framework |
| `ralph-agent plan` | Run the Planning phase with gap analysis |
| `ralph-agent build` | Run the Building phase with iterative task execution |
| `ralph-agent validate` | Run the Validation phase with verification |
| `ralph-agent pause` | Pause the Ralph loop after current iteration |
| `ralph-agent resume` | Resume a paused Ralph loop |
| `ralph-agent skip` | Skip a task by marking it as blocked |
| `ralph-agent inject` | Inject a message into the next iteration's context |
| `ralph-agent handoff` | Manually trigger a context handoff |
| `ralph-agent regenerate-plan` | Regenerate the implementation plan from specs |
| `ralph-agent history` | Show session history |
| `ralph-agent memory` | Manage Ralph memory system |
| `ralph-agent test` | Run tests using uv run pytest |
| `ralph-agent lint` | Run linting using uv run ruff |
| `ralph-agent typecheck` | Run type checking using uv run mypy |
| `ralph-agent deps` | Dependency management commands |

---

## Global Options

These options are available for all commands:

| Option | Description |
|--------|-------------|
| `--install-completion` | Install completion for the current shell |
| `--show-completion` | Show completion for the current shell, to copy it or customize the installation |
| `--help` | Show help message and exit |

---

## Core Commands

Core commands are essential for initializing and managing Ralph projects.

### init

Initialize Ralph in a project directory.

#### Synopsis

```
ralph-agent init [OPTIONS]
```

#### Description

Creates the `.ralph/` directory structure with `state.json` and `implementation_plan.json` files. This command must be run before using any other Ralph commands in a project.

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--force` | `-f` | FLAG | `false` | Reinitialize even if already exists |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Initialize Ralph in the current directory
ralph-agent init

# Initialize Ralph in a specific directory
ralph-agent init -p /path/to/project

# Force reinitialize an existing Ralph project
ralph-agent init --force

# Initialize in a subdirectory with force flag
ralph-agent init -p ./my-project -f
```

#### See Also

- `status` - View the initialized state
- `reset` - Reset state without removing `.ralph/` directory

---

### status

Show current Ralph state.

#### Synopsis

```
ralph-agent status [OPTIONS]
```

#### Description

Displays the current state of the Ralph project including the current phase, iteration count, task progress, and any active flags (paused, blocked, etc.).

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--verbose` | `-v` | FLAG | `false` | Show detailed information |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Show basic status
ralph-agent status

# Show detailed status information
ralph-agent status -v

# Check status of a project in another directory
ralph-agent status -p /path/to/project
```

#### See Also

- `tasks` - List implementation tasks
- `history` - View session history

---

### tasks

List tasks in the implementation plan.

#### Synopsis

```
ralph-agent tasks [OPTIONS]
```

#### Description

Lists all tasks defined in the implementation plan. By default, shows tasks that are not yet completed. Use filters to show specific subsets of tasks.

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--pending` | | FLAG | `false` | Show only pending tasks |
| `--all` | `-a` | FLAG | `false` | Show all tasks including completed |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# List non-completed tasks (default view)
ralph-agent tasks

# List only pending tasks (not started)
ralph-agent tasks --pending

# List all tasks including completed ones
ralph-agent tasks --all

# List tasks for a project in another directory
ralph-agent tasks -p /path/to/project -a
```

#### See Also

- `skip` - Skip a specific task
- `plan` - Generate or regenerate the task plan

---

### reset

Reset Ralph state to initial values.

#### Synopsis

```
ralph-agent reset [OPTIONS]
```

#### Description

Resets the Ralph state file to its initial values. This clears iteration counts, phase progress, and flags. By default, also clears the implementation plan unless `--keep-plan` is specified.

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--keep-plan` | | FLAG | `false` | Keep implementation plan |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Full reset including plan
ralph-agent reset

# Reset state but keep the implementation plan
ralph-agent reset --keep-plan

# Reset a project in another directory
ralph-agent reset -p /path/to/project
```

#### See Also

- `init` - Initialize a fresh Ralph project
- `regenerate-plan` - Regenerate plan without full reset
- `clean` - Clean up state files completely

---

### clean

Clean up Ralph state files for a fresh start.

#### Synopsis

```
ralph-agent clean [OPTIONS]
```

#### Description

Removes all Ralph state files (state.json, implementation_plan.json, injections.json, and progress.txt) to achieve an init-equivalent state. Configuration files (config.yaml) are always preserved.

This command is useful when you want to start completely fresh without manually deleting files, or after completing a development cycle.

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--memory` | `-m` | FLAG | `false` | Also remove memory files (MEMORY.md, memory/) |
| `--force` | `-f` | FLAG | `false` | Skip confirmation prompt |
| `--dry-run` | | FLAG | `false` | Show what would be cleaned without deleting |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Clean state files with confirmation prompt
ralph-agent clean

# Preview what would be cleaned without deleting
ralph-agent clean --dry-run

# Clean without confirmation (for scripts)
ralph-agent clean --force

# Clean state files and memory
ralph-agent clean --memory

# Clean everything including memory, no confirmation
ralph-agent clean --memory --force

# Clean a project in another directory
ralph-agent clean -p /path/to/project
```

#### What Gets Cleaned

**Always removed (if they exist):**
- `.ralph/state.json` - Current phase, iteration count, flags
- `.ralph/implementation_plan.json` - Task list and dependencies
- `.ralph/injections.json` - Injected context messages
- `progress.txt` - Operational learnings log

**Removed only with `--memory` flag:**
- `.ralph/MEMORY.md` - Active memory content
- `.ralph/memory/` - Memory directory with all memory files

**Always preserved:**
- `.ralph/config.yaml` - User configuration
- `.ralph/` directory itself

#### See Also

- `init` - Initialize a fresh Ralph project
- `reset` - Reset state values without removing files

---

### run

Run the full Ralph loop.

#### Synopsis

```
ralph-agent run [OPTIONS]
```

#### Description

Orchestrates the complete Ralph development workflow through all four phases:

1. **DISCOVERY** - Gather requirements using JTBD (Jobs To Be Done) framework
2. **PLANNING** - Create implementation plan with sized tasks
3. **BUILDING** - Execute tasks with TDD and backpressure
4. **VALIDATION** - Verify implementation meets requirements

The loop continues until all tasks are complete, the circuit breaker trips, or the maximum iteration count is reached.

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--phase` | | TEXT | | Start from specific phase |
| `--max-iterations` | `-n` | INTEGER | | Maximum iterations |
| `--dry-run` | | FLAG | `false` | Show what would be done without executing |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Run the full loop with defaults
ralph-agent run

# Run starting from a specific phase
ralph-agent run --phase building

# Run with a maximum iteration limit
ralph-agent run -n 50

# Preview what would be done without executing
ralph-agent run --dry-run

# Run in a different project directory with iteration limit
ralph-agent run -p /path/to/project -n 100
```

#### See Also

- `discover` - Run only the discovery phase
- `plan` - Run only the planning phase
- `build` - Run only the building phase
- `validate` - Run only the validation phase

---

## Phase Commands

Phase commands allow running individual phases of the Ralph loop independently.

### discover

Run the Discovery phase with JTBD framework.

#### Synopsis

```
ralph-agent discover [OPTIONS]
```

#### Description

Executes the Discovery phase which gathers requirements using the Jobs To Be Done (JTBD) framework. This phase analyzes the project goal and produces specifications that inform the planning phase.

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--goal` | `-g` | TEXT | | Project goal |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Run discovery with interactive goal input
ralph-agent discover

# Run discovery with a specified goal
ralph-agent discover -g "Build a REST API for user authentication"

# Run discovery for a project in another directory
ralph-agent discover -p /path/to/project -g "Add payment processing"
```

#### See Also

- `plan` - Next phase after discovery
- `run` - Run the full loop

---

### plan

Run the Planning phase with gap analysis.

#### Synopsis

```
ralph-agent plan [OPTIONS]
```

#### Description

Executes the Planning phase which performs gap analysis between the current codebase and the requirements from discovery. Produces a sized implementation plan with tasks ordered by dependencies.

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Run planning phase
ralph-agent plan

# Run planning for a project in another directory
ralph-agent plan -p /path/to/project
```

#### See Also

- `discover` - Previous phase
- `build` - Next phase after planning
- `regenerate-plan` - Regenerate an existing plan
- `tasks` - View the generated tasks

---

### build

Run the Building phase with iterative task execution.

#### Synopsis

```
ralph-agent build [OPTIONS]
```

#### Description

Executes the Building phase which implements tasks from the plan using Test-Driven Development (TDD) and backpressure mechanisms. Tasks are executed iteratively with continuous validation.

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--task` | `-t` | TEXT | | Specific task to work on |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Run building phase (works on next pending task)
ralph-agent build

# Work on a specific task by ID
ralph-agent build -t task-001

# Build in a different project directory
ralph-agent build -p /path/to/project

# Work on specific task in specific project
ralph-agent build -p /path/to/project -t auth-implementation
```

#### See Also

- `plan` - Previous phase
- `validate` - Next phase after building
- `tasks` - View available tasks
- `skip` - Skip a blocked task

---

### validate

Run the Validation phase with verification.

#### Synopsis

```
ralph-agent validate [OPTIONS]
```

#### Description

Executes the Validation phase which verifies that the implementation meets all requirements from the discovery phase. Runs comprehensive checks including tests, linting, and type checking.

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Run validation phase
ralph-agent validate

# Validate a project in another directory
ralph-agent validate -p /path/to/project
```

#### See Also

- `build` - Previous phase
- `test` - Run tests independently
- `lint` - Run linting independently
- `typecheck` - Run type checking independently

---

## Control Commands

Control commands allow manual intervention in the Ralph loop execution.

### pause

Pause the Ralph loop after current iteration.

#### Synopsis

```
ralph-agent pause [OPTIONS]
```

#### Description

Signals Ralph to pause after completing the current iteration. The loop will stop gracefully, preserving all state for later resumption.

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Pause the running loop
ralph-agent pause

# Pause a loop in another project
ralph-agent pause -p /path/to/project
```

#### See Also

- `resume` - Resume a paused loop
- `status` - Check if loop is paused

---

### resume

Resume a paused Ralph loop.

#### Synopsis

```
ralph-agent resume [OPTIONS]
```

#### Description

Resumes a previously paused Ralph loop, continuing from where it left off.

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Resume the paused loop
ralph-agent resume

# Resume a loop in another project
ralph-agent resume -p /path/to/project
```

#### See Also

- `pause` - Pause a running loop
- `status` - Check current state

---

### skip

Skip a task by marking it as blocked.

#### Synopsis

```
ralph-agent skip [OPTIONS] TASK_ID
```

#### Description

Marks a specific task as blocked/skipped, allowing the loop to continue with other tasks. Useful when a task is blocked by external factors or needs to be deferred.

#### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `TASK_ID` | Yes | Task ID to skip |

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--reason` | `-r` | TEXT | | Reason for skipping |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Skip a task without a reason
ralph-agent skip task-003

# Skip a task with a reason
ralph-agent skip task-003 -r "Waiting for API credentials"

# Skip a task in another project
ralph-agent skip task-003 -p /path/to/project -r "Blocked by external dependency"
```

#### See Also

- `tasks` - List tasks to find task IDs
- `inject` - Add context about why task was skipped

---

### inject

Inject a message into the next iteration's context.

#### Synopsis

```
ralph-agent inject [OPTIONS] MESSAGE
```

#### Description

Injects a custom message into the context that will be available to the next iteration of the Ralph loop. Useful for providing additional guidance, constraints, or information to the agent.

#### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `MESSAGE` | Yes | Message to inject into context |

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--priority` | | INTEGER | `0` | Injection priority (higher = processed first) |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Inject a simple message
ralph-agent inject "Focus on error handling in the next iteration"

# Inject a high-priority message
ralph-agent inject "CRITICAL: Do not modify the database schema" --priority 10

# Inject guidance for a specific project
ralph-agent inject -p /path/to/project "Use the new API endpoint format"

# Inject multiple messages with different priorities
ralph-agent inject "Consider performance implications" --priority 5
ralph-agent inject "Follow the existing code style" --priority 3
```

#### See Also

- `status` - View injected messages
- `handoff` - Trigger context handoff with summary

---

### handoff

Manually trigger a context handoff.

#### Synopsis

```
ralph-agent handoff [OPTIONS]
```

#### Description

Manually triggers a context handoff, which saves the current session state and prepares for a new context window. Useful when approaching context limits or when you want to checkpoint progress.

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--reason` | `-r` | TEXT | `manual` | Handoff reason |
| `--summary` | `-s` | TEXT | | Session summary |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Trigger a simple manual handoff
ralph-agent handoff

# Handoff with a reason
ralph-agent handoff -r "Approaching context limit"

# Handoff with a detailed summary
ralph-agent handoff -r "checkpoint" -s "Completed auth module, starting on API routes"

# Handoff in another project
ralph-agent handoff -p /path/to/project -r "end of session" -s "All tests passing"
```

#### See Also

- `history` - View handoff history
- `inject` - Add context for next session

---

### regenerate-plan

Regenerate the implementation plan from specs.

#### Synopsis

```
ralph-agent regenerate-plan [OPTIONS]
```

#### Description

Discards the current implementation plan and re-runs the planning phase to generate a new plan from the existing specifications. Useful when the plan has diverged from reality or when specs have been updated.

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--discard-completed` | | FLAG | `false` | Discard completed tasks (default: keep them) |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Regenerate plan, keeping completed tasks
ralph-agent regenerate-plan

# Regenerate plan, discarding all task progress
ralph-agent regenerate-plan --discard-completed

# Regenerate plan for another project
ralph-agent regenerate-plan -p /path/to/project
```

#### See Also

- `plan` - Run planning phase
- `tasks` - View the new plan
- `reset` - Full state reset

---

## Development Commands

Development commands provide shortcuts for common development tasks.

### test

Run tests using uv run pytest.

#### Synopsis

```
ralph-agent test [OPTIONS] [ARGS]...
```

#### Description

Executes the project's test suite using pytest through uv. Additional arguments are passed directly to pytest.

#### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `ARGS` | No | Additional pytest arguments |

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Run all tests
ralph-agent test

# Run tests with verbose output
ralph-agent test -v

# Run a specific test file
ralph-agent test tests/test_auth.py

# Run tests matching a pattern
ralph-agent test -k "test_login"

# Run tests with coverage
ralph-agent test --cov=src

# Run tests in another project
ralph-agent test -p /path/to/project -v
```

#### See Also

- `lint` - Run linting
- `typecheck` - Run type checking
- `validate` - Run full validation phase

---

### lint

Run linting using uv run ruff.

#### Synopsis

```
ralph-agent lint [OPTIONS]
```

#### Description

Runs the ruff linter on the project codebase through uv. Can optionally auto-fix issues.

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--fix` | | FLAG | `false` | Auto-fix issues |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Run linting (report only)
ralph-agent lint

# Run linting with auto-fix
ralph-agent lint --fix

# Lint another project
ralph-agent lint -p /path/to/project

# Lint and fix another project
ralph-agent lint -p /path/to/project --fix
```

#### See Also

- `test` - Run tests
- `typecheck` - Run type checking
- `validate` - Run full validation phase

---

### typecheck

Run type checking using uv run mypy.

#### Synopsis

```
ralph-agent typecheck [OPTIONS]
```

#### Description

Runs mypy type checker on the project codebase through uv.

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Run type checking
ralph-agent typecheck

# Type check another project
ralph-agent typecheck -p /path/to/project
```

#### See Also

- `test` - Run tests
- `lint` - Run linting
- `validate` - Run full validation phase

---

### deps

Dependency management commands.

#### Synopsis

```
ralph-agent deps [OPTIONS] COMMAND [ARGS]...
```

#### Description

Parent command for dependency management operations. Provides subcommands for adding, removing, and syncing dependencies using uv.

#### Subcommands

| Subcommand | Description |
|------------|-------------|
| `add` | Add dependencies using uv add |
| `sync` | Sync dependencies using uv sync |
| `remove` | Remove dependencies using uv remove |

---

### deps add

Add dependencies using uv add.

#### Synopsis

```
ralph-agent deps add [OPTIONS] PACKAGES...
```

#### Description

Adds one or more packages to the project dependencies using uv add.

#### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `PACKAGES` | Yes | Packages to add |

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--dev` | `-d` | FLAG | `false` | Add as dev dependency |
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Add a production dependency
ralph-agent deps add requests

# Add multiple dependencies
ralph-agent deps add requests httpx pydantic

# Add a dev dependency
ralph-agent deps add -d pytest

# Add dependencies to another project
ralph-agent deps add -p /path/to/project fastapi uvicorn
```

#### See Also

- `deps remove` - Remove dependencies
- `deps sync` - Sync dependencies

---

### deps sync

Sync dependencies using uv sync.

#### Synopsis

```
ralph-agent deps sync [OPTIONS]
```

#### Description

Synchronizes the project dependencies with the lock file using uv sync.

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Sync dependencies
ralph-agent deps sync

# Sync dependencies in another project
ralph-agent deps sync -p /path/to/project
```

#### See Also

- `deps add` - Add dependencies
- `deps remove` - Remove dependencies

---

### deps remove

Remove dependencies using uv remove.

#### Synopsis

```
ralph-agent deps remove [OPTIONS] PACKAGES...
```

#### Description

Removes one or more packages from the project dependencies using uv remove.

#### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `PACKAGES` | Yes | Packages to remove |

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Remove a dependency
ralph-agent deps remove requests

# Remove multiple dependencies
ralph-agent deps remove requests httpx

# Remove dependencies from another project
ralph-agent deps remove -p /path/to/project flask
```

#### See Also

- `deps add` - Add dependencies
- `deps sync` - Sync dependencies

---

## Information Commands

Information commands provide visibility into Ralph's state and history.

### version

Show Ralph version.

#### Synopsis

```
ralph-agent version [OPTIONS]
```

#### Description

Displays the current version of Ralph.

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Show version
ralph-agent version
```

#### See Also

- `status` - Show project status

---

### history

Show session history.

#### Synopsis

```
ralph-agent history [OPTIONS]
```

#### Description

Displays the history of Ralph sessions including handoffs, phase transitions, and key events.

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--limit` | `-n` | INTEGER | `10` | Number of sessions to show |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Show last 10 sessions (default)
ralph-agent history

# Show last 5 sessions
ralph-agent history -n 5

# Show full history (50 sessions)
ralph-agent history -n 50

# Show history for another project
ralph-agent history -p /path/to/project -n 20
```

#### See Also

- `status` - Show current state
- `handoff` - Trigger a handoff
- `memory` - View and manage memory system

---

### memory

Manage Ralph memory system.

#### Synopsis

```
ralph-agent memory [OPTIONS]
```

#### Description

View, inspect, and manage Ralph's deterministic memory system. The memory system automatically captures context at:

- **Phase transitions** - When moving between discovery/planning/building/validation
- **Iteration boundaries** - At the end of each iteration within a phase
- **Session handoffs** - When a session ends

This command allows you to view the active memory content, see statistics about memory files, and run cleanup operations.

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--project-root` | `-p` | TEXT | `.` | Project root directory |
| `--show` | `-s` | FLAG | `false` | Show active memory content |
| `--stats` | | FLAG | `false` | Show memory statistics |
| `--cleanup` | | FLAG | `false` | Run memory cleanup (rotate and archive) |
| `--help` | | FLAG | | Show this message and exit |

#### Examples

```bash
# Show active memory content (default if no flags provided)
ralph-agent memory
ralph-agent memory --show

# Show memory file statistics
ralph-agent memory --stats

# Run memory cleanup (rotate old files to archive)
ralph-agent memory --cleanup

# View memory for another project
ralph-agent memory -p /path/to/project --show

# Combine options
ralph-agent memory --stats --cleanup
```

#### Memory Directory Structure

The memory system stores files in `.ralph/memory/`:

```
.ralph/
├── MEMORY.md                 # Active memory (injected into prompts)
└── memory/
    ├── phases/               # Phase transition memories
    │   ├── discovery.md
    │   ├── planning.md
    │   └── building.md
    ├── iterations/           # Iteration memories
    │   ├── iter-001.md
    │   └── iter-002.md
    ├── sessions/             # Session handoff memories
    │   └── session-001.md
    └── archive/              # Rotated old files
```

#### Configuration

Memory behavior can be configured via the `MemoryConfig`:

| Setting | Default | Description |
|---------|---------|-------------|
| `max_active_memory_chars` | 8,000 | Maximum characters in active memory |
| `max_iteration_files` | 20 | Maximum iteration memory files before rotation |
| `max_session_files` | 10 | Maximum session memory files before rotation |
| `archive_retention_days` | 30 | Days to keep archived files |

#### See Also

- `status` - Show current state
- `history` - View session history
- `handoff` - Trigger a handoff

---

## Environment Variables

Ralph respects the following environment variables:

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | API key for Claude Agent SDK |
| `RALPH_PROJECT_ROOT` | Default project root directory |
| `RALPH_LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) |

---

## Exit Codes

| Code | Description |
|------|-------------|
| `0` | Success |
| `1` | General error |
| `2` | Invalid usage / bad arguments |
| `3` | Project not initialized |
| `4` | Circuit breaker tripped |
| `5` | Max iterations reached |

---

## Files

Ralph creates and uses the following files in the `.ralph/` directory:

| File | Description |
|------|-------------|
| `state.json` | Current state of the Ralph loop |
| `implementation_plan.json` | Task plan with dependencies and sizing |
| `specs/` | Discovery phase specifications |
| `history/` | Session history and handoff records |
| `context/` | Injected context messages |

---

## Workflow Examples

### Starting a New Project

```bash
# Initialize Ralph
ralph-agent init

# Set a goal and run discovery
ralph-agent discover -g "Build a REST API for user management"

# Generate the implementation plan
ralph-agent plan

# Review the tasks
ralph-agent tasks

# Run the full loop
ralph-agent run
```

### Resuming Work

```bash
# Check current status
ralph-agent status -v

# See remaining tasks
ralph-agent tasks --pending

# Resume the loop
ralph-agent run
```

### Handling Blocked Tasks

```bash
# List tasks to find the blocked one
ralph-agent tasks

# Skip the blocked task with a reason
ralph-agent skip task-005 -r "Waiting for database access"

# Inject context for the next iteration
ralph-agent inject "Skip database tasks until credentials are available"

# Continue with other tasks
ralph-agent run
```

### Manual Phase Control

```bash
# Run phases individually for more control
ralph-agent discover -g "Add payment processing"
ralph-agent plan
ralph-agent build -t payment-integration
ralph-agent validate
```

---

## Troubleshooting

### Common Issues

**"Ralph not initialized"**
```bash
ralph-agent init
```

**"No tasks in plan"**
```bash
ralph-agent discover -g "Your project goal"
ralph-agent plan
```

**"Circuit breaker tripped"**
```bash
ralph-agent status -v  # Check what went wrong
ralph-agent reset --keep-plan  # Reset state, keep tasks
ralph-agent run  # Try again
```

**"Max iterations reached"**
```bash
ralph-agent run -n 200  # Increase limit
```

---

## See Also

- [Ralph Documentation](./README.md)
- [Architecture Guide](./architecture.md)
- [Configuration Reference](./configuration.md)
