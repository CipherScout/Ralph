# Troubleshooting Guide

This guide provides solutions for common issues encountered when using Ralph. Each section covers specific error categories with symptoms, causes, solutions, and prevention strategies.

## Table of Contents

- [Installation Issues](#installation-issues)
- [Authentication Issues](#authentication-issues)
- [Initialization Issues](#initialization-issues)
- [Runtime Issues](#runtime-issues)
- [Phase-Specific Issues](#phase-specific-issues)
- [State and Persistence Issues](#state-and-persistence-issues)
- [CLI Issues](#cli-issues)
- [Recovery Procedures](#recovery-procedures)
- [Diagnostic Commands Reference](#diagnostic-commands-reference)

---

## Installation Issues

### Python Version Errors

#### Symptoms
```
ERROR: Requires-Python >=3.11 not satisfied
```
or
```
SyntaxError: invalid syntax
```
when running Ralph commands.

#### Cause
Ralph requires Python 3.11 or later. Earlier versions lack required language features and type annotations.

#### Solution
1. Check your Python version:
   ```bash
   python --version
   # or
   python3 --version
   ```

2. Install Python 3.11+ using your package manager:
   ```bash
   # macOS with Homebrew
   brew install python@3.11

   # Ubuntu/Debian
   sudo apt update && sudo apt install python3.11

   # Windows with winget
   winget install Python.Python.3.11
   ```

3. If using pyenv:
   ```bash
   pyenv install 3.11.8
   pyenv local 3.11.8
   ```

4. Verify uv is using the correct Python:
   ```bash
   uv python list
   uv python pin 3.11
   ```

#### Prevention
- Always check Python version requirements before installation
- Use `uv python pin` to lock the Python version for the project

---

### uv Installation Problems

#### Symptoms
```
command not found: uv
```
or
```
error: no such command: 'sync'
```

#### Cause
uv is not installed or not in the system PATH.

#### Solution
1. Install uv:
   ```bash
   # macOS/Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # Windows (PowerShell)
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

   # Using pip (fallback)
   pip install uv
   ```

2. Verify installation:
   ```bash
   uv --version
   ```

3. If uv is installed but not found, add to PATH:
   ```bash
   # Add to ~/.bashrc or ~/.zshrc
   export PATH="$HOME/.cargo/bin:$PATH"
   ```

4. Restart your terminal or source the config:
   ```bash
   source ~/.zshrc  # or ~/.bashrc
   ```

#### Prevention
- Use the official installation script
- Ensure PATH is configured correctly in your shell profile

---

### Dependency Conflicts

#### Symptoms
```
error: package `foo` requires `bar>=2.0` but `bar==1.5` is installed
```
or
```
ResolutionImpossible: Unable to find compatible versions
```

#### Cause
Conflicting package versions in the project environment or system packages interfering.

#### Solution
1. Create a fresh virtual environment:
   ```bash
   rm -rf .venv
   uv venv
   ```

2. Reinstall dependencies:
   ```bash
   uv sync --extra dev
   ```

3. If conflicts persist, check for version constraints:
   ```bash
   uv pip compile pyproject.toml -o requirements.txt --verbose
   ```

4. Update conflicting packages:
   ```bash
   uv add --upgrade package-name
   ```

#### Prevention
- Avoid installing packages globally
- Use `uv sync` instead of `pip install` for consistent environments
- Regularly update dependencies with `uv sync --upgrade`

---

### Missing claude-agent-sdk

#### Symptoms
```
ModuleNotFoundError: No module named 'claude_agent_sdk'
```
or
```
ImportError: cannot import name 'ClaudeSDKClient' from 'claude_agent_sdk'
```

#### Cause
The Claude Agent SDK is not installed or is an incompatible version.

#### Solution
1. Verify the package is listed in dependencies:
   ```bash
   grep claude-agent-sdk pyproject.toml
   ```

2. Install/reinstall dependencies:
   ```bash
   uv sync --extra dev
   ```

3. Check the installed version:
   ```bash
   uv pip show claude-agent-sdk
   ```

4. If version is incompatible, update:
   ```bash
   uv add "claude-agent-sdk>=0.1.21"
   ```

5. Verify the import works:
   ```bash
   uv run python -c "from claude_agent_sdk import ClaudeSDKClient; print('OK')"
   ```

#### Prevention
- Pin minimum SDK version in `pyproject.toml`
- Run `uv sync` after pulling updates

---

## Authentication Issues

### ANTHROPIC_API_KEY Not Set

#### Symptoms
```
Error: ANTHROPIC_API_KEY environment variable not set
```
or
```
AuthenticationError: No API key provided
```

#### Cause
The Anthropic API key is not configured in the environment.

#### Solution
1. Set the environment variable:
   ```bash
   # Temporary (current session)
   export ANTHROPIC_API_KEY="sk-ant-..."

   # Permanent (add to shell profile)
   echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.zshrc
   ```

2. For project-specific configuration, use a `.env` file:
   ```bash
   # Create .env in project root (DO NOT commit this file)
   echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env
   ```

3. Alternatively, use Claude Code CLI authentication (no API key needed):
   ```bash
   # Login to Claude Code
   claude login

   # Verify authentication
   claude --version
   ```

#### Prevention
- Use a `.env` file for local development (add to `.gitignore`)
- Consider using Claude Code CLI authentication to avoid managing API keys
- Use secret managers in production environments

---

### Invalid API Key

#### Symptoms
```
AuthenticationError: Invalid API key
```
or
```
401 Unauthorized: The API key provided is invalid
```

#### Cause
The API key is malformed, expired, or belongs to a different organization.

#### Solution
1. Verify the key format (should start with `sk-ant-`):
   ```bash
   echo $ANTHROPIC_API_KEY | head -c 10
   # Should output: sk-ant-...
   ```

2. Check for accidental whitespace:
   ```bash
   echo "[$ANTHROPIC_API_KEY]" | cat -A
   # Look for trailing spaces or newlines
   ```

3. Generate a new key at [console.anthropic.com](https://console.anthropic.com/settings/keys)

4. Update the environment variable with the new key

5. Test the key:
   ```bash
   curl https://api.anthropic.com/v1/messages \
     -H "x-api-key: $ANTHROPIC_API_KEY" \
     -H "anthropic-version: 2023-06-01" \
     -H "content-type: application/json" \
     -d '{"model":"claude-sonnet-4-20250514","max_tokens":10,"messages":[{"role":"user","content":"Hi"}]}'
   ```

#### Prevention
- Store API keys securely
- Rotate keys periodically
- Use Claude Code CLI authentication when possible

---

### Rate Limiting

#### Symptoms
```
RateLimitError: Rate limit exceeded
```
or
```
429 Too Many Requests
```
or iterations becoming very slow.

#### Cause
Too many API requests in a short period, exceeding your account's rate limits.

#### Solution
1. Check current rate limit status:
   ```bash
   uv run ralph-agent status --verbose
   # Review iteration frequency and costs
   ```

2. Wait and retry (rate limits typically reset after 60 seconds):
   ```bash
   # Pause Ralph
   uv run ralph-agent pause

   # Wait 1-2 minutes
   sleep 120

   # Resume
   uv run ralph-agent resume
   ```

3. If persistent, contact Anthropic to increase rate limits

#### Prevention
- Monitor costs and iteration counts regularly
- Use context handoffs to reduce API calls
- Configure appropriate cost limits in `ralph.yml`

---

### Claude Code CLI Authentication Problems

#### Symptoms
```
Error: Not logged in to Claude Code
```
or
```
Error: Claude Code CLI not found
```

#### Cause
Claude Code CLI is not installed, not logged in, or the session has expired.

#### Solution
1. Verify Claude Code is installed:
   ```bash
   claude --version
   ```

2. If not installed, follow the [Claude Code installation guide](https://docs.anthropic.com/claude-code/installation)

3. Login to Claude Code:
   ```bash
   claude login
   ```

4. Verify authentication:
   ```bash
   claude auth status
   ```

5. If session expired, re-login:
   ```bash
   claude logout
   claude login
   ```

#### Prevention
- Check authentication status before long-running sessions
- Consider using API key authentication for automated workflows

---

## Initialization Issues

### Ralph Already Initialized

#### Symptoms
```
Ralph already initialized in /path/to/project
Use --force to reinitialize
```

#### Cause
A `.ralph/` directory already exists in the project.

#### Solution
1. If you want to keep existing state, skip initialization:
   ```bash
   uv run ralph-agent status
   ```

2. To reinitialize (warning: resets all state):
   ```bash
   uv run ralph-agent init --force
   ```

3. To preserve the plan but reset state:
   ```bash
   uv run ralph-agent reset --keep-plan
   ```

#### Prevention
- Run `ralph-agent status` before `init` to check existing state
- Use `--force` only when you intentionally want to start fresh

---

### Permission Errors Creating .ralph/

#### Symptoms
```
PermissionError: [Errno 13] Permission denied: '.ralph'
```
or
```
OSError: [Errno 30] Read-only file system
```

#### Cause
Insufficient permissions to create directories in the project root.

#### Solution
1. Check directory permissions:
   ```bash
   ls -la /path/to/project
   ```

2. Fix ownership if needed:
   ```bash
   sudo chown -R $(whoami) /path/to/project
   ```

3. Fix permissions:
   ```bash
   chmod 755 /path/to/project
   ```

4. If on a read-only filesystem (like some network mounts), copy the project locally:
   ```bash
   cp -r /network/path/project ~/local/project
   cd ~/local/project
   uv run ralph-agent init
   ```

#### Prevention
- Ensure you have write access to the project directory
- Avoid running Ralph on network filesystems or read-only mounts

---

### Invalid Project Directory

#### Symptoms
```
Error: Directory does not exist: /path/to/project
```
or
```
Error: Not a directory: /path/to/file
```

#### Cause
The specified project path does not exist or is not a directory.

#### Solution
1. Verify the path exists:
   ```bash
   ls -la /path/to/project
   ```

2. Create the directory if needed:
   ```bash
   mkdir -p /path/to/project
   ```

3. Use the correct path:
   ```bash
   # Use current directory
   uv run ralph-agent init

   # Or specify explicitly
   uv run ralph-agent init --project-root /correct/path
   ```

4. Check for typos in the path

#### Prevention
- Use tab completion for paths
- Run commands from within the project directory when possible

---

## Runtime Issues

### Circuit Breaker Opens (Consecutive Failures)

#### Symptoms
```
Loop halted: consecutive_failures:3
```
or
```
Circuit breaker state: open
```

#### Cause
Three or more consecutive iterations failed without completing a task. This is a safety mechanism to prevent runaway failures and wasted resources.

#### Solution
1. Diagnose the failure:
   ```bash
   uv run ralph-agent status --verbose
   ```

2. Check the last failure reason:
   ```bash
   uv run ralph-agent status --verbose | grep "Last Failure"
   ```

3. Review the current task:
   ```bash
   uv run ralph-agent tasks --all
   ```

4. Option A - Skip the problematic task:
   ```bash
   uv run ralph-agent skip TASK_ID --reason "Requires manual intervention"
   ```

5. Option B - Inject guidance and retry:
   ```bash
   uv run ralph-agent inject "The previous attempts failed because X. Try approach Y instead." --priority 1
   ```

6. Reset the circuit breaker and resume:
   ```bash
   uv run ralph-agent resume
   ```

#### Prevention
- Size tasks appropriately (aim for ~30 minutes of work each)
- Include clear verification criteria in task definitions
- Use the `inject` command to provide context when tasks are complex

---

### Stagnation Detected

#### Symptoms
```
Loop halted: stagnation:5
```
or status showing high stagnation count without task completions.

#### Cause
Five or more iterations completed without making progress (no tasks completed). The agent may be stuck on a task that is too large or poorly defined.

#### Solution
1. Check which task is causing issues:
   ```bash
   uv run ralph-agent tasks --all
   ```

2. Review what the agent has been doing:
   ```bash
   cat progress.txt | tail -30
   ```

3. Option A - Regenerate the plan with better task breakdown:
   ```bash
   uv run ralph-agent regenerate-plan
   uv run ralph-agent plan
   uv run ralph-agent run
   ```

4. Option B - Skip the stuck task:
   ```bash
   uv run ralph-agent skip TASK_ID --reason "Task too complex, needs manual breakdown"
   ```

5. Option C - Inject clarifying context:
   ```bash
   uv run ralph-agent inject "Focus on completing the current task. The main blocker is..." --priority 1
   uv run ralph-agent resume
   ```

#### Prevention
- Break down large tasks during planning
- Set clear verification criteria for each task
- Review and refine specs before planning phase

---

### Cost Limit Exceeded

#### Symptoms
```
Loop halted: cost_limit:$50.00
```
or
```
Error: Total cost exceeded limit
```

#### Cause
The total cost of API calls has exceeded the configured limit.

#### Solution
1. Review current spending:
   ```bash
   uv run ralph-agent status --verbose
   ```
   Look for "Total Cost" and "Session Cost" values.

2. If the limit is appropriate, increase it in configuration:
   ```yaml
   # ralph.yml (project root) or .ralph/config.yaml
   cost_limits:
     per_iteration: 10.0
     per_session: 50.0
     total: 100.0
   ```

3. Reset state if you want to continue with a new budget:
   ```bash
   uv run ralph-agent reset --keep-plan
   ```

4. Resume:
   ```bash
   uv run ralph-agent resume
   ```

#### Prevention
- Set realistic cost limits based on project scope
- Monitor spending with `ralph-agent status --verbose`
- Use smaller models (claude-sonnet vs claude-opus) for routine tasks

---

### Context Handoff Problems

#### Symptoms
```
Handoff failed: Could not write MEMORY.md
```
or tasks not resuming properly after handoff.

#### Cause
Failure to write session state files or corrupted handoff data.

#### Solution
1. Check MEMORY.md exists and is readable:
   ```bash
   cat MEMORY.md
   ```

2. Check session history:
   ```bash
   ls -la .ralph/session_history/
   cat .ralph/session_history/sessions.jsonl | tail -5
   ```

3. If MEMORY.md is missing or corrupted, trigger manual handoff:
   ```bash
   uv run ralph-agent handoff --reason "manual recovery" --summary "Previous session was working on..."
   ```

4. Clear corrupted injections:
   ```bash
   rm -f .ralph/injections.json
   ```

5. Resume:
   ```bash
   uv run ralph-agent resume
   ```

#### Prevention
- Ensure sufficient disk space for state files
- Do not manually edit `.ralph/` files
- Use `ralph-agent handoff` for manual context resets

---

### Task Stuck in IN_PROGRESS

#### Symptoms
A task shows `in_progress` status but no work is happening, or:
```
No pending tasks available (task may be stuck in_progress)
```

#### Cause
The previous session crashed or was terminated while a task was in progress. Ralph normally resets stale IN_PROGRESS tasks at session start, but this can fail.

#### Solution
1. Check task status:
   ```bash
   uv run ralph-agent tasks --all
   ```

2. Identify stuck tasks (status shows `in_progress`).

3. Reset the task manually by editing the plan or using:
   ```bash
   # Skip and recreate similar task
   uv run ralph-agent skip TASK_ID --reason "Stuck from previous session"
   ```

4. Or reset all state:
   ```bash
   uv run ralph-agent reset --keep-plan
   ```

5. Start a new session - Ralph automatically resets stale tasks:
   ```bash
   uv run ralph-agent run
   ```

#### Prevention
- Allow Ralph to complete iterations gracefully
- Use `ralph-agent pause` instead of killing the process
- Ralph automatically resets IN_PROGRESS tasks at session start

---

## Phase-Specific Issues

### Discovery: No Specs Created

#### Symptoms
After running discovery phase:
```
Created specs: (empty)
```
or no files in `specs/` directory.

#### Cause
The discovery phase did not produce spec files, possibly due to:
- Insufficient user interaction
- No goal provided
- Early termination

#### Solution
1. Check if specs directory exists:
   ```bash
   ls -la specs/
   ```

2. Provide a clear goal and re-run discovery:
   ```bash
   uv run ralph-agent discover --goal "Build a REST API for user authentication with JWT tokens"
   ```

3. Ensure you answer the JTBD questions when prompted

4. Create specs manually if needed:
   ```bash
   mkdir -p specs
   cat > specs/feature-auth.md << 'EOF'
   # User Authentication Feature

   ## Job to be Done
   When a user wants to access protected resources, they need to authenticate.

   ## Requirements
   - JWT-based authentication
   - Login/logout endpoints
   - Token refresh capability

   ## Acceptance Criteria
   - Users can register with email/password
   - Users can login and receive JWT
   - Protected routes reject unauthenticated requests
   EOF
   ```

5. Proceed to planning:
   ```bash
   uv run ralph-agent plan
   ```

#### Prevention
- Always provide a clear, specific goal
- Engage with the JTBD questions
- Review generated specs before proceeding to planning

---

### Planning: Empty Plan Generated

#### Symptoms
```
Created 0 tasks in plan
```
or `ralph-agent tasks` shows no tasks.

#### Cause
Planning phase did not create tasks, possibly due to:
- No specs to analyze
- Specs too vague
- Planning phase terminated early

#### Solution
1. Verify specs exist:
   ```bash
   ls -la specs/
   cat specs/*.md
   ```

2. If specs are missing, run discovery first:
   ```bash
   uv run ralph-agent discover --goal "Your goal here"
   ```

3. If specs exist but are vague, enhance them with more detail

4. Re-run planning:
   ```bash
   uv run ralph-agent plan
   ```

5. Check if tasks were created:
   ```bash
   uv run ralph-agent tasks --all
   ```

6. If still empty, add tasks manually via inject:
   ```bash
   uv run ralph-agent inject "Create the following tasks: 1. Set up project structure, 2. Implement core feature X, 3. Add tests" --priority 1
   uv run ralph-agent plan
   ```

#### Prevention
- Write detailed specs with clear requirements
- Include acceptance criteria in specs
- Review planning output before proceeding

---

### Building: Tests Always Fail

#### Symptoms
Tasks repeatedly fail with test failures:
```
pytest: 5 failed, 0 passed
```
or circuit breaker trips due to test failures.

#### Cause
- Tests have bugs
- Implementation has bugs
- Test environment not configured
- Missing dependencies

#### Solution
1. Run tests manually to see detailed output:
   ```bash
   uv run pytest -v --tb=long
   ```

2. Check for environment issues:
   ```bash
   uv run pytest --collect-only
   ```

3. Fix obvious test setup issues (imports, fixtures)

4. Inject guidance about the test failures:
   ```bash
   uv run ralph-agent inject "The tests are failing because of X. Focus on fixing Y first." --priority 1
   ```

5. If tests are fundamentally broken, skip the task and fix manually:
   ```bash
   uv run ralph-agent skip TASK_ID --reason "Tests need manual review"
   ```

6. Consider adding the test command output to context:
   ```bash
   uv run pytest 2>&1 | head -100 > test_output.txt
   uv run ralph-agent inject "$(cat test_output.txt)" --priority 1
   ```

#### Prevention
- Write tests incrementally during task implementation
- Use TDD approach (write failing test first)
- Keep tasks small and testable

---

### Validation: Lint/Type Errors Blocking Completion

#### Symptoms
```
Validation incomplete: ruff check failed
```
or
```
mypy: Found 15 errors
```

#### Cause
Code quality issues preventing validation phase completion.

#### Solution
1. Run linting manually:
   ```bash
   uv run ruff check . --show-fixes
   ```

2. Auto-fix simple issues:
   ```bash
   uv run ruff check . --fix
   ```

3. Run type checking:
   ```bash
   uv run mypy . --show-error-codes
   ```

4. Common fixes:
   ```bash
   # Format code
   uv run ruff format .

   # Sort imports
   uv run ruff check . --select I --fix
   ```

5. For persistent type errors, add targeted ignores:
   ```python
   # For specific lines
   result = some_dynamic_call()  # type: ignore[return-value]
   ```

6. If validation keeps failing, inject guidance:
   ```bash
   uv run ralph-agent inject "Focus on fixing the mypy errors in src/ralph/models.py first" --priority 1
   ```

#### Prevention
- Run linting during development (`uv run ruff check .`)
- Configure editor to show lint/type errors
- Address issues incrementally, not all at once

---

## State and Persistence Issues

### Corrupted state.json

#### Symptoms
```
CorruptedStateError: Invalid JSON in state file
```
or
```
Error loading state: Invalid state data
```

#### Cause
The state file has been corrupted, possibly due to:
- Interrupted write operation
- Manual editing with syntax errors
- Disk issues

#### Solution
1. Backup the current state:
   ```bash
   cp .ralph/state.json .ralph/state.json.backup
   ```

2. Try to view the file and identify issues:
   ```bash
   cat .ralph/state.json | python -m json.tool
   ```

3. If the file is completely corrupted, reinitialize:
   ```bash
   uv run ralph-agent init --force
   ```

4. If you want to preserve the plan:
   ```bash
   # Backup plan
   cp .ralph/implementation_plan.json .ralph/plan_backup.json

   # Reinitialize
   uv run ralph-agent init --force

   # Restore plan
   cp .ralph/plan_backup.json .ralph/implementation_plan.json
   ```

5. To recover specific values from backup:
   ```bash
   # View backup
   cat .ralph/state.json.backup | python -m json.tool
   ```

#### Prevention
- Do not manually edit `.ralph/` files
- Ensure sufficient disk space
- Ralph uses atomic writes to prevent corruption; if it happens, investigate disk health

---

### Missing implementation_plan.json

#### Symptoms
```
StateNotFoundError: Plan file not found
```
or
```
No implementation plan found
```

#### Cause
The plan file was deleted, never created, or the path is wrong.

#### Solution
1. Check if the file exists:
   ```bash
   ls -la .ralph/implementation_plan.json
   ```

2. If missing, initialize a new plan:
   ```bash
   uv run ralph-agent init --force
   ```

3. Or regenerate from specs:
   ```bash
   # This creates an empty plan then runs planning
   uv run ralph-agent regenerate-plan
   uv run ralph-agent plan
   ```

4. If the file exists but is in the wrong location, ensure you're in the project root:
   ```bash
   pwd
   ls -la .ralph/
   ```

#### Prevention
- Run `ralph-agent init` before other commands
- Do not delete `.ralph/` contents manually
- Use `ralph-agent reset` instead of deleting files

---

### State Not Syncing Between Iterations

#### Symptoms
Progress not being saved, tasks reverting to previous status, or:
```
Task marked complete but shows pending after restart
```

#### Cause
State not being saved properly, possibly due to:
- Permission issues
- Disk full
- Process terminated before save

#### Solution
1. Check state is saving:
   ```bash
   # Make a change
   uv run ralph-agent inject "test message"

   # Check injections saved
   cat .ralph/injections.json
   ```

2. Check disk space:
   ```bash
   df -h .
   ```

3. Check file permissions:
   ```bash
   ls -la .ralph/
   ```

4. Force save state:
   ```bash
   uv run ralph-agent status  # This loads and displays state
   ```

5. If state is corrupted, reset:
   ```bash
   uv run ralph-agent reset --keep-plan
   ```

#### Prevention
- Ensure sufficient disk space
- Do not kill Ralph process abruptly (use `ralph-agent pause`)
- Check permissions on `.ralph/` directory

---

## CLI Issues

### Command Not Found

#### Symptoms
```
command not found: ralph-agent
```
or
```
zsh: command not found: ralph-agent
```

#### Cause
The `ralph-agent` command is not in PATH, or the package is not installed correctly.

#### Solution
1. Use `uv run` prefix:
   ```bash
   uv run ralph-agent status
   ```

2. Or install the package:
   ```bash
   uv pip install -e .
   ```

3. Check if the entry point is defined:
   ```bash
   grep "ralph-agent" pyproject.toml
   ```

4. Verify the virtual environment is active:
   ```bash
   which python
   # Should show .venv/bin/python
   ```

5. Activate the virtual environment:
   ```bash
   source .venv/bin/activate
   ralph-agent status
   ```

#### Prevention
- Always use `uv run ralph-agent` for consistency
- Ensure virtual environment is activated when using direct commands

---

### Unexpected Output

#### Symptoms
Commands produce unexpected output, garbled text, or incorrect formatting.

#### Cause
- Terminal encoding issues
- Incompatible terminal
- Rich library display issues

#### Solution
1. Check terminal encoding:
   ```bash
   echo $LANG
   # Should be something like en_US.UTF-8
   ```

2. Set proper encoding:
   ```bash
   export LANG=en_US.UTF-8
   export LC_ALL=en_US.UTF-8
   ```

3. Try a simpler output format:
   ```bash
   # Redirect to file to avoid terminal formatting
   uv run ralph-agent status > status.txt
   cat status.txt
   ```

4. Check Rich console compatibility:
   ```bash
   python -c "from rich.console import Console; c=Console(); c.print('Test')"
   ```

5. Disable Rich formatting (if available):
   ```bash
   export NO_COLOR=1
   uv run ralph-agent status
   ```

#### Prevention
- Use a modern terminal emulator with UTF-8 support
- Keep terminal width reasonable (80+ characters)

---

### Hanging Commands

#### Symptoms
Commands hang indefinitely without output, or:
```
^C (Ctrl+C doesn't stop it)
```

#### Cause
- Waiting for API response
- Deadlock in async code
- Network issues

#### Solution
1. Try Ctrl+C multiple times

2. If that fails, find and kill the process:
   ```bash
   # Find the process
   ps aux | grep ralph

   # Kill it
   kill -9 PID
   ```

3. Check network connectivity:
   ```bash
   curl -I https://api.anthropic.com
   ```

4. Check for pending operations:
   ```bash
   uv run ralph-agent status
   ```

5. If the issue persists, reset state:
   ```bash
   uv run ralph-agent reset --keep-plan
   ```

#### Prevention
- Ensure stable network connection
- Set appropriate timeouts in configuration
- Use `ralph-agent pause` instead of killing processes

---

## Recovery Procedures

### How to Reset State Safely

When you need to start fresh without losing your plan:

```bash
# 1. Check current state
uv run ralph-agent status --verbose

# 2. Backup current state (optional)
cp -r .ralph .ralph.backup

# 3. Reset state but keep plan
uv run ralph-agent reset --keep-plan

# 4. Verify state was reset
uv run ralph-agent status

# 5. Continue from where you left off
uv run ralph-agent run
```

If you need a complete reset (removing all state files):

```bash
# Option A: Use the clean command (recommended)
uv run ralph-agent clean              # Remove state files, keep config
uv run ralph-agent clean --memory     # Also remove memory files
uv run ralph-agent init               # Reinitialize

# Option B: Full reset using reset command
uv run ralph-agent reset
uv run ralph-agent init --force
```

---

### How to Regenerate Plan

When the plan has diverged from reality or specs have changed:

```bash
# 1. Review current plan
uv run ralph-agent tasks --all

# 2. Option A: Keep completed tasks
uv run ralph-agent regenerate-plan

# 3. Option B: Discard everything and start fresh
uv run ralph-agent regenerate-plan --discard-completed

# 4. Run planning to create new tasks
uv run ralph-agent plan

# 5. Review new plan
uv run ralph-agent tasks --all

# 6. Continue building
uv run ralph-agent build
```

---

### How to Skip Problematic Tasks

When a task is blocking progress:

```bash
# 1. Identify the problematic task
uv run ralph-agent tasks --all

# 2. Skip with a reason
uv run ralph-agent skip task-003 --reason "Requires external API not available in dev"

# 3. Verify task was skipped
uv run ralph-agent tasks --all

# 4. Resume normal operation
uv run ralph-agent resume
```

For multiple stuck tasks:

```bash
# Skip multiple tasks
uv run ralph-agent skip task-003 --reason "Blocked on external dependency"
uv run ralph-agent skip task-005 --reason "Needs design clarification"

# Resume
uv run ralph-agent resume
```

---

### How to Inject Guidance

When the agent needs direction:

```bash
# Simple guidance
uv run ralph-agent inject "Focus on completing the user model first before the API endpoints"

# High priority guidance (processed first)
uv run ralph-agent inject "IMPORTANT: The database connection string is in .env, not config.py" --priority 1

# Provide error context
uv run ralph-agent inject "The last attempt failed because of a circular import. Import the module inside the function instead." --priority 1

# Provide technical direction
uv run ralph-agent inject "Use SQLAlchemy 2.0 style with the new select() syntax, not the legacy Query API"
```

View pending injections:

```bash
cat .ralph/injections.json
```

---

### When to Start Fresh

Start fresh when:

1. **State is severely corrupted** and recovery attempts fail
2. **Specs have fundamentally changed** and the plan is obsolete
3. **Cost has exceeded limits** and you want to restart with a new budget
4. **Too many blocked tasks** are impeding progress

Steps for a clean start:

```bash
# 1. Preview what will be cleaned (recommended)
uv run ralph-agent clean --dry-run

# 2. Clean up state files (preserves config.yaml)
uv run ralph-agent clean

# 3. Or clean up including memory files
uv run ralph-agent clean --memory

# 4. Reinitialize
uv run ralph-agent init

# 5. Start from discovery (or your desired phase)
uv run ralph-agent discover --goal "Your goal"
# OR jump to planning if you have specs
uv run ralph-agent plan
```

Alternative manual cleanup (not recommended):

```bash
# Manual cleanup only if `clean` command fails
cp -r .ralph .ralph.backup.$(date +%Y%m%d)
rm -rf .ralph
rm -f MEMORY.md progress.txt
uv run ralph-agent init
```

---

## Diagnostic Commands Reference

Quick reference for diagnosing issues:

```bash
# Overall status
uv run ralph-agent status --verbose

# Task status
uv run ralph-agent tasks --all
uv run ralph-agent tasks --pending

# Session history
uv run ralph-agent history --limit 20

# Check state files directly
cat .ralph/state.json | python -m json.tool
cat .ralph/implementation_plan.json | python -m json.tool

# Check session archives
cat .ralph/session_history/sessions.jsonl | tail -5

# Check pending injections
cat .ralph/injections.json 2>/dev/null || echo "No pending injections"

# Check memory file
cat MEMORY.md 2>/dev/null || echo "No memory file"

# Check progress learnings
tail -20 progress.txt 2>/dev/null || echo "No progress file"

# Check specs
ls -la specs/ 2>/dev/null || echo "No specs directory"

# Verify environment
uv run python -c "import ralph; print(ralph.__version__)"
echo "API Key set: $([ -n \"$ANTHROPIC_API_KEY\" ] && echo 'yes' || echo 'no')"

# Check disk space
df -h .

# Check permissions
ls -la .ralph/

# Preview cleanup targets
uv run ralph-agent clean --dry-run
```

### Example Diagnostic Session

```bash
$ uv run ralph-agent status --verbose

Ralph Status
Phase: building
Iteration: 45
Session ID: abc123

Cost Tracking
Total Cost: $12.3456
Session Cost: $2.1234

Circuit Breaker
State: closed
Failure Count: 0/3
Stagnation Count: 2/5

Context Budget
Usage: 45.2%
Available: 109,600 tokens

Implementation Plan
ID          Pri  Status       Description
task-001    1    complete     Set up project structure
task-002    1    complete     Implement user model
task-003    2    in_progress  Add authentication endpoint
task-004    2    pending      Write integration tests

Completion: 50.0% (2/4 tasks)
Next task: Add authentication endpoint
```

---

## Getting Help

If you encounter an issue not covered in this guide:

1. **Check logs**: Look for error messages in terminal output
2. **Search existing issues**: Check the project issue tracker
3. **Gather diagnostic info**: Run the diagnostic commands above
4. **Report the issue**: Include:
   - Ralph version (`uv run ralph-agent version`)
   - Python version (`python --version`)
   - OS and version
   - Full error message
   - Output of `ralph-agent status --verbose`
   - Steps to reproduce

---

## See Also

- [Getting Started Guide](getting-started.md) - Initial setup and first steps
- [CLI Reference](cli-reference.md) - Complete command documentation
- [Core Concepts](core-concepts.md) - Understanding Ralph's architecture
