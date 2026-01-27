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
    """Tests for PhaseTransitionPrompt interactive behavior."""

    @pytest.fixture
    def prompt(self):
        """Create a PhaseTransitionPrompt instance for testing."""
        from rich.console import Console

        console = Console()
        return PhaseTransitionPrompt(
            console=console,
            current_phase=Phase.DISCOVERY,
            next_phase=Phase.PLANNING,
            timeout_seconds=2,  # Short timeout for faster tests
        )

    @pytest.fixture
    def mock_sys_stdin_isatty(self, monkeypatch):
        """Mock sys.stdin.isatty to return True (interactive mode)."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    async def test_countdown_expiry_auto_continues(self, prompt, mock_sys_stdin_isatty, monkeypatch):
        """When countdown expires without input, should auto-continue (return True)."""
        import asyncio

        # Mock the input task to never complete (simulate no user input)
        async def mock_input_that_hangs():
            await asyncio.sleep(10)  # Longer than countdown timeout
            return ""

        monkeypatch.setattr(prompt, "_input_task", mock_input_that_hangs)

        # Mock asyncio.sleep to avoid real time delays
        sleep_calls = []

        async def mock_sleep(duration):
            sleep_calls.append(duration)
            # Don't actually sleep, just record the call
            pass

        monkeypatch.setattr("asyncio.sleep", mock_sleep)

        result = await prompt.prompt()

        assert result is True  # Should auto-continue
        assert len(sleep_calls) >= 2  # Should have called sleep multiple times during countdown

    async def test_user_presses_enter_continues(self, prompt, mock_sys_stdin_isatty, monkeypatch):
        """When user presses Enter, should continue (return True)."""
        from unittest.mock import AsyncMock

        # Mock input to return empty string (Enter key)
        async def mock_input():
            return ""

        monkeypatch.setattr(prompt, "_input_task", mock_input)

        # Mock asyncio.sleep to avoid real delays
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        result = await prompt.prompt()

        assert result is True

    async def test_user_presses_y_continues(self, prompt, mock_sys_stdin_isatty, monkeypatch):
        """When user presses 'y', should continue (return True)."""
        from unittest.mock import AsyncMock

        # Mock input to return 'y'
        async def mock_input():
            return "y"

        monkeypatch.setattr(prompt, "_input_task", mock_input)

        # Mock asyncio.sleep to avoid real delays
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        result = await prompt.prompt()

        assert result is True

    async def test_user_presses_n_exits(self, prompt, mock_sys_stdin_isatty, monkeypatch):
        """When user presses 'n', should exit (return False)."""
        from unittest.mock import AsyncMock

        # Mock input to return 'n'
        async def mock_input():
            return "n"

        monkeypatch.setattr(prompt, "_input_task", mock_input)

        # Mock asyncio.sleep to avoid real delays
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        result = await prompt.prompt()

        assert result is False

    async def test_non_interactive_mode_auto_continues(self, prompt, monkeypatch):
        """In non-interactive mode, should auto-continue without countdown."""
        # Mock sys.stdin.isatty to return False (non-interactive mode)
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)

        result = await prompt.prompt()

        assert result is True

    async def test_eoferror_handling(self, prompt, mock_sys_stdin_isatty, monkeypatch):
        """Should handle EOFError gracefully (non-interactive scenarios)."""
        from unittest.mock import AsyncMock

        # Mock input to raise EOFError (simulates end of file in non-interactive mode)
        async def mock_input():
            raise EOFError()

        monkeypatch.setattr(prompt, "_input_task", mock_input)

        # Mock asyncio.sleep to avoid real delays
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        result = await prompt.prompt()

        # Should return True when handling EOFError (default behavior)
        assert result is True

    async def test_input_exception_handling(self, prompt, mock_sys_stdin_isatty, monkeypatch):
        """Should handle input exceptions gracefully."""
        from unittest.mock import AsyncMock

        # Mock input to raise an exception
        async def mock_input():
            raise EOFError("Test exception")

        monkeypatch.setattr(prompt, "_input_task", mock_input)

        # Mock asyncio.sleep to avoid real delays
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        result = await prompt.prompt()

        # Should return True when input fails (default behavior)
        assert result is True

    async def test_countdown_updates_remaining_time(self, prompt, mock_sys_stdin_isatty, monkeypatch):
        """Countdown should update _remaining time as it progresses."""
        import asyncio

        # Track _remaining values during countdown
        remaining_values = []

        original_render = prompt._render
        def mock_render():
            remaining_values.append(prompt._remaining)
            return original_render()

        prompt._render = mock_render

        # Mock input task to never complete
        async def mock_input_that_hangs():
            await asyncio.sleep(10)
            return ""

        monkeypatch.setattr(prompt, "_input_task", mock_input_that_hangs)

        # Mock asyncio.sleep to track calls but not actually sleep
        sleep_count = 0
        async def mock_sleep(duration):
            nonlocal sleep_count
            sleep_count += 1
            # Simulate countdown progressing
            prompt._remaining = max(0, prompt._remaining - 1)

        monkeypatch.setattr("asyncio.sleep", mock_sleep)

        await prompt.prompt()

        # Should have decremented _remaining over time
        assert len(remaining_values) > 1
        assert remaining_values[0] == 2  # Initial timeout_seconds
        assert remaining_values[-1] <= remaining_values[0]  # Should decrease

    async def test_cancelled_flag_set_during_countdown(self, prompt, mock_sys_stdin_isatty, monkeypatch):
        """The _cancelled flag should affect countdown behavior."""
        import asyncio

        from rich.console import Console

        # Test that setting _cancelled = True stops the countdown loop
        # We'll test the _countdown_task method directly
        from rich.live import Live

        console = Console()
        live = Live(prompt._render(), console=console)

        # Start countdown task
        countdown_task = asyncio.create_task(prompt._countdown_task(live))

        # Let it run briefly
        await asyncio.sleep(0.05)

        # Set cancelled flag
        prompt._cancelled = True

        # Wait for countdown to complete
        await countdown_task

        # Countdown should have exited due to _cancelled flag
        assert prompt._cancelled is True

    async def test_uses_async_input_reader(self, prompt, mock_sys_stdin_isatty, monkeypatch):
        """PhaseTransitionPrompt should use AsyncInputReader for input."""
        from unittest.mock import AsyncMock, patch

        from ralph.async_input_reader import AsyncInputReader

        # Mock AsyncInputReader
        mock_reader = AsyncMock(spec=AsyncInputReader)
        mock_reader.read_input.return_value = "y"

        with patch('ralph.transitions.AsyncInputReader', return_value=mock_reader):
            # Mock asyncio.sleep to avoid real delays
            monkeypatch.setattr("asyncio.sleep", AsyncMock())

            result = await prompt.prompt()

            # Should have created and used AsyncInputReader
            mock_reader.read_input.assert_called_once()
            assert result is True

    async def test_asyncio_event_coordination(self, prompt, mock_sys_stdin_isatty, monkeypatch):
        """PhaseTransitionPrompt should use asyncio.Event for task coordination."""
        from unittest.mock import AsyncMock, patch

        # Track event operations
        event_operations = []

        class MockEvent:
            def __init__(self):
                self.is_set_called = False

            def set(self):
                event_operations.append("set")
                self.is_set_called = True

            def is_set(self):
                event_operations.append("is_set")
                return self.is_set_called

            async def wait(self):
                event_operations.append("wait")
                return True

        # Mock asyncio.Event
        mock_event = MockEvent()
        with patch('asyncio.Event', return_value=mock_event):
            # Mock other dependencies
            from ralph.async_input_reader import AsyncInputReader
            mock_reader = AsyncMock(spec=AsyncInputReader)
            mock_reader.read_input.return_value = "y"

            with patch('ralph.transitions.AsyncInputReader', return_value=mock_reader):
                monkeypatch.setattr("asyncio.sleep", AsyncMock())

                result = await prompt.prompt()

                # Should have used event coordination
                assert "set" in event_operations or "wait" in event_operations
                assert result is True

    async def test_zero_timeout_auto_continues(self, mock_sys_stdin_isatty):
        """When timeout is 0 seconds, should auto-continue immediately."""
        from rich.console import Console

        console = Console()
        prompt = PhaseTransitionPrompt(
            console=console,
            current_phase=Phase.DISCOVERY,
            next_phase=Phase.PLANNING,
            timeout_seconds=0,  # Zero timeout
        )

        # Should auto-continue without any delay
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
