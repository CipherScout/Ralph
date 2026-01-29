# Ralph Development Commands

**CRITICAL: Always use `uv` for all Python commands - never use bare `python`, `pytest`, `pip`, etc.**

## Core Development
```bash
# Run all tests (554 tests expected to pass)
uv run pytest tests/ -v

# Run specific test file  
uv run pytest tests/test_sdk_client.py -v

# Run linting
uv run ruff check src/

# Run type checking
uv run mypy src/

# Fix lint issues automatically
uv run ruff check src/ --fix
```

## Running Ralph
```bash
# CLI help
uv run ralph-agent --help

# Phase commands
uv run ralph-agent discover --goal "..."
uv run ralph-agent plan
uv run ralph-agent build
uv run ralph-agent validate
```

## System Commands (Darwin)
- `ls`, `cd`, `find`, `grep` work as standard Unix commands
- Git operations: `git status`, `git add`, `git commit`, `git push`