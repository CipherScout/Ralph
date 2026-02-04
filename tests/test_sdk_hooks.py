"""Tests for Claude SDK hooks integration."""

from pathlib import Path
from typing import Any, cast

import pytest
from claude_agent_sdk.types import HookContext, PreToolUseHookInput

from ralph.models import Phase, RalphState
from ralph.sdk_hooks import (
    _allow_response,
    _deny_response,
    create_bash_safety_hook,
    create_cost_limit_hook,
    create_phase_validation_hook,
    create_uv_enforcement_hook,
    get_minimal_hooks,
    get_ralph_hooks,
    get_safety_hooks,
)


# Typed factory functions for test inputs
def create_pre_tool_use_input(
    tool_name: str,
    tool_input: dict[str, Any] | None = None,
) -> PreToolUseHookInput:
    """Create a properly typed PreToolUseHookInput for testing."""
    return PreToolUseHookInput(
        session_id="test-session",
        transcript_path="/tmp/transcript.jsonl",
        cwd="/tmp/test",
        permission_mode="default",
        hook_event_name="PreToolUse",
        tool_name=tool_name,
        tool_input=tool_input or {},
    )


def create_hook_context() -> HookContext:
    """Create a properly typed HookContext for testing."""
    return HookContext(signal=None)


def as_dict(result: Any) -> dict[str, Any]:
    """Cast hook result to dict for assertion access.

    Hook functions return Union types, but at runtime return plain dicts.
    This helper allows type-safe dict access in tests.
    """
    return cast(dict[str, Any], result)


# Helper function to create a mock RalphState
def create_mock_state(
    phase: Phase = Phase.BUILDING,
    session_cost: float = 0.0,
) -> RalphState:
    """Create a mock RalphState for testing."""
    state = RalphState(project_root=Path("/tmp/test"))
    state.current_phase = phase
    state.session_cost_usd = session_cost
    return state


class TestHelperFunctions:
    """Tests for hook helper functions."""

    def test_deny_response_basic(self) -> None:
        """Deny response has correct structure."""
        result = _deny_response("Test reason")
        assert "hookSpecificOutput" in result
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert as_dict(result)["hookSpecificOutput"]["permissionDecisionReason"] == "Test reason"

    def test_deny_response_with_suggestion(self) -> None:
        """Deny response includes suggestion when provided."""
        result = _deny_response("Test reason", "Use this instead")
        assert as_dict(result)["hookSpecificOutput"]["suggestion"] == "Use this instead"

    def test_deny_response_without_suggestion(self) -> None:
        """Deny response omits suggestion when not provided."""
        result = _deny_response("Test reason")
        assert "suggestion" not in as_dict(result)["hookSpecificOutput"]

    def test_allow_response(self) -> None:
        """Allow response is empty dict."""
        result = _allow_response()
        assert result == {}


class TestBashSafetyHook:
    """Tests for bash safety hook."""

    @pytest.fixture
    def hook(self):
        """Create bash safety hook matcher."""
        return create_bash_safety_hook()

    @pytest.mark.asyncio
    async def test_allows_safe_command(self, hook) -> None:
        """Safe commands are allowed."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "ls -la"}),
            "test-id",
            create_hook_context(),
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_allows_git_status(self, hook) -> None:
        """Git status is allowed."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "git status"}),
            "test-id",
            create_hook_context(),
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_allows_git_log(self, hook) -> None:
        """Git log is allowed."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "git log --oneline -5"}),
            "test-id",
            create_hook_context(),
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_allows_git_diff(self, hook) -> None:
        """Git diff is allowed."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "git diff HEAD~1"}),
            "test-id",
            create_hook_context(),
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_blocks_git_commit(self, hook) -> None:
        """Git commit is blocked."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "git commit -m 'test'"}),
            "test-id",
            create_hook_context(),
        )
        assert "hookSpecificOutput" in result
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "git" in as_dict(result)["hookSpecificOutput"]["permissionDecisionReason"].lower()

    @pytest.mark.asyncio
    async def test_blocks_git_push(self, hook) -> None:
        """Git push is blocked."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "git push origin main"}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_git_pull(self, hook) -> None:
        """Git pull is blocked."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "git pull"}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_git_merge(self, hook) -> None:
        """Git merge is blocked."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "git merge feature"}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_git_rebase(self, hook) -> None:
        """Git rebase is blocked."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "git rebase main"}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_git_checkout(self, hook) -> None:
        """Git checkout is blocked."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "git checkout feature"}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_git_reset(self, hook) -> None:
        """Git reset is blocked."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "git reset --hard"}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_git_stash(self, hook) -> None:
        """Git stash is blocked."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "git stash"}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_pip_install(self, hook) -> None:
        """Pip install is blocked with uv suggestion."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "pip install requests"}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "uv" in as_dict(result)["hookSpecificOutput"]["suggestion"]

    @pytest.mark.asyncio
    async def test_blocks_pip3_install(self, hook) -> None:
        """Pip3 install is blocked."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "pip3 install requests"}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_pip_uninstall(self, hook) -> None:
        """Pip uninstall is blocked."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "pip uninstall requests"}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_venv_creation(self, hook) -> None:
        """Venv creation is blocked."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "python -m venv .venv"}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_virtualenv(self, hook) -> None:
        """Virtualenv is blocked."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "virtualenv .venv"}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_conda_install(self, hook) -> None:
        """Conda install is blocked."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "conda install numpy"}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_poetry_add(self, hook) -> None:
        """Poetry add is blocked."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "poetry add requests"}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_allows_uv_commands(self, hook) -> None:
        """UV commands are allowed."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "uv add requests"}),
            "test-id",
            create_hook_context(),
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_ignores_non_bash_tools(self, hook) -> None:
        """Non-Bash tools are ignored."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Read", {"file": "test.py"}),
            "test-id",
            create_hook_context(),
        )
        assert result == {}


class TestUvEnforcementHook:
    """Tests for uv enforcement hook."""

    @pytest.fixture
    def hook(self):
        """Create uv enforcement hook matcher."""
        return create_uv_enforcement_hook()

    @pytest.mark.asyncio
    async def test_allows_uv_run_pytest(self, hook) -> None:
        """uv run pytest is allowed."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "uv run pytest"}),
            "test-id",
            create_hook_context(),
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_blocks_bare_pytest(self, hook) -> None:
        """Bare pytest is blocked with suggestion."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "pytest -v"}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "uv run" in as_dict(result)["hookSpecificOutput"]["suggestion"]

    @pytest.mark.asyncio
    async def test_blocks_bare_mypy(self, hook) -> None:
        """Bare mypy is blocked."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "mypy ."}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_bare_ruff(self, hook) -> None:
        """Bare ruff is blocked."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "ruff check ."}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_bare_python(self, hook) -> None:
        """Bare python is blocked."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "python script.py"}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_allows_non_python_commands(self, hook) -> None:
        """Non-Python commands are allowed."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "ls -la"}),
            "test-id",
            create_hook_context(),
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_ignores_non_bash_tools(self, hook) -> None:
        """Non-Bash tools are ignored."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Edit", {"file": "test.py"}),
            "test-id",
            create_hook_context(),
        )
        assert result == {}


class TestPhaseValidationHook:
    """Tests for phase validation hook."""

    @pytest.mark.asyncio
    async def test_allows_read_in_all_phases(self) -> None:
        """Read tool is allowed in all phases."""
        for phase in Phase:
            state = create_mock_state(phase=phase)
            hook = create_phase_validation_hook(state)
            hook_fn = hook.hooks[0]
            result = await hook_fn(
                create_pre_tool_use_input("Read", {"file": "test.py"}),
                "test-id",
                create_hook_context(),
            )
            assert result == {}, f"Read should be allowed in {phase.value}"

    @pytest.mark.asyncio
    async def test_allows_ask_user_in_validation(self) -> None:
        """AskUserQuestion tool is allowed in validation phase (SPEC-002)."""
        state = create_mock_state(phase=Phase.VALIDATION)
        hook = create_phase_validation_hook(state)
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("AskUserQuestion", {"questions": []}),
            "test-id",
            create_hook_context(),
        )
        assert result == {}  # Allowed in validation for human approval

    @pytest.mark.asyncio
    async def test_blocks_ask_user_in_building(self) -> None:
        """AskUserQuestion tool is blocked in building phase."""
        state = create_mock_state(phase=Phase.BUILDING)
        hook = create_phase_validation_hook(state)
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("AskUserQuestion", {"questions": []}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_allows_edit_in_building(self) -> None:
        """Edit tool is allowed in building phase."""
        state = create_mock_state(phase=Phase.BUILDING)
        hook = create_phase_validation_hook(state)
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Edit", {"file": "test.py"}),
            "test-id",
            create_hook_context(),
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_allows_edit_in_discovery(self) -> None:
        """Edit tool is now allowed in discovery phase."""
        state = create_mock_state(phase=Phase.DISCOVERY)
        hook = create_phase_validation_hook(state)
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Edit", {"file": "test.py"}),
            "test-id",
            create_hook_context(),
        )
        # Edit is now allowed in all phases
        assert result == {}

    @pytest.mark.asyncio
    async def test_allows_mcp_tools(self) -> None:
        """MCP tools are always allowed."""
        state = create_mock_state(phase=Phase.VALIDATION)
        hook = create_phase_validation_hook(state)
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("mcp__custom_tool", {}),
            "test-id",
            create_hook_context(),
        )
        assert result == {}


class TestCostLimitHook:
    """Tests for cost limit hook."""

    @pytest.mark.asyncio
    async def test_allows_under_cost_limit(self) -> None:
        """Allows tool use when under cost limit."""
        state = create_mock_state(session_cost=1.0)
        hook = create_cost_limit_hook(state, max_cost_per_iteration=2.0)
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Read", {}),
            "test-id",
            create_hook_context(),
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_blocks_over_cost_limit(self) -> None:
        """Blocks tool use when over cost limit."""
        state = create_mock_state(session_cost=2.5)
        hook = create_cost_limit_hook(state, max_cost_per_iteration=2.0)
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Read", {}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"
        reason = as_dict(result)["hookSpecificOutput"]["permissionDecisionReason"].lower()
        assert "cost limit" in reason

    @pytest.mark.asyncio
    async def test_blocks_at_exact_limit(self) -> None:
        """Blocks tool use at exact cost limit."""
        state = create_mock_state(session_cost=2.0)
        hook = create_cost_limit_hook(state, max_cost_per_iteration=2.0)
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Read", {}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"


class TestGetRalphHooks:
    """Tests for get_ralph_hooks function."""

    def test_returns_pre_tool_use_hooks(self) -> None:
        """Returns hooks dict with PreToolUse key."""
        state = create_mock_state()
        hooks = get_ralph_hooks(state)
        assert "PreToolUse" in hooks
        assert len(hooks["PreToolUse"]) > 0

    def test_includes_bash_safety_hook(self) -> None:
        """Includes bash safety hook."""
        state = create_mock_state()
        hooks = get_ralph_hooks(state)
        # Should have at least 3 hooks with all options enabled (bash, uv, phase, cost)
        assert len(hooks["PreToolUse"]) >= 3

    def test_excludes_phase_validation_when_disabled(self) -> None:
        """Excludes phase validation hook when disabled."""
        state = create_mock_state()
        hooks_with = get_ralph_hooks(state, include_phase_validation=True)
        hooks_without = get_ralph_hooks(state, include_phase_validation=False)
        assert len(hooks_without["PreToolUse"]) < len(hooks_with["PreToolUse"])

    def test_excludes_cost_limits_when_disabled(self) -> None:
        """Excludes cost limit hook when disabled."""
        state = create_mock_state()
        hooks_with = get_ralph_hooks(state, include_cost_limits=True)
        hooks_without = get_ralph_hooks(state, include_cost_limits=False)
        assert len(hooks_without["PreToolUse"]) < len(hooks_with["PreToolUse"])

    def test_respects_custom_cost_limit(self) -> None:
        """Respects custom cost limit parameter."""
        state = create_mock_state(session_cost=5.0)
        hooks = get_ralph_hooks(state, max_cost_per_iteration=10.0)
        # Should not block at 5.0 when limit is 10.0
        assert len(hooks["PreToolUse"]) > 0


class TestGetMinimalHooks:
    """Tests for get_minimal_hooks function."""

    def test_returns_pre_tool_use_hooks(self) -> None:
        """Returns hooks dict with PreToolUse key."""
        hooks = get_minimal_hooks()
        assert "PreToolUse" in hooks

    def test_includes_bash_safety(self) -> None:
        """Includes bash safety hook."""
        hooks = get_minimal_hooks()
        # Should have exactly 2 hooks (bash safety + uv enforcement)
        assert len(hooks["PreToolUse"]) == 2

    def test_no_state_required(self) -> None:
        """Can be called without state."""
        # Should not raise
        hooks = get_minimal_hooks()
        assert hooks is not None

    @pytest.mark.asyncio
    async def test_blocks_git_commit(self) -> None:
        """Blocks git commit even with minimal hooks."""
        hooks = get_minimal_hooks()
        bash_hook = hooks["PreToolUse"][0]
        hook_fn = bash_hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Bash", {"command": "git commit -m 'test'"}),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"


class TestTaskToolValidationHook:
    """Tests for Task tool validation hook."""

    def test_import_validation_hook(self) -> None:
        """Test that we can import the validation hook function."""
        from ralph.sdk_hooks import create_task_tool_validation_hook
        assert callable(create_task_tool_validation_hook)

    @pytest.fixture
    def hook(self):
        """Create Task tool validation hook."""
        from ralph.sdk_hooks import create_task_tool_validation_hook

        state = create_mock_state(phase=Phase.BUILDING)
        return create_task_tool_validation_hook(state)

    @pytest.mark.asyncio
    async def test_allows_non_task_tools(self, hook) -> None:
        """Non-Task tools are ignored."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Read", {"file": "test.py"}),
            "test-id",
            create_hook_context(),
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_blocks_invalid_subagent_type(self, hook) -> None:
        """Invalid subagent types are blocked."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Task", {
                "subagent_type": "invalid-agent",
                "prompt": "Do something",
                "description": "Test task"
            }),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"
        reason = as_dict(result)["hookSpecificOutput"]["permissionDecisionReason"]
        assert "invalid subagent" in reason.lower()

    @pytest.mark.asyncio
    async def test_blocks_subagent_not_allowed_in_phase(self) -> None:
        """Subagents not allowed in current phase are blocked."""
        from ralph.sdk_hooks import create_task_tool_validation_hook

        # Create state in DISCOVERY phase
        state = create_mock_state(phase=Phase.DISCOVERY)
        hook = create_task_tool_validation_hook(state)
        hook_fn = hook.hooks[0]

        # Try to use test-engineer (not allowed in discovery)
        result = await hook_fn(
            create_pre_tool_use_input("Task", {
                "subagent_type": "test-engineer",
                "prompt": "Run tests",
                "description": "Test task"
            }),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"
        reason = as_dict(result)["hookSpecificOutput"]["permissionDecisionReason"]
        assert "not allowed" in reason.lower()
        assert "discovery" in reason.lower()

    @pytest.mark.asyncio
    async def test_allows_valid_subagent_in_phase(self, hook) -> None:
        """Valid subagents allowed in current phase pass through."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Task", {
                "subagent_type": "code-reviewer",
                "prompt": "Review this code",
                "description": "Code review task"
            }),
            "test-id",
            create_hook_context(),
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_handles_missing_subagent_type(self, hook) -> None:
        """Handles Task tool calls missing subagent_type."""
        hook_fn = hook.hooks[0]
        result = await hook_fn(
            create_pre_tool_use_input("Task", {
                "prompt": "Do something",
                "description": "Test task"
                # Missing subagent_type
            }),
            "test-id",
            create_hook_context(),
        )
        assert as_dict(result)["hookSpecificOutput"]["permissionDecision"] == "deny"
        reason = as_dict(result)["hookSpecificOutput"]["permissionDecisionReason"]
        assert "subagent_type" in reason.lower()

    @pytest.mark.asyncio
    async def test_logs_subagent_invocation_attempts(self, hook, caplog) -> None:
        """Logs subagent invocation attempts."""
        import logging

        with caplog.at_level(logging.INFO):
            hook_fn = hook.hooks[0]
            await hook_fn(
                create_pre_tool_use_input("Task", {
                    "subagent_type": "code-reviewer",
                    "prompt": "Review code",
                    "description": "Code review"
                }),
                "test-id",
                create_hook_context(),
            )

        # Check that invocation was logged
        assert any("subagent invocation" in record.message.lower() for record in caplog.records)
        assert any("code-reviewer" in record.message for record in caplog.records)


class TestGetSafetyHooks:
    """Tests for get_safety_hooks function."""

    def test_import_safety_hooks(self) -> None:
        """Test that we can import the get_safety_hooks function."""
        from ralph.sdk_hooks import get_safety_hooks
        assert callable(get_safety_hooks)

    def test_returns_pre_tool_use_hooks(self) -> None:
        """Returns hooks dict with PreToolUse key."""
        state = create_mock_state()
        hooks = get_safety_hooks(state)
        assert "PreToolUse" in hooks
        assert len(hooks["PreToolUse"]) > 0

    def test_includes_task_validation_hook_by_default(self) -> None:
        """Includes Task tool validation hook by default."""
        state = create_mock_state()
        hooks = get_safety_hooks(state)
        # Should have at least 5 hooks with all options enabled (bash, uv, phase, cost, task)
        assert len(hooks["PreToolUse"]) >= 5

    def test_excludes_task_validation_when_disabled(self) -> None:
        """Excludes Task tool validation hook when disabled."""
        state = create_mock_state()
        hooks_with = get_safety_hooks(state, include_task_validation=True)
        hooks_without = get_safety_hooks(state, include_task_validation=False)
        assert len(hooks_without["PreToolUse"]) < len(hooks_with["PreToolUse"])

    def test_excludes_phase_validation_when_disabled(self) -> None:
        """Excludes phase validation hook when disabled."""
        state = create_mock_state()
        hooks_with = get_safety_hooks(state, include_phase_validation=True)
        hooks_without = get_safety_hooks(state, include_phase_validation=False)
        assert len(hooks_without["PreToolUse"]) < len(hooks_with["PreToolUse"])

    def test_excludes_cost_limits_when_disabled(self) -> None:
        """Excludes cost limit hook when disabled."""
        state = create_mock_state()
        hooks_with = get_safety_hooks(state, include_cost_limits=True)
        hooks_without = get_safety_hooks(state, include_cost_limits=False)
        assert len(hooks_without["PreToolUse"]) < len(hooks_with["PreToolUse"])

    def test_minimal_hooks_only_bash_and_uv(self) -> None:
        """With all optional hooks disabled, only bash and uv hooks remain."""
        state = create_mock_state()
        hooks = get_safety_hooks(
            state,
            include_phase_validation=False,
            include_cost_limits=False,
            include_task_validation=False
        )
        # Should have exactly 2 hooks (bash safety + uv enforcement)
        assert len(hooks["PreToolUse"]) == 2
