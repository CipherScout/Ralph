# Ralph Code Style & Conventions

## Code Style
- **Line length**: 100 characters (enforced by ruff)
- **Python version**: 3.11+ with type hints
- **Future imports**: Use `from __future__ import annotations` for forward references
- **Data models**: Dataclasses for models, Pydantic only for config
- **Async**: Use async/await for SDK interactions
- **UI**: Rich for CLI formatting (Panel, Console, Prompt)

## Naming Conventions
- Snake_case for variables, functions, modules
- PascalCase for classes
- ALL_CAPS for constants
- Descriptive names following domain language

## Architecture Patterns
- Event streaming with async generators using `yield`/`send()`
- Tool permission callbacks for user interaction
- Phase-based execution with specialized executors
- Circuit breaker patterns for fault tolerance

## Type Hints
- Strict typing enabled in mypy
- All functions must have type annotations
- Use Union types appropriately
- Forward references with `from __future__ import annotations`