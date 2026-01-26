# Ralph Agent Architecture

This document describes the agent architecture used in Ralph's deterministic coding loop.

## Overview

Ralph uses a single-agent architecture with Python orchestration. The LLM operates in discrete sessions (context windows), while Python maintains persistent state across sessions.

```
┌─────────────────────────────────────────────────────────────┐
│                    Python Orchestrator                       │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────┐ │
│  │  State  │  │  Plan   │  │ Config  │  │ Circuit Breaker │ │
│  │ Manager │  │ Manager │  │ Loader  │  │    Manager      │ │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────────┬────────┘ │
│       │            │            │                │          │
│  ┌────┴────────────┴────────────┴────────────────┴────┐     │
│  │                  Loop Runner                        │     │
│  │   ┌─────────────────────────────────────────────┐  │     │
│  │   │            Context Hand-off                  │  │     │
│  │   │  MEMORY.md ← Session Archive → New Session  │  │     │
│  │   └─────────────────────────────────────────────┘  │     │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Claude Agent SDK                          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                    LLM Session                       │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │    │
│  │  │ System   │  │  Tools   │  │ Phase-Specific   │   │    │
│  │  │ Prompt   │  │ (Gated)  │  │ Instructions     │   │    │
│  │  └──────────┘  └──────────┘  └──────────────────┘   │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Phase-Specific Tool Allocation

Each phase has a curated set of tools:

### Discovery Phase
```
Tools: Read, Glob, Grep, WebSearch, WebFetch, Write, Task, AskUserQuestion
Focus: Understanding requirements, asking questions
```

### Planning Phase
```
Tools: Read, Glob, Grep, WebSearch, WebFetch, Write, Task, ExitPlanMode
Focus: Creating implementation plan with tasks
```

### Building Phase
```
Tools: Read, Write, Edit, Bash, Glob, Grep, Task, TodoWrite, WebSearch, WebFetch
Focus: Implementing code, running tests
```

### Validation Phase
```
Tools: Read, Glob, Grep, Bash, Task, WebFetch
Focus: Verifying implementation, running checks
```

## Tool Validation Hooks

All tool uses are validated through hooks:

### PreToolUse Hooks
1. **Phase Validation**: Tool must be allowed in current phase
2. **Bash Command Validation**: Block dangerous commands
3. **uv Prefix Enforcement**: Add `uv run` to Python tools

### PostToolUse Hooks
1. **Token Tracking**: Update context budget
2. **Error Recording**: Track failures for circuit breaker

## Custom MCP Tools

Ralph provides custom tools for state management:

### ralph_get_next_task
Returns the next available task based on priority and dependencies.

### ralph_mark_task_complete
Marks a task complete with optional notes and token tracking.

### ralph_mark_task_blocked
Marks a task as blocked with a reason.

### ralph_append_learning
Records learnings to progress.txt for future sessions.

### ralph_add_task
Adds a new task to the plan (used in planning phase).

## Context Hand-off Protocol

When context budget reaches threshold (~60%):

1. **Generate MEMORY.md**
   - Session summary
   - Completed tasks
   - Current task state
   - Learnings
   - Files modified

2. **Archive Session**
   - Save to sessions.jsonl
   - Record metrics

3. **Start New Session**
   - Fresh context
   - Load MEMORY.md
   - Continue from state

## Circuit Breaker Pattern

Ralph implements a circuit breaker to prevent runaway loops:

### Triggers
- 3 consecutive failures
- 5 iterations without progress
- Cost limit exceeded ($100 default)

### States
- **Closed**: Normal operation
- **Open**: Halt execution
- **Half-Open**: Recovery attempt

### Recovery Actions
1. Retry with backoff
2. Skip blocked task
3. Force context handoff
4. Manual intervention

## State Files

### .ralph/state.json
```json
{
  "current_phase": "building",
  "iteration_count": 42,
  "session_id": "abc123",
  "total_cost_usd": 15.50,
  "circuit_breaker": {...},
  "context_budget": {...}
}
```

### .ralph/implementation_plan.json
```json
{
  "tasks": [
    {
      "id": "auth-01",
      "description": "Implement login API",
      "priority": 1,
      "status": "complete",
      "dependencies": []
    }
  ]
}
```

### MEMORY.md
Markdown file containing session context for LLM to read.

### progress.txt
Append-only log of learnings and patterns.

## Cost Control

```
Hierarchy:
- Per-iteration limit: $2 (prevents runaway single calls)
- Per-session limit: $50 (prevents expensive sessions)
- Total project limit: $200 (hard stop)
```

## Safety Constraints

### Git (Read-Only)
- Allowed: status, diff, log, show, branch
- Blocked: commit, push, merge, rebase, reset

### Package Management (uv-Only)
- Allowed: uv run, uv add, uv sync, uv remove
- Blocked: pip, venv, conda, poetry, pipenv

### Command Validation
All Bash commands are validated before execution.
Dangerous patterns are blocked by default.
