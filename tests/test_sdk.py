"""Tests for Claude SDK integration."""


import pytest

from ralph.models import Phase
from ralph.sdk import (
    BLOCKED_GIT_COMMANDS,
    BLOCKED_PACKAGE_COMMANDS,
    calculate_cost,
    calculate_max_turns,
    get_tools_for_phase,
    validate_bash_command,
    validate_tool_use_for_phase,
)


class TestCommandValidation:
    """Tests for bash command validation."""

    def test_allows_safe_commands(self) -> None:
        """Safe commands are allowed."""
        safe_commands = [
            "ls -la",
            "pwd",
            "cat file.txt",
            "echo 'hello'",
            "uv run pytest",
            "uv add requests",
            "git status",
            "git log --oneline",
            "git diff HEAD~1",
        ]
        for cmd in safe_commands:
            result = validate_bash_command(cmd)
            assert result.allowed, f"Command should be allowed: {cmd}"

    def test_blocks_git_state_operations(self) -> None:
        """Git state-changing operations are blocked."""
        blocked_commands = [
            "git commit -m 'test'",
            "git push origin main",
            "git push",
            "git pull",
            "git merge feature",
            "git rebase main",
            "git checkout feature",
            "git reset --hard",
            "git stash",
            "git cherry-pick abc123",
            "git revert HEAD",
        ]
        for cmd in blocked_commands:
            result = validate_bash_command(cmd)
            assert not result.allowed, f"Command should be blocked: {cmd}"
            assert "git" in result.reason.lower()

    def test_blocks_pip_commands(self) -> None:
        """Pip commands are blocked with uv suggestion."""
        pip_commands = [
            "pip install requests",
            "pip3 install requests",
            "pip uninstall requests",
            "pip freeze > requirements.txt",
            "python -m pip install requests",
        ]
        for cmd in pip_commands:
            result = validate_bash_command(cmd)
            assert not result.allowed, f"Command should be blocked: {cmd}"
            assert result.suggestion is not None
            assert "uv" in result.suggestion

    def test_blocks_venv_commands(self) -> None:
        """Venv commands are blocked."""
        venv_commands = [
            "python -m venv .venv",
            "python3 -m venv env",
            "virtualenv .venv",
        ]
        for cmd in venv_commands:
            result = validate_bash_command(cmd)
            assert not result.allowed, f"Command should be blocked: {cmd}"
            assert result.suggestion is not None

    def test_blocks_other_package_managers(self) -> None:
        """Other package managers are blocked."""
        other_commands = [
            "conda install numpy",
            "conda create -n myenv",
            "poetry install",
            "poetry add requests",
            "pipenv install",
        ]
        for cmd in other_commands:
            result = validate_bash_command(cmd)
            assert not result.allowed, f"Command should be blocked: {cmd}"

    def test_case_insensitive_blocking(self) -> None:
        """Blocking is case insensitive."""
        result = validate_bash_command("GIT COMMIT -m 'test'")
        assert not result.allowed

        result = validate_bash_command("PIP INSTALL requests")
        assert not result.allowed


class TestPhaseTools:
    """Tests for phase-specific tool allocation."""

    def test_discovery_phase_tools(self) -> None:
        """Discovery phase has correct tools."""
        tools = get_tools_for_phase(Phase.DISCOVERY)
        assert "Read" in tools
        assert "Glob" in tools
        assert "WebSearch" in tools
        assert "AskUserQuestion" in tools
        assert "Bash" in tools  # Now allowed for exploration
        assert "Edit" in tools  # Now allowed for all phases
        assert "TodoWrite" in tools  # Now allowed for tracking

    def test_planning_phase_tools(self) -> None:
        """Planning phase has correct tools."""
        tools = get_tools_for_phase(Phase.PLANNING)
        assert "Read" in tools
        assert "Write" in tools
        assert "ExitPlanMode" in tools
        assert "Bash" in tools  # Now allowed for analysis
        assert "Edit" in tools  # Now allowed for all phases
        assert "TodoWrite" in tools  # Now allowed for tracking

    def test_building_phase_tools(self) -> None:
        """Building phase has full tool access."""
        tools = get_tools_for_phase(Phase.BUILDING)
        assert "Read" in tools
        assert "Write" in tools
        assert "Edit" in tools
        assert "Bash" in tools
        assert "BashOutput" in tools
        assert "KillBash" in tools
        assert "TodoWrite" in tools

    def test_validation_phase_tools(self) -> None:
        """Validation phase has correct tools."""
        tools = get_tools_for_phase(Phase.VALIDATION)
        assert "Read" in tools
        assert "Bash" in tools
        assert "Task" in tools
        assert "Write" in tools  # Now allowed for validation report
        assert "Edit" in tools  # Now allowed for all phases
        assert "WebSearch" in tools  # Now allowed for all phases


class TestCalculateMaxTurns:
    """Tests for turn limit calculation."""

    def test_discovery_turns(self) -> None:
        """Discovery has moderate turns for interaction."""
        assert calculate_max_turns(Phase.DISCOVERY) == 50

    def test_planning_turns(self) -> None:
        """Planning has moderate turns."""
        assert calculate_max_turns(Phase.PLANNING) == 30

    def test_building_turns(self) -> None:
        """Building has highest turns for implementation."""
        assert calculate_max_turns(Phase.BUILDING) == 100

    def test_validation_turns(self) -> None:
        """Validation has fewer turns."""
        assert calculate_max_turns(Phase.VALIDATION) == 20


class TestCalculateCost:
    """Tests for cost calculation."""

    def test_calculate_cost_sonnet(self) -> None:
        """Cost calculated correctly for Sonnet model."""
        # 1M input, 1M output tokens
        cost = calculate_cost(1_000_000, 1_000_000, "claude-sonnet-4-20250514")
        # Expected: $3 input + $15 output = $18
        assert cost == pytest.approx(18.0, rel=0.01)

    def test_calculate_cost_opus(self) -> None:
        """Cost calculated correctly for Opus model."""
        # 1M input, 1M output tokens
        cost = calculate_cost(1_000_000, 1_000_000, "claude-opus-4-20250514")
        # Expected: $15 input + $75 output = $90
        assert cost == pytest.approx(90.0, rel=0.01)

    def test_calculate_cost_small_usage(self) -> None:
        """Cost calculated correctly for small token usage."""
        # 10K input, 5K output tokens with Sonnet
        cost = calculate_cost(10_000, 5_000, "claude-sonnet-4-20250514")
        # Expected: $0.03 input + $0.075 output = $0.105
        assert cost == pytest.approx(0.105, rel=0.01)

    def test_calculate_cost_unknown_model(self) -> None:
        """Unknown model uses default pricing."""
        cost = calculate_cost(1_000_000, 1_000_000, "unknown-model")
        # Uses default (Sonnet-like) pricing
        assert cost == pytest.approx(18.0, rel=0.01)


class TestValidateToolUseForPhase:
    """Tests for validate_tool_use_for_phase function."""

    @pytest.mark.asyncio
    async def test_validate_tool_use_allowed(self) -> None:
        """Tool allowed in phase validates successfully."""
        result = await validate_tool_use_for_phase("Read", {"file": "test.py"}, Phase.BUILDING)
        assert result.allowed

    @pytest.mark.asyncio
    async def test_validate_tool_use_wrong_phase(self) -> None:
        """Tool not allowed in phase is blocked."""
        # AskUserQuestion only allowed in discovery phase, not building
        result = await validate_tool_use_for_phase(
            "AskUserQuestion", {"questions": []}, Phase.BUILDING
        )
        assert not result.allowed
        assert "not allowed" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_validate_bash_blocked(self) -> None:
        """Blocked bash commands are rejected."""
        result = await validate_tool_use_for_phase(
            "Bash", {"command": "git commit -m 'test'"}, Phase.BUILDING
        )
        assert not result.allowed
        assert "git" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_validate_bash_allowed(self) -> None:
        """Safe bash commands are allowed."""
        result = await validate_tool_use_for_phase(
            "Bash", {"command": "uv run pytest"}, Phase.BUILDING
        )
        assert result.allowed

    @pytest.mark.asyncio
    async def test_validate_pip_blocked(self) -> None:
        """Pip commands are blocked."""
        result = await validate_tool_use_for_phase(
            "Bash", {"command": "pip install requests"}, Phase.BUILDING
        )
        assert not result.allowed
        assert "pip" in result.reason.lower() or "package" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_validate_uv_allowed(self) -> None:
        """UV commands are allowed."""
        result = await validate_tool_use_for_phase(
            "Bash", {"command": "uv add requests"}, Phase.BUILDING
        )
        assert result.allowed


class TestBlockedCommandLists:
    """Tests for blocked command lists completeness."""

    def test_git_commands_comprehensive(self) -> None:
        """Blocked git commands cover state-changing operations."""
        state_changing = ["commit", "push", "pull", "merge", "rebase", "checkout", "reset", "stash"]
        for cmd in state_changing:
            found = any(cmd in blocked for blocked in BLOCKED_GIT_COMMANDS)
            assert found, f"Missing blocked git command: {cmd}"

    def test_package_commands_comprehensive(self) -> None:
        """Blocked package commands cover major package managers."""
        package_managers = ["pip", "venv", "virtualenv", "conda", "poetry", "pipenv"]
        for pm in package_managers:
            found = any(pm in blocked for blocked in BLOCKED_PACKAGE_COMMANDS)
            assert found, f"Missing blocked package manager: {pm}"
