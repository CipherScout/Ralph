# Ralph Documentation

Welcome to the Ralph documentation! Ralph is a deterministic agentic coding loop that uses Python to orchestrate Claude for autonomous software development.

## Quick Navigation

| Document | Description |
|----------|-------------|
| [Getting Started](getting-started.md) | Installation, setup, and your first Ralph session |
| [Core Concepts](core-concepts.md) | Philosophy, phases, state management, and safety controls |
| [CLI Reference](cli-reference.md) | Complete command reference with examples |
| [Configuration](configuration.md) | All configuration options and examples |
| [Troubleshooting](troubleshooting.md) | Common issues and how to solve them |
| [Architecture](architecture.md) | Internal design for contributors |

## Learning Path

### New to Ralph?

1. **Start here**: [Getting Started](getting-started.md)
   - Install prerequisites
   - Run your first workflow
   - Understand the output

2. **Understand the concepts**: [Core Concepts](core-concepts.md)
   - Learn the four-phase workflow
   - Understand state management
   - Learn about safety controls

3. **Master the CLI**: [CLI Reference](cli-reference.md)
   - All commands with examples
   - Workflow patterns

### Setting Up for Your Project

1. [Configuration](configuration.md) - Customize Ralph for your needs
2. [CLI Reference](cli-reference.md) - Learn the commands you'll use daily

### When Things Go Wrong

1. [Troubleshooting](troubleshooting.md) - Diagnose and fix issues
2. [Error Recovery](../README.md#error-recovery--troubleshooting) - Recovery procedures

### Contributing to Ralph

1. [Architecture](architecture.md) - Understand the internals
2. [Core Concepts](core-concepts.md) - Understand the design principles

## Key Concepts at a Glance

### The Four Phases

```
Discovery → Planning → Building → Validation
    │           │          │           │
    ▼           ▼          ▼           ▼
  Specs      Tasks      Code       Verified
```

1. **Discovery**: Gather requirements using JTBD framework
2. **Planning**: Create sized, prioritized tasks with dependencies
3. **Building**: Implement tasks iteratively with TDD
4. **Validation**: Verify with tests, linting, and type checking

### Safety Controls

- **Circuit Breaker**: Halts after 3 failures or 5 stagnation iterations
- **Cost Limits**: Per-iteration ($10), per-session ($50), total ($100)
- **Command Blocking**: Read-only git, uv-only package management

### Quick Commands

```bash
# Initialize Ralph
uv run ralph-agent init

# Run full workflow
uv run ralph-agent run --goal "Your feature description"

# Check status
uv run ralph-agent status --verbose

# View tasks
uv run ralph-agent tasks --all

# Skip a problematic task
uv run ralph-agent skip TASK_ID --reason "Description"

# Resume after pause/halt
uv run ralph-agent resume
```

## Getting Help

- **Issues**: Check [Troubleshooting](troubleshooting.md) first
- **Questions**: Open an issue on the repository
- **Contributing**: See [Architecture](architecture.md) for internals

## Documentation Version

This documentation covers Ralph v0.1.0.
