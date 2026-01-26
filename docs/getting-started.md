# Getting Started with Ralph

Ralph is a deterministic agentic coding loop that uses the Claude Agent SDK to break down development work into discrete, trackable tasks and execute them iteratively. This guide will walk you through installing Ralph, initializing it in a project, and running your first workflow.

## Prerequisites

Before installing Ralph, ensure you have the following:

### Python 3.11+

Ralph requires Python 3.11 or later. Check your Python version:

```bash
python --version
# or
python3 --version
```

If you need to install or upgrade Python, visit [python.org](https://www.python.org/downloads/) or use a version manager like pyenv.

### uv Package Manager

Ralph uses `uv` for all Python dependency management and command execution. Install uv if you don't have it:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or via pip
pip install uv
```

Verify the installation:

```bash
uv --version
```

### Authentication

Ralph requires access to the Claude API. You have two options:

**Option 1: Anthropic API Key**

Set the `ANTHROPIC_API_KEY` environment variable:

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

> **Tip:** Add this line to your `.bashrc`, `.zshrc`, or `.env` file for persistence.

**Option 2: Claude Code CLI Authentication**

If you have Claude Code installed and are logged in with your Anthropic subscription, Ralph can authenticate automatically through the local Claude Code instance. No API key configuration is required.

---

## Installation

You have two installation options: run directly without cloning (recommended for users) or clone for development.

### Option 1: Run Directly with uvx (Recommended)

`uvx` lets you run Ralph directly from GitHub without cloning or installing. This is the fastest way to get started:

```bash
# Run directly from GitHub
uvx --from git+https://github.com/CipherScout/Ralph ralph-agent --help

# Run with a specific version/tag
uvx --from git+https://github.com/CipherScout/Ralph@v0.1.0 ralph-agent --help
```

For repeated use, install Ralph globally as a tool:

```bash
# Install globally (creates isolated environment automatically)
uv tool install git+https://github.com/CipherScout/Ralph

# Now run without uvx prefix
ralph-agent --help
ralph-agent version
```

> **Note:** When installed globally, Ralph's commands are available directly as `ralph-agent` without any prefix.

### Option 2: Clone and Install (For Development)

If you want to contribute to Ralph or need to modify the code:

#### 1. Clone the Repository

```bash
git clone https://github.com/CipherScout/Ralph.git
cd Ralph
```

#### 2. Install Dependencies

Use uv to install Ralph with all development dependencies:

```bash
uv sync --extra dev
```

This installs:
- Core dependencies (claude-agent-sdk, rich, typer, pydantic, etc.)
- Development tools (pytest, ruff, mypy)

#### 3. Verify Installation

Confirm Ralph is installed correctly:

```bash
ralph-agent version
```

Expected output:

```
Ralph v0.1.0
```

You can also check available commands:

```bash
ralph-agent --help
```

### Command Convention

Throughout this guide and the documentation:

| Installation Method | How to Run Commands |
|--------------------|---------------------|
| Global install (`uv tool install`) | `ralph-agent <command>` |
| Local clone (`uv sync`) | `uv run ralph-agent <command>` |
| Direct run (`uvx`) | `uvx --from git+... ralph-agent <command>` |

> **Note:** The examples below use `ralph-agent` directly. If you cloned the repo locally instead of installing globally, prefix all commands with `uv run`.

---

## Your First Ralph Session

Let's walk through initializing Ralph in a project directory.

### Step 1: Navigate to Your Project

Ralph can be initialized in any project directory. For this guide, we'll create a sample project:

```bash
mkdir my-project
cd my-project
git init  # Ralph works best with git-tracked projects
```

### Step 2: Initialize Ralph

Run the init command:

```bash
ralph-agent init
```

Expected output:

```
Initializing Ralph in /path/to/my-project...
✓ Created .ralph/state.json
✓ Created .ralph/implementation_plan.json
Ralph initialized successfully!

Current phase: building
Tasks in plan: 0
```

### What Gets Created

After initialization, your project will have the following new files:

```
my-project/
├── .ralph/
│   ├── state.json              # Master state (phase, iteration, costs)
│   ├── implementation_plan.json # Task list with dependencies
│   └── session_history/        # Context handoff records (created later)
├── specs/                      # Created during Discovery phase
└── progress.txt               # Operational learnings log (created during execution)
```

**`.ralph/state.json`** - Tracks the current execution state:
- Current workflow phase
- Iteration count
- Cost tracking (tokens and USD)
- Circuit breaker status
- Context budget usage

**`.ralph/implementation_plan.json`** - Contains the task list:
- Prioritized tasks with dependencies
- Task statuses (pending, in_progress, complete, blocked)
- Verification criteria for each task

### Step 3: Check Status

Verify Ralph is ready:

```bash
ralph-agent status
```

Expected output:

```
╭─────────────────── Ralph Status ───────────────────╮
│ Phase: building                                     │
│ Iteration: 0                                        │
│ Session ID: None                                    │
│ Started: 2024-01-15 10:30:00                       │
│ Last Activity: 2024-01-15 10:30:00                 │
╰────────────────────────────────────────────────────╯
╭─────────────────── Cost Tracking ──────────────────╮
│ Total Cost: $0.0000                                │
│ Total Tokens: 0                                    │
│ Session Cost: $0.0000                              │
│ Session Tokens: 0                                  │
╰────────────────────────────────────────────────────╯
╭─────────────────── Circuit Breaker ────────────────╮
│ State: closed                                      │
│ Failure Count: 0/3                                 │
│ Stagnation Count: 0/5                              │
│ Cost Used: $0.00/$100.00                           │
╰────────────────────────────────────────────────────╯
╭─────────────────── Context Budget ─────────────────╮
│ Usage: 0.0% (0/200,000)                            │
│ Smart Zone Max: 120,000 (60%)                      │
│ Available: 160,000                                 │
│ Should Handoff: No                                 │
╰────────────────────────────────────────────────────╯
```

---

## Running Your First Workflow

Ralph operates in four phases: **Discovery**, **Planning**, **Building**, and **Validation**. Let's walk through a complete workflow with a simple example.

### Example Goal: "Add a hello world endpoint"

We'll use this goal to demonstrate each phase.

### Phase 1: Discovery

The Discovery phase uses the Jobs-to-be-Done (JTBD) framework to gather requirements. Start it with:

```bash
ralph-agent discover --goal "Add a hello world REST endpoint that returns a JSON greeting"
```

**What happens:**
1. Ralph analyzes your project structure
2. It may ask clarifying questions about your requirements
3. It creates specification files in the `specs/` directory

Expected output:

```
╭──────────────── Discovery Phase ────────────────╮
│                                                  │
╰──────────────────────────────────────────────────╯
Goal: Add a hello world REST endpoint that returns a JSON greeting
Discovery complete!
Created specs: hello-world-endpoint.md
```

After discovery, check the created spec:

```bash
ls specs/
cat specs/hello-world-endpoint.md
```

### Phase 2: Planning

The Planning phase analyzes your specs and codebase to create an implementation plan with sized, prioritized tasks:

```bash
ralph-agent plan
```

**What happens:**
1. Ralph reads the specs from Discovery
2. It performs gap analysis against your existing code
3. It creates tasks sized for single context windows (~30 minutes of work each)

Expected output:

```
╭──────────────── Planning Phase ────────────────╮
│                                                 │
╰─────────────────────────────────────────────────╯
Planning complete!
Created 4 tasks
```

View the created tasks:

```bash
ralph-agent tasks --all
```

Expected output:

```
                          Tasks
┏━━━━━━━━━━━━━━━━━━━┳━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┓
┃ ID                ┃ Pri ┃ Status  ┃ Description            ┃ Deps ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━┩
│ task-001          │ 1   │ pending │ Set up FastAPI project │ -    │
│ task-002          │ 2   │ pending │ Create hello endpoint  │ 1    │
│ task-003          │ 3   │ pending │ Add unit tests         │ 2    │
│ task-004          │ 4   │ pending │ Add documentation      │ 3    │
└───────────────────┴─────┴─────────┴────────────────────────┴──────┘

Total: 4 | Complete: 0 | Pending: 4 | Completion: 0.0%

Next task: Set up FastAPI project structure
```

### Phase 3: Building

The Building phase iteratively executes tasks using a TDD approach:

```bash
ralph-agent build
```

**What happens for each task:**
1. Ralph marks the task as "in progress"
2. Writes failing tests first
3. Implements the feature to make tests pass
4. Marks the task as complete
5. Moves to the next available task

Expected output:

```
╭──────────────── Building Phase ────────────────╮
│                                                 │
╰─────────────────────────────────────────────────╯

Iteration 1 (building) - 0.0% context used
  SUCCESS - $0.0234 (15,432 tokens)
  Task completed: task-001

Iteration 2 (building) - 12.3% context used
  SUCCESS - $0.0189 (12,891 tokens)
  Task completed: task-002

...

Building complete!
Completed 4 tasks in 4 iterations
```

> **Note:** During building, Ralph enforces safety controls:
> - Git is read-only (no commits, pushes, etc.)
> - Package installation goes through uv only
> - Circuit breaker monitors for failures and stagnation

### Phase 4: Validation

The Validation phase verifies that your implementation meets requirements:

```bash
ralph-agent validate
```

**What happens:**
1. Runs all tests
2. Performs linting with ruff
3. Runs type checking with mypy
4. Verifies spec compliance

Expected output:

```
╭──────────────── Validation Phase ────────────────╮
│                                                   │
╰───────────────────────────────────────────────────╯
Validation complete!
All checks passed
```

### Running the Full Workflow

Instead of running phases individually, you can run the entire workflow:

```bash
ralph-agent run --goal "Add a hello world REST endpoint"
```

This runs Discovery, Planning, Building, and Validation in sequence.

---

## Monitoring Progress

### Check Status Anytime

```bash
ralph-agent status
```

For detailed information including the task list:

```bash
ralph-agent status --verbose
```

### View Tasks

Show pending and in-progress tasks:

```bash
ralph-agent tasks
```

Show only pending tasks:

```bash
ralph-agent tasks --pending
```

Show all tasks including completed:

```bash
ralph-agent tasks --all
```

### View Session History

See past sessions, costs, and handoff reasons:

```bash
ralph-agent history
```

Expected output:

```
                          Session History
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┓
┃ Session ID     ┃ Phase   ┃ Iterations ┃ Cost    ┃ Reason             ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━┩
│ abc123def...   │ building│ 12         │ $0.1234 │ context_limit      │
│ 789xyz012...   │ building│ 8          │ $0.0891 │ phase_complete     │
└────────────────┴─────────┴────────────┴─────────┴────────────────────┘
```

---

## Understanding the Output

### Status Panel

The status command shows several information panels:

| Panel | Description |
|-------|-------------|
| **Ralph Status** | Current phase, iteration count, session info |
| **Cost Tracking** | Total and session-level token/cost usage |
| **Circuit Breaker** | Failure/stagnation monitoring state |
| **Context Budget** | Token usage and handoff status |

### Task Status Values

| Status | Meaning |
|--------|---------|
| `pending` | Task waiting to be started |
| `in_progress` | Task currently being worked on |
| `complete` | Task finished successfully |
| `blocked` | Task cannot proceed (manual intervention needed) |

### Circuit Breaker States

| State | Meaning |
|-------|---------|
| `closed` | Normal operation |
| `open` | Halted due to failures (needs recovery) |
| `half_open` | Testing recovery after being open |

---

## Common Commands Reference

```bash
# Initialize Ralph in current directory
ralph-agent init

# Check current status
ralph-agent status

# Run full workflow
ralph-agent run --goal "your feature description"

# Run individual phases
ralph-agent discover --goal "description"
ralph-agent plan
ralph-agent build
ralph-agent validate

# Task management
ralph-agent tasks              # Show pending tasks
ralph-agent tasks --all        # Show all tasks
ralph-agent skip TASK_ID       # Skip a problematic task

# Control the loop
ralph-agent pause              # Pause after current iteration
ralph-agent resume             # Resume paused loop
ralph-agent inject "message"   # Add guidance for next iteration

# Reset state
ralph-agent reset              # Full reset
ralph-agent reset --keep-plan  # Reset but keep task list
```

---

## Next Steps

Now that you understand the basics, explore these resources to learn more:

- **[Core Concepts](./core-concepts.md)** - Deep dive into Ralph's four-phase workflow, deterministic task selection, and context management
- **[CLI Reference](./cli-reference.md)** - Complete documentation of all commands and options
- **[Configuration](./configuration.md)** - Customize Ralph with `ralph.yml` settings
- **[Error Recovery](./error-recovery.md)** - Handle circuit breaker trips, stagnation, and other issues
- **[MCP Tools](./mcp-tools.md)** - Understanding the tools Ralph exposes for state management

---

## Getting Help

If you encounter issues:

1. Check status: `ralph-agent status --verbose`
2. Review session history: `ralph-agent history`
3. Check the `progress.txt` file for operational learnings
4. Reset if needed: `ralph-agent reset`

For bugs or feature requests, please open an issue on GitHub.
