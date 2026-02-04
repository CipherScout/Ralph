# Ralph - Deterministic Agentic Coding Loop

## Project Overview

Ralph is a deterministic agentic coding loop built on Claude Agent SDK. It orchestrates Claude through four development phases (Discovery, Planning, Building, Validation) with persistent state, circuit breakers, and context management.

## Development Commands

**IMPORTANT: Always use `uv` for all Python commands - never use bare `python`, `pytest`, `pip`, etc.**

```bash
# Run tests (1200+ tests expected to pass)
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_sdk_client.py -v

# Run linting
uv run ruff check src/

# Run type checking
uv run mypy src/

# Fix lint issues automatically
uv run ruff check src/ --fix

# Run the CLI
uv run ralph-agent --help
uv run ralph-agent discover --goal "..."
uv run ralph-agent plan
uv run ralph-agent build
uv run ralph-agent validate
```

## Project Structure

```
src/ralph/
├── cli.py          # Typer CLI with Rich display (RalphLiveDisplay)
├── sdk_client.py   # Claude Agent SDK wrapper (RalphSDKClient)
├── executors.py    # Phase executors (Discovery, Planning, Building, Validation)
├── events.py       # StreamEvent types for real-time output
├── models.py       # Core data models (RalphState, Task, ImplementationPlan)
├── config.py       # Configuration (RalphConfig, CostLimits)
├── persistence.py  # State/plan save/load
├── context.py      # Context management, handoffs
├── mcp_tools.py    # Ralph MCP tools (ralph_mark_task_complete, etc.)
├── sdk_hooks.py    # SDK safety hooks (bash safety, phase validation)
├── verification.py # Test/lint/type verification
└── templates/      # System prompt templates
```

## Architecture Patterns

### Event Streaming
Ralph uses async generators with `yield`/`send()` for bidirectional communication:

```python
async def stream_execution(self) -> AsyncGenerator[StreamEvent, str | None]:
    # Yield events to display
    yield info_event("Starting...")

    # Get user input via send()
    user_response = yield needs_input_event(question="...", options=[...])
```

### Claude Agent SDK Integration

**Tool Permission Callback** - Handle user input tools via `can_use_tool`:

```python
async def can_use_tool(tool_name, input_data, context):
    if tool_name == "AskUserQuestion":
        # Display questions, collect answers
        return PermissionResultAllow(
            updated_input={"questions": [...], "answers": {...}}
        )
    return PermissionResultAllow()
```

**Key SDK Types**:
- `ClaudeAgentOptions` - Configure tools, hooks, MCP servers
- `PermissionResultAllow(updated_input={...})` - Allow with modified input
- `PermissionResultDeny(message="...")` - Deny with reason
- `HookMatcher` - Tool validation hooks

### Phase Execution

Each phase has an executor in `executors.py`:
- `DiscoveryExecutor` - Interactive requirements gathering with AskUserQuestion
- `PlanningExecutor` - Create tasks using ralph_add_task MCP tool
- `BuildingExecutor` - Implement tasks with TDD, circuit breaker protection
- `ValidationExecutor` - Run tests/lint/types, optional human approval

## Code Conventions

- Line length: 100 characters (ruff)
- Python 3.11+ with type hints
- Use `from __future__ import annotations` for forward references
- Dataclasses for models, not Pydantic (except config)
- Async/await for SDK interactions
- Rich for CLI formatting (Panel, Console, Prompt)

## Testing Requirements

- All tests must pass before committing
- Test files mirror source structure: `tests/test_<module>.py`
- Use `pytest-asyncio` for async tests (auto mode configured)
- Mock SDK client for unit tests

## Common Pitfalls

1. **SDK Documentation**: Always check Context7 for Claude Agent SDK docs - don't guess API signatures
   ```
   Use: mcp__plugin_context7_context7__query-docs with libraryId="/anthropics/claude-agent-sdk-python"
   ```

2. **AskUserQuestion Structure**: Uses `questions` (plural array), not `question` (singular)
   ```python
   # Correct
   questions = input_data.get("questions", [])
   first_q = questions[0]
   question_text = first_q.get("question", "")
   ```

3. **Tool Results**: The `can_use_tool` callback provides answers via `updated_input`, not by intercepting the message stream

4. **Verbosity Levels**:
   - `verbosity=2` (default) - Show LLM text
   - `verbosity=1` (--quiet) - Show only tool calls

## Key Files for Common Tasks

| Task | Files |
|------|-------|
| Add CLI command | `cli.py` |
| Modify SDK behavior | `sdk_client.py` |
| Add safety hooks | `sdk_hooks.py` |
| Change phase logic | `executors.py` |
| Add event types | `events.py` |
| Modify state/models | `models.py` |
| Add MCP tools | `mcp_tools.py` |

## Configuration

Ralph stores state in `.ralph/` directory:
- `state.json` - Current phase, iteration count, circuit breaker
- `implementation_plan.json` - Tasks with dependencies
- `config.yaml` - User configuration
- `memory/` - Context handoff files
