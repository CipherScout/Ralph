# Task Completion Checklist

Before considering any task complete, run these commands:

## Required Checks
1. **Run all tests**: `uv run pytest tests/ -v`
   - All 554 tests must pass
   - No test failures or errors allowed

2. **Linting**: `uv run ruff check src/`
   - No linting errors
   - Use `uv run ruff check src/ --fix` to auto-fix

3. **Type checking**: `uv run mypy src/`
   - No type errors
   - Strict typing must pass

## Before Committing
- Ensure all tests pass
- No linting or type errors
- Test files mirror source structure: `tests/test_<module>.py`
- Use pytest-asyncio for async tests

## Key Quality Gates
- Code follows 100-character line limit
- All functions have type annotations
- Async patterns used correctly for SDK interactions
- Rich formatting used for CLI output