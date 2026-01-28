# Configuration Guide

This guide covers all configuration options for Ralph, a deterministic agentic coding loop using the Claude Agent SDK.

## Configuration Overview

Ralph uses a layered configuration system that provides flexibility while maintaining sensible defaults.

### Configuration Loading Order

Ralph loads configuration in the following order, with later sources overriding earlier ones:

1. **Built-in Defaults** - Sensible defaults for all options
2. **Project Configuration** (`.ralph/config.yaml`) - Project-specific settings
3. **Environment Variables** - Runtime overrides for CI/CD and local development

```
┌─────────────────────────────────────────────────────────────┐
│                    Environment Variables                     │
│                    (highest precedence)                      │
├─────────────────────────────────────────────────────────────┤
│                  .ralph/config.yaml                          │
│                  (project settings)                          │
├─────────────────────────────────────────────────────────────┤
│                    Built-in Defaults                         │
│                    (lowest precedence)                       │
└─────────────────────────────────────────────────────────────┘
```

### Configuration File Location

Ralph looks for configuration at:

```
your-project/
├── .ralph/
│   └── config.yaml    # Project configuration
├── src/
└── ...
```

Create this file manually or use `ralph init` to generate a default configuration.

---

## Project Configuration (ralph.yml)

### Complete Configuration Reference

Below is a complete reference of all configuration options with their default values.

#### Project Section

Defines basic project metadata.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `name` | string | `""` | Project name (defaults to directory name if empty) |
| `root` | string | `"."` | Project root directory relative to config file |
| `python_version` | string | `"3.13"` | Python version for the project |

```yaml
project:
  name: "my-project"
  root: "."
  python_version: "3.13"
```

#### Build Section

Configures build tools and commands.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `tool` | string | `"uv"` | Build tool (`uv`, `pip`, `poetry`) |
| `test_command` | string | `"uv run pytest"` | Command to run tests |
| `lint_command` | string | `"uv run ruff check ."` | Command to run linter |
| `typecheck_command` | string | `"uv run mypy ."` | Command to run type checker |
| `format_command` | string | `"uv run ruff format ."` | Command to format code |

```yaml
build:
  tool: "uv"
  test_command: "uv run pytest"
  lint_command: "uv run ruff check ."
  typecheck_command: "uv run mypy ."
  format_command: "uv run ruff format ."
```

#### Cost Limits Section

Controls spending limits at different granularities. Cost limits are nested under the `safety` section.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `per_iteration` | float | `10.0` | Maximum cost per single iteration (USD) |
| `per_session` | float | `50.0` | Maximum cost per session (USD) |
| `total` | float | `100.0` | Maximum total cost across all sessions (USD) |

```yaml
safety:
  cost_limits:
    per_iteration: 10.0
    per_session: 50.0
    total: 100.0
```

#### Context Section

Manages memory limits.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `max_progress_entries` | integer | `20` | Maximum progress log entries to retain |
| `max_files_in_memory` | integer | `10` | Maximum files to keep in working memory |
| `max_session_history` | integer | `50` | Maximum session history entries |

```yaml
context:
  max_progress_entries: 20
  max_files_in_memory: 10
  max_session_history: 50
```

#### Phases Section

Configures behavior for each phase of the Ralph loop.

**Discovery Phase**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `human_in_loop` | boolean | `true` | Require human confirmation for clarifications |
| `max_questions` | integer | `10` | Maximum clarifying questions to ask |

**Planning Phase**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `task_size_tokens` | integer | `30000` | Target token size for task chunks |
| `dependency_analysis` | boolean | `true` | Analyze task dependencies |

**Building Phase**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `max_iterations` | integer | `100` | Maximum iterations before stopping |
| `backpressure` | list[string] | See below | Commands to run after each change |

Default backpressure commands:
```yaml
backpressure:
  - "uv run pytest"
  - "uv run mypy ."
  - "uv run ruff check ."
```

**Validation Phase**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `require_human_approval` | boolean | `true` | Require human approval before completion |

```yaml
phases:
  discovery:
    human_in_loop: true
    max_questions: 10
  planning:
    task_size_tokens: 30000
    dependency_analysis: true
  building:
    max_iterations: 100
    backpressure:
      - "uv run pytest"
      - "uv run mypy ."
      - "uv run ruff check ."
  validation:
    require_human_approval: true
```

#### Safety Section

Controls sandboxing, command blocking, and git restrictions.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `sandbox_enabled` | boolean | `true` | Enable command sandboxing |
| `blocked_commands` | list[string] | See below | Commands that are never allowed |
| `git_read_only` | boolean | `true` | Restrict git to read-only operations |
| `allowed_git_operations` | list[string] | See below | Git operations allowed when read-only |
| `max_retries` | integer | `3` | Maximum retries for failed operations |

Default blocked commands:
```yaml
blocked_commands:
  - "rm -rf"
  - "docker rm"
  - "pip install"
  - "python -m venv"
```

Default allowed git operations:
```yaml
allowed_git_operations:
  - "status"
  - "log"
  - "diff"
```

```yaml
safety:
  sandbox_enabled: true
  blocked_commands:
    - "rm -rf"
    - "docker rm"
    - "pip install"
  git_read_only: true
  allowed_git_operations:
    - "status"
    - "log"
    - "diff"
  max_retries: 3
```

#### Circuit Breaker Settings

These are top-level settings that control failure detection.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `circuit_breaker_failures` | integer | `3` | Consecutive failures before circuit breaks |
| `circuit_breaker_stagnation` | integer | `5` | Iterations without progress before stopping |

### Full Example Configuration

```yaml
# .ralph/config.yaml
# Complete Ralph configuration with all options

# Project metadata
project:
  name: "my-awesome-project"
  root: "."
  python_version: "3.13"

# Build system configuration
build:
  tool: "uv"
  test_command: "uv run pytest -v"
  lint_command: "uv run ruff check . --fix"
  typecheck_command: "uv run mypy . --strict"
  format_command: "uv run ruff format ."

# Phase-specific settings
phases:
  discovery:
    # Enable human-in-loop for clarifying questions
    human_in_loop: true
    # Maximum questions before proceeding
    max_questions: 10

  planning:
    # Target size for task chunks (tokens)
    task_size_tokens: 30000
    # Analyze dependencies between tasks
    dependency_analysis: true

  building:
    # Maximum iterations per task
    max_iterations: 100
    # Commands to run after each code change
    backpressure:
      - "uv run pytest"
      - "uv run mypy ."
      - "uv run ruff check ."

  validation:
    # Require human approval before marking complete
    require_human_approval: true

# Context management
context:
  # Limits on in-memory items
  max_progress_entries: 20
  max_files_in_memory: 10
  max_session_history: 50

# Safety and cost controls
safety:
  # Enable sandboxed command execution
  sandbox_enabled: true
  # Commands that are never allowed
  blocked_commands:
    - "rm -rf"
    - "docker rm"
    - "pip install"
    - "python -m venv"
    - "sudo"
    - "curl | bash"
  # Restrict git to read-only operations
  git_read_only: true
  # Allowed git operations when read-only
  allowed_git_operations:
    - "status"
    - "log"
    - "diff"
    - "show"
  # Maximum retries for failed operations
  max_retries: 3
  # Cost controls
  cost_limits:
    per_iteration: 10.0
    per_session: 50.0
    total: 100.0
```

---

## Environment Variables

Environment variables provide runtime overrides and are ideal for CI/CD pipelines or temporary adjustments.

### Required Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key (required for all operations) |

### Model Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_PRIMARY_MODEL` | `claude-sonnet-4-20250514` | Model for building and general tasks |
| `RALPH_PLANNING_MODEL` | `claude-opus-4-20250514` | Model for planning phase (higher capability) |

### Runtime Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_MAX_ITERATIONS` | `100` | Maximum iterations before stopping |
| `RALPH_MAX_COST_USD` | `200.0` | Maximum total cost (overrides config) |
| `RALPH_CONTEXT_BUDGET_PERCENT` | `60` | Context window budget percentage |

### Circuit Breaker

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_CIRCUIT_BREAKER_FAILURES` | `3` | Consecutive failures before circuit breaks |
| `RALPH_CIRCUIT_BREAKER_STAGNATION` | `5` | Iterations without progress before stopping |

### Usage Examples

```bash
# Set API key (required)
export ANTHROPIC_API_KEY="sk-ant-..."

# Use a different model for building
export RALPH_PRIMARY_MODEL="claude-sonnet-4-20250514"

# Reduce costs for experimentation
export RALPH_MAX_COST_USD="10.0"

# Increase iteration limit for complex tasks
export RALPH_MAX_ITERATIONS="200"

# Run Ralph
ralph run "implement feature X"
```

### CI/CD Example

```yaml
# .github/workflows/ralph.yml
name: Ralph Task
on:
  workflow_dispatch:
    inputs:
      task:
        description: 'Task description'
        required: true

jobs:
  run-ralph:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Ralph
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          RALPH_MAX_COST_USD: "25.0"
          RALPH_MAX_ITERATIONS: "50"
        run: |
          ralph run "${{ inputs.task }}"
```

---

## Model Selection

Ralph uses different models for different phases to balance cost and capability.

### Available Models

| Model | Best For | Cost | Capability |
|-------|----------|------|------------|
| `claude-opus-4-20250514` | Complex planning, architecture | Highest | Highest |
| `claude-sonnet-4-20250514` | Building, general coding | Medium | High |

### Default Model Assignment

| Phase | Default Model | Rationale |
|-------|--------------|-----------|
| Discovery | `claude-sonnet-4-20250514` | Good at asking clarifying questions |
| Planning | `claude-opus-4-20250514` | Complex reasoning for task breakdown |
| Building | `claude-sonnet-4-20250514` | Fast iteration, good coding ability |
| Validation | `claude-sonnet-4-20250514` | Review and verification tasks |

### Customizing Models

Use environment variables to override model selection:

```bash
# Use Opus for all phases (higher quality, higher cost)
export RALPH_PRIMARY_MODEL="claude-opus-4-20250514"
export RALPH_PLANNING_MODEL="claude-opus-4-20250514"

# Use Sonnet for all phases (faster, lower cost)
export RALPH_PRIMARY_MODEL="claude-sonnet-4-20250514"
export RALPH_PLANNING_MODEL="claude-sonnet-4-20250514"
```

### Cost Implications

Approximate costs per 1M tokens (input + output):

| Model | Input | Output |
|-------|-------|--------|
| Claude Opus 4 | ~$15 | ~$75 |
| Claude Sonnet 4 | ~$3 | ~$15 |

**Recommendation**: Use the default configuration (Opus for planning, Sonnet for building) to balance cost and quality. Switch to all-Opus only for complex architectural tasks.

---

## Cost Management

Ralph provides multi-level cost controls to prevent runaway spending.

### How Cost Tracking Works

```
┌─────────────────────────────────────────────────────────────┐
│                      TOTAL LIMIT ($100)                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │               SESSION LIMIT ($50)                      │ │
│  │  ┌──────────────────────────────────────────────────┐ │ │
│  │  │           ITERATION LIMIT ($10)                  │ │ │
│  │  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐   │ │ │
│  │  │  │ API    │ │ API    │ │ API    │ │ API    │   │ │ │
│  │  │  │ Call 1 │ │ Call 2 │ │ Call 3 │ │ Call 4 │   │ │ │
│  │  │  └────────┘ └────────┘ └────────┘ └────────┘   │ │ │
│  │  └──────────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

1. **Iteration Cost**: Resets after each iteration (building cycle)
2. **Session Cost**: Resets when starting a new session
3. **Total Cost**: Persists across all sessions

### Setting Appropriate Limits

| Scenario | per_iteration | per_session | total |
|----------|--------------|-------------|-------|
| Experimentation | $5.0 | $25.0 | $50.0 |
| Development | $10.0 | $50.0 | $100.0 |
| Production | $20.0 | $100.0 | $500.0 |

### Monitoring Costs

Check current costs using the status command:

```bash
ralph status
```

Output includes:
```
Cost Summary:
  Current iteration: $0.45
  Current session:   $12.30
  Total (all time):  $87.50

Remaining Budget:
  Iteration: $1.55
  Session:   $37.70
  Total:     $112.50
```

### Cost Exceeded Behavior

When a limit is exceeded:

1. **Iteration Limit**: Current iteration stops, moves to next phase
2. **Session Limit**: Session ends gracefully, state is saved
3. **Total Limit**: Ralph refuses to start until limit is increased

---

## Security Configuration

Ralph includes multiple security layers to prevent unintended actions.

### Command Blocking

Block dangerous commands that should never execute:

```yaml
safety:
  blocked_commands:
    # Destructive file operations
    - "rm -rf"
    - "rm -r /"

    # Docker operations
    - "docker rm"
    - "docker rmi"

    # Package management (use uv instead)
    - "pip install"
    - "pip uninstall"

    # Virtual environment (use uv instead)
    - "python -m venv"
    - "virtualenv"

    # System commands
    - "sudo"
    - "su -"

    # Network downloads to execution
    - "curl | bash"
    - "wget | bash"
```

### Sandbox Settings

The sandbox restricts command execution:

```yaml
safety:
  # Enable sandboxing (recommended)
  sandbox_enabled: true

  # Maximum retries for failed operations
  max_retries: 3
```

When sandbox is enabled:
- Commands run in restricted environment
- File system access is limited to project directory
- Network access may be restricted
- Certain system calls are blocked

### Git Operation Restrictions

Control git operations to prevent unintended commits:

```yaml
safety:
  # Read-only mode (recommended for automation)
  git_read_only: true

  # Operations allowed in read-only mode
  allowed_git_operations:
    - "status"
    - "log"
    - "diff"
    - "show"
    - "branch"
    - "remote"
```

When `git_read_only: true`:
- No commits can be made
- No branches can be created/deleted
- No pushes or pulls
- Only listed operations are allowed

To enable write operations (for trusted environments):

```yaml
safety:
  git_read_only: false
  allowed_git_operations:
    - "status"
    - "log"
    - "diff"
    - "add"
    - "commit"
    - "branch"
    - "checkout"
    - "merge"
```

---

## Phase-Specific Configuration

Each phase of Ralph's loop can be customized independently.

### Discovery Phase

The discovery phase gathers requirements and asks clarifying questions.

```yaml
phases:
  discovery:
    # Enable human-in-loop for questions
    human_in_loop: true

    # Maximum questions before proceeding
    # Set lower for simpler tasks, higher for complex ones
    max_questions: 10
```

**When to adjust**:
- `human_in_loop: false` - For fully automated pipelines
- `max_questions: 5` - For well-defined tasks
- `max_questions: 20` - For ambiguous requirements

### Planning Phase

The planning phase breaks down tasks and analyzes dependencies.

```yaml
phases:
  planning:
    # Target token size for task chunks
    # Larger = fewer tasks, smaller = more granular
    task_size_tokens: 30000

    # Enable dependency analysis
    dependency_analysis: true
```

**When to adjust**:
- `task_size_tokens: 15000` - For simpler, more isolated changes
- `task_size_tokens: 50000` - For complex, interconnected changes
- `dependency_analysis: false` - For independent tasks

### Building Phase

The building phase implements changes iteratively.

```yaml
phases:
  building:
    # Maximum iterations per task
    max_iterations: 100

    # Commands to run after each change (backpressure)
    backpressure:
      - "uv run pytest"
      - "uv run mypy ."
      - "uv run ruff check ."
```

**Backpressure Commands**:
Backpressure commands run after each code change to ensure quality. They provide immediate feedback and prevent accumulating technical debt.

Recommended order:
1. **Fast tests** (`pytest --fast`) - Quick sanity check
2. **Type checking** (`mypy .`) - Catch type errors early
3. **Linting** (`ruff check .`) - Enforce code style
4. **Full tests** (`pytest`) - Complete verification

```yaml
# Fast feedback loop
backpressure:
  - "uv run pytest tests/unit -x"  # Stop on first failure
  - "uv run ruff check ."

# Thorough verification
backpressure:
  - "uv run pytest"
  - "uv run mypy . --strict"
  - "uv run ruff check ."
  - "uv run ruff format . --check"
```

### Validation Phase

The validation phase verifies completion and quality.

```yaml
phases:
  validation:
    # Require human approval before marking complete
    require_human_approval: true
```

**When to adjust**:
- `require_human_approval: false` - For CI/CD pipelines
- `require_human_approval: true` - For production changes

---

## Configuration Examples

### Minimal Configuration

For quick starts, only specify what differs from defaults:

```yaml
# .ralph/config.yaml
project:
  name: "my-project"

build:
  test_command: "pytest"
```

### Development Configuration

Optimized for fast iteration during development:

```yaml
# .ralph/config.yaml
# Development: Lower costs, faster feedback

project:
  name: "my-project"
  python_version: "3.13"

build:
  tool: "uv"
  test_command: "uv run pytest -x --tb=short"
  lint_command: "uv run ruff check . --fix"
  typecheck_command: "uv run mypy ."

phases:
  discovery:
    human_in_loop: true
    max_questions: 5
  planning:
    task_size_tokens: 20000
  building:
    max_iterations: 50
    backpressure:
      - "uv run pytest -x"
  validation:
    require_human_approval: false

context:
  max_progress_entries: 10

safety:
  sandbox_enabled: true
  git_read_only: false
  cost_limits:
    per_iteration: 1.0
    per_session: 20.0
    total: 100.0
```

### Production Configuration

Optimized for quality and thorough verification:

```yaml
# .ralph/config.yaml
# Production: Higher quality, thorough validation

project:
  name: "production-app"
  python_version: "3.13"

build:
  tool: "uv"
  test_command: "uv run pytest --cov=src --cov-report=term-missing"
  lint_command: "uv run ruff check ."
  typecheck_command: "uv run mypy . --strict"

phases:
  discovery:
    human_in_loop: true
    max_questions: 15
  planning:
    task_size_tokens: 40000
    dependency_analysis: true
  building:
    max_iterations: 200
    backpressure:
      - "uv run pytest"
      - "uv run mypy . --strict"
      - "uv run ruff check ."
      - "uv run ruff format . --check"
  validation:
    require_human_approval: true

context:
  max_progress_entries: 30
  max_files_in_memory: 15

safety:
  sandbox_enabled: true
  blocked_commands:
    - "rm -rf"
    - "docker rm"
    - "pip install"
    - "sudo"
    - "curl | bash"
  git_read_only: true
  allowed_git_operations:
    - "status"
    - "log"
    - "diff"
  max_retries: 5
  cost_limits:
    per_iteration: 5.0
    per_session: 100.0
    total: 500.0
```

### CI/CD Configuration

Optimized for automated pipelines:

```yaml
# .ralph/config.yaml
# CI/CD: Fully automated, strict limits

project:
  name: "ci-project"

build:
  tool: "uv"
  test_command: "uv run pytest --tb=short"
  lint_command: "uv run ruff check ."
  typecheck_command: "uv run mypy ."

phases:
  discovery:
    human_in_loop: false  # No human interaction
    max_questions: 0
  planning:
    task_size_tokens: 25000
  building:
    max_iterations: 30    # Limited iterations
    backpressure:
      - "uv run pytest -x"
      - "uv run ruff check ."
  validation:
    require_human_approval: false  # Auto-approve

safety:
  sandbox_enabled: true
  git_read_only: true
  max_retries: 2
  cost_limits:
    per_iteration: 1.0
    per_session: 15.0
    total: 50.0
```

---

## Validation Rules

Ralph validates configuration on load. Common validation errors:

| Error | Cause | Solution |
|-------|-------|----------|
| `Invalid cost limit` | Negative value | Use positive numbers |
| `Unknown build tool` | Unsupported tool name | Use `uv`, `pip`, or `poetry` |
| `YAML parse error` | Malformed YAML | Check indentation and syntax |

---

## Tips and Best Practices

1. **Start with defaults**: Only override what you need
2. **Use environment variables for secrets**: Never put API keys in config files
3. **Set conservative cost limits**: Start low, increase as needed
4. **Enable sandbox in production**: Adds safety layer for automated runs
5. **Customize backpressure**: Match your project's test/lint setup
6. **Use git read-only**: Prevent unintended commits in automation
7. **Monitor costs regularly**: Use `ralph status` to track spending
8. **Version control your config**: Keep `.ralph/config.yaml` in git
