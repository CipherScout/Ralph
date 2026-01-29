"""Tests for phase transitions module."""

import pytest

from ralph.models import Phase
from ralph.transitions import (
    PHASE_ORDER,
    PhaseTransitionPrompt,
    get_next_phase,
)


class TestPhaseOrder:
    """Tests for phase ordering."""

    def test_phase_order_contains_all_phases(self) -> None:
        """Phase order contains all four phases."""
        assert len(PHASE_ORDER) == 4
        assert Phase.DISCOVERY in PHASE_ORDER
        assert Phase.PLANNING in PHASE_ORDER
        assert Phase.BUILDING in PHASE_ORDER
        assert Phase.VALIDATION in PHASE_ORDER

    def test_phase_order_is_correct(self) -> None:
        """Phases are in the correct order."""
        assert PHASE_ORDER[0] == Phase.DISCOVERY
        assert PHASE_ORDER[1] == Phase.PLANNING
        assert PHASE_ORDER[2] == Phase.BUILDING
        assert PHASE_ORDER[3] == Phase.VALIDATION


class TestGetNextPhase:
    """Tests for get_next_phase function."""

    def test_discovery_to_planning(self) -> None:
        """Discovery transitions to Planning."""
        assert get_next_phase(Phase.DISCOVERY) == Phase.PLANNING

    def test_planning_to_building(self) -> None:
        """Planning transitions to Building."""
        assert get_next_phase(Phase.PLANNING) == Phase.BUILDING

    def test_building_to_validation(self) -> None:
        """Building transitions to Validation."""
        assert get_next_phase(Phase.BUILDING) == Phase.VALIDATION

    def test_validation_returns_none(self) -> None:
        """Validation is final phase, returns None."""
        assert get_next_phase(Phase.VALIDATION) is None


class TestPhaseTransitionPrompt:
    """Tests for PhaseTransitionPrompt class."""

    def test_creates_prompt_with_defaults(self) -> None:
        """Can create prompt with default timeout."""
        from rich.console import Console

        console = Console()
        prompt = PhaseTransitionPrompt(
            console=console,
            current_phase=Phase.DISCOVERY,
            next_phase=Phase.PLANNING,
        )

        assert prompt.current_phase == Phase.DISCOVERY
        assert prompt.next_phase == Phase.PLANNING
        assert prompt.timeout_seconds == 60

    def test_creates_prompt_with_custom_timeout(self) -> None:
        """Can create prompt with custom timeout."""
        from rich.console import Console

        console = Console()
        prompt = PhaseTransitionPrompt(
            console=console,
            current_phase=Phase.PLANNING,
            next_phase=Phase.BUILDING,
            timeout_seconds=30,
        )

        assert prompt.timeout_seconds == 30

    def test_render_returns_panel(self) -> None:
        """Render method returns a Rich Panel."""
        from rich.console import Console
        from rich.panel import Panel

        console = Console()
        prompt = PhaseTransitionPrompt(
            console=console,
            current_phase=Phase.BUILDING,
            next_phase=Phase.VALIDATION,
            timeout_seconds=10,
        )

        rendered = prompt._render()
        assert isinstance(rendered, Panel)


@pytest.mark.asyncio
class TestPhaseTransitionPromptBehavior:
    """Tests for PhaseTransitionPrompt auto-continue behavior."""

    @pytest.fixture
    def prompt(self):
        """Create a PhaseTransitionPrompt instance for testing."""
        from rich.console import Console

        console = Console()
        return PhaseTransitionPrompt(
            console=console,
            current_phase=Phase.DISCOVERY,
            next_phase=Phase.PLANNING,
            timeout_seconds=2,
        )

    @pytest.fixture
    def mock_sys_stdin_isatty(self, monkeypatch):
        """Mock sys.stdin.isatty to return True (interactive mode)."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    async def test_auto_continues_after_pause(self, prompt, mock_sys_stdin_isatty, monkeypatch):
        """Prompt should auto-continue after a brief pause."""
        from unittest.mock import AsyncMock

        mock_sleep = AsyncMock()
        monkeypatch.setattr("asyncio.sleep", mock_sleep)

        result = await prompt.prompt()

        assert result is True
        mock_sleep.assert_called_once_with(2)

    async def test_non_interactive_mode_auto_continues(self, prompt, monkeypatch):
        """In non-interactive mode, should auto-continue without delay."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)

        result = await prompt.prompt()

        assert result is True

    async def test_zero_timeout_auto_continues(self, mock_sys_stdin_isatty):
        """When timeout is 0 seconds, should auto-continue immediately."""
        from rich.console import Console

        console = Console()
        prompt = PhaseTransitionPrompt(
            console=console,
            current_phase=Phase.DISCOVERY,
            next_phase=Phase.PLANNING,
            timeout_seconds=0,
        )

        result = await prompt.prompt()

        assert result is True


@pytest.mark.asyncio
class TestPromptPhaseTransition:
    """Tests for prompt_phase_transition function."""

    @pytest.fixture
    def console(self):
        """Create a Rich Console for testing."""
        from rich.console import Console
        return Console(file=open('/dev/null', 'w'))  # Suppress output during tests

    async def test_final_phase_returns_true_none(self, console):
        """When current phase is VALIDATION (final), should return (True, None)."""
        from ralph.transitions import prompt_phase_transition

        result = await prompt_phase_transition(console, Phase.VALIDATION, timeout_seconds=1)

        assert result == (True, None)

    async def test_non_final_phase_with_continue(self, console, monkeypatch):
        """When user continues from non-final phase, should return (True, next_phase)."""

        from ralph.transitions import PhaseTransitionPrompt, prompt_phase_transition

        # Mock PhaseTransitionPrompt.prompt to return True (continue)
        async def mock_prompt_true(self):
            return True

        monkeypatch.setattr(PhaseTransitionPrompt, "prompt", mock_prompt_true)

        result = await prompt_phase_transition(console, Phase.DISCOVERY, timeout_seconds=1)

        assert result == (True, Phase.PLANNING)

    async def test_non_final_phase_with_exit(self, console, monkeypatch):
        """When user exits from non-final phase, should return (False, None)."""

        from ralph.transitions import PhaseTransitionPrompt, prompt_phase_transition

        # Mock PhaseTransitionPrompt.prompt to return False (exit)
        async def mock_prompt_false(self):
            return False

        monkeypatch.setattr(PhaseTransitionPrompt, "prompt", mock_prompt_false)

        result = await prompt_phase_transition(console, Phase.PLANNING, timeout_seconds=1)

        assert result == (False, None)

    async def test_keyboard_interrupt_returns_false_none(self, console, monkeypatch):
        """When KeyboardInterrupt occurs, should return (False, None)."""
        from ralph.transitions import PhaseTransitionPrompt, prompt_phase_transition

        # Mock PhaseTransitionPrompt.prompt to raise KeyboardInterrupt
        async def mock_prompt_keyboard_interrupt(self):
            raise KeyboardInterrupt()

        monkeypatch.setattr(PhaseTransitionPrompt, "prompt", mock_prompt_keyboard_interrupt)

        result = await prompt_phase_transition(console, Phase.BUILDING, timeout_seconds=1)

        assert result == (False, None)

    async def test_final_phase_with_project_root_offers_cleanup(
        self, console, tmp_path, monkeypatch
    ):
        """When validation completes with project_root, cleanup should be offered."""
        from ralph.persistence import initialize_state
        from ralph.transitions import WorkflowCleanupPrompt, prompt_phase_transition

        # Setup state
        initialize_state(tmp_path)
        assert (tmp_path / ".ralph" / "state.json").exists()

        # Mock cleanup prompt to decline (so we can verify state preserved)
        def mock_prompt(self, project_root):
            return False, False  # decline cleanup

        monkeypatch.setattr(WorkflowCleanupPrompt, "prompt", mock_prompt)

        result = await prompt_phase_transition(
            console,
            Phase.VALIDATION,
            timeout_seconds=0,
            project_root=tmp_path,
        )

        # Should complete successfully
        assert result == (True, None)
        # State should still exist (cleanup declined)
        assert (tmp_path / ".ralph" / "state.json").exists()

    async def test_final_phase_cleanup_accepted(self, console, tmp_path, monkeypatch):
        """When user accepts cleanup, state files should be removed."""
        from ralph.persistence import initialize_state
        from ralph.transitions import WorkflowCleanupPrompt, prompt_phase_transition

        # Setup state
        initialize_state(tmp_path)
        assert (tmp_path / ".ralph" / "state.json").exists()

        # Mock cleanup prompt to accept
        def mock_prompt(self, project_root):
            return True, False  # accept cleanup, don't include memory

        monkeypatch.setattr(WorkflowCleanupPrompt, "prompt", mock_prompt)

        result = await prompt_phase_transition(
            console,
            Phase.VALIDATION,
            timeout_seconds=0,
            project_root=tmp_path,
        )

        # Should complete successfully
        assert result == (True, None)
        # State should be removed
        assert not (tmp_path / ".ralph" / "state.json").exists()

    async def test_final_phase_without_project_root_skips_cleanup(self, console):
        """When project_root is None, cleanup should be skipped."""
        from ralph.transitions import prompt_phase_transition

        # No project_root provided - should just show completion message
        result = await prompt_phase_transition(
            console,
            Phase.VALIDATION,
            timeout_seconds=0,
            project_root=None,
        )

        # Should complete successfully without errors
        assert result == (True, None)


class TestWorkflowCleanupPrompt:
    """Tests for WorkflowCleanupPrompt class."""

    @pytest.fixture
    def console(self):
        """Create a Rich Console for testing."""
        from rich.console import Console
        return Console(file=open('/dev/null', 'w'))  # Suppress output

    def test_non_interactive_mode_skips_cleanup(self, console, tmp_path, monkeypatch):
        """In non-interactive mode, cleanup should be skipped."""
        from ralph.transitions import WorkflowCleanupPrompt

        # Mock sys.stdin.isatty to return False (non-interactive)
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)

        prompt = WorkflowCleanupPrompt(console)
        should_cleanup, include_memory = prompt.prompt(tmp_path)

        assert should_cleanup is False
        assert include_memory is False

    def test_user_declines_cleanup(self, console, tmp_path, monkeypatch):
        """When user declines cleanup, should return False."""
        from ralph.transitions import WorkflowCleanupPrompt

        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        # User says no to cleanup
        monkeypatch.setattr("typer.confirm", lambda *args, **kwargs: False)

        prompt = WorkflowCleanupPrompt(console)
        should_cleanup, include_memory = prompt.prompt(tmp_path)

        assert should_cleanup is False
        assert include_memory is False

    def test_user_accepts_cleanup_without_memory(self, console, tmp_path, monkeypatch):
        """When user accepts cleanup but declines memory removal."""
        from ralph.transitions import WorkflowCleanupPrompt

        monkeypatch.setattr("sys.stdin.isatty", lambda: True)

        # Track confirm calls
        confirm_calls = []

        def mock_confirm(*args, **kwargs):
            confirm_calls.append(kwargs.get("default", True))
            if len(confirm_calls) == 1:
                return True  # Accept cleanup
            elif len(confirm_calls) == 2:
                return False  # Decline memory removal
            else:
                return True  # Final confirmation

        monkeypatch.setattr("typer.confirm", mock_confirm)

        prompt = WorkflowCleanupPrompt(console)
        should_cleanup, include_memory = prompt.prompt(tmp_path)

        assert should_cleanup is True
        assert include_memory is False

    def test_user_accepts_cleanup_with_memory(self, console, tmp_path, monkeypatch):
        """When user accepts cleanup including memory removal."""
        from ralph.transitions import WorkflowCleanupPrompt

        monkeypatch.setattr("sys.stdin.isatty", lambda: True)

        # Always return True
        monkeypatch.setattr("typer.confirm", lambda *args, **kwargs: True)

        prompt = WorkflowCleanupPrompt(console)
        should_cleanup, include_memory = prompt.prompt(tmp_path)

        assert should_cleanup is True
        assert include_memory is True

    def test_execute_cleanup_removes_files(self, console, tmp_path):
        """Execute cleanup should remove state files."""
        from ralph.persistence import initialize_state
        from ralph.transitions import WorkflowCleanupPrompt

        initialize_state(tmp_path)
        assert (tmp_path / ".ralph" / "state.json").exists()

        prompt = WorkflowCleanupPrompt(console)
        result = prompt.execute_cleanup(tmp_path, include_memory=False)

        assert result.success
        assert not (tmp_path / ".ralph" / "state.json").exists()

    def test_execute_cleanup_preserves_memory(self, console, tmp_path):
        """Execute cleanup without memory flag preserves memory files."""
        from ralph.persistence import initialize_state
        from ralph.transitions import WorkflowCleanupPrompt

        initialize_state(tmp_path)
        ralph_dir = tmp_path / ".ralph"
        (ralph_dir / "MEMORY.md").write_text("# Memory")

        prompt = WorkflowCleanupPrompt(console)
        result = prompt.execute_cleanup(tmp_path, include_memory=False)

        assert result.success
        assert (ralph_dir / "MEMORY.md").exists()

    def test_execute_cleanup_removes_memory(self, console, tmp_path):
        """Execute cleanup with memory flag removes memory files."""
        from ralph.persistence import initialize_state
        from ralph.transitions import WorkflowCleanupPrompt

        initialize_state(tmp_path)
        ralph_dir = tmp_path / ".ralph"
        (ralph_dir / "MEMORY.md").write_text("# Memory")

        prompt = WorkflowCleanupPrompt(console)
        result = prompt.execute_cleanup(tmp_path, include_memory=True)

        assert result.success
        assert not (ralph_dir / "MEMORY.md").exists()
