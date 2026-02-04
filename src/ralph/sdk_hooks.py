"""SDK hooks adapter for Ralph orchestrator.

Converts Ralph's internal hook system to Claude Agent SDK HookMatcher format.
Provides PreToolUse validation hooks for command safety, phase validation,
and uv enforcement.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from claude_agent_sdk import HookMatcher

from ralph.models import RalphState
from ralph.sdk import BLOCKED_GIT_COMMANDS, BLOCKED_PACKAGE_COMMANDS

if TYPE_CHECKING:
    # Type hints for SDK types
    HookInput = dict[str, Any]
    HookContext = dict[str, Any]
    HookJSONOutput = dict[str, Any]

# Set up logger for structured logging
logger = logging.getLogger(__name__)


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
    state: RalphState, max_cost_per_iteration: float = 10.0
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


def create_task_tool_validation_hook(state: RalphState) -> HookMatcher:
    """Create hook to validate Task tool subagent invocations.

    This hook provides comprehensive validation for Task tool usage to ensure:
    1. Subagent type is valid (exists in the subagent system)
    2. Phase-specific subagent restrictions are enforced
    3. Invalid subagents are blocked with helpful error messages
    4. Subagent invocation attempts are logged for monitoring

    Note: Parallel execution is managed by the Claude Agent SDK itself;
    Ralph does not need to enforce concurrency limits at the hook level.

    Args:
        state: Current Ralph state (for phase access)

    Returns:
        HookMatcher for Task tool validation
    """

    async def validate_task_tool(
        input_data: HookInput,
        tool_use_id: str | None,
        context: HookContext,
    ) -> HookJSONOutput:
        """Validate Task tool inputs against subagent policies."""
        tool_name = input_data.get("tool_name", "")
        if tool_name != "Task":
            return _allow_response()

        tool_input = input_data.get("tool_input", {})
        subagent_type = tool_input.get("subagent_type")

        # Log subagent invocation attempt
        description = tool_input.get("description", "")
        logger.info(
            f"Subagent invocation attempt: type={subagent_type}, "
            f"phase={state.current_phase.value}, description='{description}'"
        )

        # Check if subagent_type is provided
        if not subagent_type:
            return _deny_response(
                "Task tool requires 'subagent_type' parameter",
                "Specify a valid subagent type like 'code-reviewer' or 'research-specialist'"
            )

        # Import here to avoid circular imports
        from typing import cast

        from ralph.subagents import PHASE_SUBAGENT_CONFIG, SUBAGENT_SECURITY_CONSTRAINTS

        # Check if subagent type is valid (exists in our configuration)
        tool_permissions = cast(
            dict[str, list[str]], SUBAGENT_SECURITY_CONSTRAINTS.get("tool_permissions", {})
        )
        if subagent_type not in tool_permissions:
            return _deny_response(
                f"Invalid subagent type: '{subagent_type}'",
                f"Valid types: {', '.join(tool_permissions.keys())}"
            )

        # Check phase-specific restrictions
        allowed_subagents_for_phase = PHASE_SUBAGENT_CONFIG.get(state.current_phase, [])
        if subagent_type not in allowed_subagents_for_phase:
            allowed_types_str = ', '.join(allowed_subagents_for_phase)
            return _deny_response(
                f"Subagent '{subagent_type}' not allowed in {state.current_phase.value} phase",
                f"Allowed subagents for {state.current_phase.value}: {allowed_types_str}"
            )

        # All validations passed
        logger.info(
            f"Task tool validation passed: subagent_type={subagent_type}, "
            f"phase={state.current_phase.value}"
        )
        return _allow_response()

    return HookMatcher(matcher="Task", hooks=[validate_task_tool])  # type: ignore[list-item]


def get_ralph_hooks(
    state: RalphState,
    max_cost_per_iteration: float = 10.0,
    include_phase_validation: bool = True,
    include_cost_limits: bool = True,
) -> dict[str, list[HookMatcher]]:
    """Get all Ralph hooks for the Claude Agent SDK.

    Args:
        state: Current Ralph state
        max_cost_per_iteration: Maximum cost per iteration
        include_phase_validation: Whether to include phase validation
        include_cost_limits: Whether to include cost limit checks

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


def get_safety_hooks(
    state: RalphState,
    max_cost_per_iteration: float = 10.0,
    include_phase_validation: bool = True,
    include_cost_limits: bool = True,
    include_task_validation: bool = True,
) -> dict[str, list[HookMatcher]]:
    """Get all safety hooks including Task tool validation.

    This function provides the complete set of safety hooks for Ralph,
    including the Task tool validation hook for subagent control.

    Args:
        state: Current Ralph state
        max_cost_per_iteration: Maximum cost per iteration
        include_phase_validation: Whether to include phase validation
        include_cost_limits: Whether to include cost limit checks
        include_task_validation: Whether to include Task tool validation

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

    if include_task_validation:
        pre_tool_use_hooks.append(create_task_tool_validation_hook(state))

    return {
        "PreToolUse": pre_tool_use_hooks,
    }
