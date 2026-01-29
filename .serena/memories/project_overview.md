# Ralph Project Overview

Ralph is a deterministic agentic coding loop built on Claude Agent SDK. It orchestrates Claude through four development phases (Discovery, Planning, Building, Validation) with persistent state, circuit breakers, and context management.

## Tech Stack
- **Language**: Python 3.11+
- **CLI Framework**: Typer with Rich for display
- **Async Framework**: Built on Claude Agent SDK with async generators
- **Testing**: pytest with asyncio support
- **Code Quality**: ruff (linting), mypy (type checking)

## Project Purpose
Ralph automates the software development lifecycle by providing:
- Interactive requirements gathering (Discovery phase)
- Task planning with dependencies (Planning phase) 
- Iterative implementation with TDD (Building phase)
- Automated verification (Validation phase)

## Key Features
- Persistent state management in .ralph/ directory
- Circuit breaker patterns for failure recovery
- Event streaming for real-time progress
- MCP tool integration for task management