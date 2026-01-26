"""Claude Agent SDK integration for Ralph orchestrator.

Provides phase-specific client configuration, tool allocation,
and safety constraints for deterministic workflow control.

This module provides utility functions and re-exports the SDK client
from sdk_client.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ralph.models import Phase

# Re-export from sdk_client for new code
from ralph.sdk_client import (
    PHASE_TOOLS,  # noqa: F401
    IterationResult,
    RalphSDKClient,
    calculate_cost,
    calculate_max_turns,
    create_ralph_client,
    get_model_for_phase,
    get_tools_for_phase,
)

__all__ = [
    "IterationResult",
    "RalphSDKClient",
    "calculate_cost",
    "calculate_max_turns",
    "create_ralph_client",
    "get_model_for_phase",
    "get_tools_for_phase",
    "PHASE_TOOLS",
    "BLOCKED_GIT_COMMANDS",
    "ALLOWED_GIT_COMMANDS",
    "BLOCKED_PACKAGE_COMMANDS",
    "CommandValidationResult",
    "validate_bash_command",
]


# Tool allocation by phase - import from sdk_client

# Git operations that are blocked (read-only git per PRD Section 9)
BLOCKED_GIT_COMMANDS: list[str] = [
    "git commit",
    "git push",
    "git pull",
    "git merge",
    "git rebase",
    "git checkout",
    "git reset",
    "git stash",
    "git cherry-pick",
    "git revert",
    "git branch -D",
    "git branch -d",
]

# Allowed git operations (read-only)
ALLOWED_GIT_COMMANDS: list[str] = [
    "git status",
    "git log",
    "git diff",
    "git show",
    "git ls-files",
    "git blame",
    "git branch",  # listing only
]

# Package manager commands that are blocked (uv enforcement per PRD Section 9)
BLOCKED_PACKAGE_COMMANDS: list[str] = [
    # pip commands
    "pip install",
    "pip uninstall",
    "pip freeze",
    "python -m pip",
    "pip3 install",
    "pip3 uninstall",
    # venv/virtualenv commands
    "python -m venv",
    "python3 -m venv",
    "virtualenv",
    # Other package managers
    "conda install",
    "conda create",
    "conda activate",
    "poetry install",
    "poetry add",
    "poetry remove",
    "pipenv install",
    "pipenv shell",
]


@dataclass
class CommandValidationResult:
    """Result of validating a bash command."""

    allowed: bool
    reason: str | None = None
    suggestion: str | None = None


def validate_bash_command(command: str) -> CommandValidationResult:
    """Validate a bash command against safety rules.

    Args:
        command: The command to validate

    Returns:
        CommandValidationResult indicating if command is allowed
    """
    command_lower = command.lower().strip()

    # Check for blocked git operations
    for blocked in BLOCKED_GIT_COMMANDS:
        if blocked in command_lower:
            return CommandValidationResult(
                allowed=False,
                reason=f"Git state operation blocked: {blocked}",
                suggestion="Ralph uses read-only git. State changes require manual intervention.",
            )

    # Check for blocked package manager commands
    for blocked in BLOCKED_PACKAGE_COMMANDS:
        if blocked in command_lower:
            # Provide helpful suggestion for uv alternatives
            suggestion = None
            if "pip install" in blocked or "pip3 install" in blocked:
                suggestion = "Use 'uv add <package>' instead"
            elif "pip uninstall" in blocked or "pip3 uninstall" in blocked:
                suggestion = "Use 'uv remove <package>' instead"
            elif "pip freeze" in blocked:
                suggestion = "Use 'uv lock' instead"
            elif "venv" in blocked or "virtualenv" in blocked:
                suggestion = "uv manages environments automatically"
            elif "conda" in blocked:
                suggestion = "Use uv for package management"
            elif "poetry" in blocked:
                suggestion = "Use 'uv add <package>' for dependencies"
            elif "pipenv" in blocked:
                suggestion = "Use uv for environment and package management"

            return CommandValidationResult(
                allowed=False,
                reason=f"Package manager command blocked: {blocked}",
                suggestion=suggestion or "Use uv instead",
            )

    return CommandValidationResult(allowed=True)


async def validate_tool_use_for_phase(
    tool_name: str,
    tool_input: dict[str, Any],
    phase: Phase,
) -> CommandValidationResult:
    """Validate a tool use before execution.

    This is a utility function for hooks to enforce safety constraints.

    Args:
        tool_name: Name of the tool being used
        tool_input: Input to the tool
        phase: Current phase

    Returns:
        CommandValidationResult indicating if tool use is allowed
    """
    # Check if tool is allowed for current phase
    allowed_tools = get_tools_for_phase(phase)
    if tool_name not in allowed_tools:
        return CommandValidationResult(
            allowed=False,
            reason=f"Tool '{tool_name}' not allowed in {phase.value} phase",
        )

    # Special validation for Bash commands
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        return validate_bash_command(command)

    return CommandValidationResult(allowed=True)
