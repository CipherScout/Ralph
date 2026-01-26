"""SDK hooks adapter for Ralph orchestrator.

Converts Ralph's internal hook system to Claude Agent SDK HookMatcher format.
Provides PreToolUse validation hooks for command safety, phase validation,
and uv enforcement.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from claude_agent_sdk import HookMatcher

from ralph.models import RalphState
from ralph.sdk import BLOCKED_GIT_COMMANDS, BLOCKED_PACKAGE_COMMANDS

if TYPE_CHECKING:
    # Type hints for SDK types
    HookInput = dict[str, Any]
    HookContext = dict[str, Any]
    HookJSONOutput = dict[str, Any]


def _deny_response(reason: str, suggestion: str | None = None) -> dict[str, Any]:
    """Create a deny response for a hook.

    Args:
        reason: Why the tool use was denied
        suggestion: Optional suggestion for alternative action

    Returns:
        Hook output dict with deny decision
    """
    output: dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    if suggestion:
        output["hookSpecificOutput"]["suggestion"] = suggestion
    return output


def _allow_response() -> dict[str, Any]:
    """Create an allow response for a hook."""
    return {}


def create_bash_safety_hook() -> HookMatcher:
    """Create hook to block dangerous bash commands.

    Blocks:
    - Git state operations (commit, push, etc.)
    - Non-uv package manager commands (pip, conda, etc.)

    Returns:
        HookMatcher for Bash tool validation
    """

    async def check_bash_command(
        input_data: HookInput,
        tool_use_id: str | None,
        context: HookContext,
    ) -> HookJSONOutput:
        """Validate bash command against safety rules."""
        tool_name = input_data.get("tool_name", "")
        if tool_name != "Bash":
            return _allow_response()

        tool_input = input_data.get("tool_input", {})
        command = tool_input.get("command", "")
        command_lower = command.lower().strip()

        # Check for blocked git operations
        for blocked in BLOCKED_GIT_COMMANDS:
            if blocked in command_lower:
                return _deny_response(
                    f"Git state operation blocked: {blocked}",
                    "Ralph uses read-only git. State changes require manual intervention.",
                )

        # Check for blocked package manager commands
        for blocked in BLOCKED_PACKAGE_COMMANDS:
            if blocked in command_lower:
                # Provide helpful uv alternatives
                suggestion = "Use uv instead"
                if "pip install" in blocked or "pip3 install" in blocked:
                    suggestion = "Use 'uv add <package>' instead"
                elif "pip uninstall" in blocked or "pip3 uninstall" in blocked:
                    suggestion = "Use 'uv remove <package>' instead"
                elif "pip freeze" in blocked:
                    suggestion = "Use 'uv lock' instead"
                elif "venv" in blocked or "virtualenv" in blocked:
                    suggestion = "uv manages environments automatically"

                return _deny_response(
                    f"Package manager command blocked: {blocked}",
                    suggestion,
                )

        return _allow_response()

    return HookMatcher(matcher="Bash", hooks=[check_bash_command])  # type: ignore[list-item]


def create_uv_enforcement_hook() -> HookMatcher:
    """Create hook to enforce uv prefix for Python commands.

    Automatically adds 'uv run' prefix to Python tool commands
    that don't already have it.

    Returns:
        HookMatcher for Bash tool modification
    """

    async def enforce_uv_prefix(
        input_data: HookInput,
        tool_use_id: str | None,
        context: HookContext,
    ) -> HookJSONOutput:
        """Add uv run prefix to Python commands if missing."""
        tool_name = input_data.get("tool_name", "")
        if tool_name != "Bash":
            return _allow_response()

        tool_input = input_data.get("tool_input", {})
        command = tool_input.get("command", "").strip()

        # Commands that should use uv run
        python_commands = ["pytest", "mypy", "ruff", "python", "python3"]

        for cmd in python_commands:
            if command.startswith(cmd) and not command.startswith("uv run"):
                # Note: SDK doesn't support modification via hooks,
                # so we deny with a suggestion to use the correct command
                modified_command = f"uv run {command}"
                return _deny_response(
                    f"Python command '{cmd}' should use uv run prefix",
                    f"Use: {modified_command}",
                )

        return _allow_response()

    return HookMatcher(matcher="Bash", hooks=[enforce_uv_prefix])  # type: ignore[list-item]


def create_phase_validation_hook(state: RalphState) -> HookMatcher:
    """Create hook to validate tool use against current phase.

    Args:
        state: Current Ralph state (for phase access)

    Returns:
        HookMatcher for all tools
    """
    # Import here to avoid circular imports
    from ralph.sdk_client import get_tools_for_phase

    async def validate_phase(
        input_data: HookInput,
        tool_use_id: str | None,
        context: HookContext,
    ) -> HookJSONOutput:
        """Validate tool is allowed for current phase."""
        tool_name = input_data.get("tool_name", "")
        allowed_tools = get_tools_for_phase(state.current_phase)

        # Also allow MCP tools
        if tool_name.startswith("mcp__"):
            return _allow_response()

        if tool_name not in allowed_tools:
            return _deny_response(
                f"Tool '{tool_name}' not allowed in {state.current_phase.value} phase",
                f"Allowed tools: {', '.join(allowed_tools[:5])}...",
            )

        return _allow_response()

    return HookMatcher(matcher="*", hooks=[validate_phase])  # type: ignore[list-item]


def create_cost_limit_hook(
    state: RalphState, max_cost_per_iteration: float = 2.0
) -> HookMatcher:
    """Create hook to enforce cost limits.

    Args:
        state: Current Ralph state
        max_cost_per_iteration: Maximum cost in USD per iteration

    Returns:
        HookMatcher for all tools
    """

    async def check_cost_limit(
        input_data: HookInput,
        tool_use_id: str | None,
        context: HookContext,
    ) -> HookJSONOutput:
        """Check if cost limits are exceeded."""
        if state.session_cost_usd >= max_cost_per_iteration:
            cost_msg = (
                f"Iteration cost limit exceeded: "
                f"${state.session_cost_usd:.2f} >= ${max_cost_per_iteration:.2f}"
            )
            return _deny_response(
                cost_msg,
                "Consider completing the current task or requesting handoff.",
            )
        return _allow_response()

    return HookMatcher(matcher="*", hooks=[check_cost_limit])  # type: ignore[list-item]


def create_context_budget_hook(state: RalphState) -> HookMatcher:
    """Create hook to check context budget before tool use.

    Args:
        state: Current Ralph state

    Returns:
        HookMatcher for all tools
    """

    async def check_context_budget(
        input_data: HookInput,
        tool_use_id: str | None,
        context: HookContext,
    ) -> HookJSONOutput:
        """Check if context budget is exhausted."""
        if state.needs_handoff():
            return _deny_response(
                f"Context budget exceeded ({state.context_budget.current_usage} tokens)",
                "Complete current task and trigger handoff to fresh session.",
            )
        return _allow_response()

    return HookMatcher(matcher="*", hooks=[check_context_budget])  # type: ignore[list-item]


def get_ralph_hooks(
    state: RalphState,
    max_cost_per_iteration: float = 2.0,
    include_phase_validation: bool = True,
    include_cost_limits: bool = True,
    include_context_budget: bool = True,
) -> dict[str, list[HookMatcher]]:
    """Get all Ralph hooks for the Claude Agent SDK.

    Args:
        state: Current Ralph state
        max_cost_per_iteration: Maximum cost per iteration
        include_phase_validation: Whether to include phase validation
        include_cost_limits: Whether to include cost limit checks
        include_context_budget: Whether to include context budget checks

    Returns:
        Dict of hook event names to HookMatcher lists
    """
    pre_tool_use_hooks: list[HookMatcher] = [
        create_bash_safety_hook(),
        create_uv_enforcement_hook(),
    ]

    if include_phase_validation:
        pre_tool_use_hooks.append(create_phase_validation_hook(state))

    if include_cost_limits:
        pre_tool_use_hooks.append(create_cost_limit_hook(state, max_cost_per_iteration))

    if include_context_budget:
        pre_tool_use_hooks.append(create_context_budget_hook(state))

    return {
        "PreToolUse": pre_tool_use_hooks,
    }


def get_minimal_hooks() -> dict[str, list[HookMatcher]]:
    """Get minimal safety hooks (no state required).

    Returns only the bash safety and uv enforcement hooks.

    Returns:
        Dict of hook event names to HookMatcher lists
    """
    return {
        "PreToolUse": [
            create_bash_safety_hook(),
            create_uv_enforcement_hook(),
        ],
    }
