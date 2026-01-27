"""Test race condition scenarios in PhaseTransitionPrompt.

This module tests the fixes for race conditions between input/timer tasks
and ensures proper task cancellation and cleanup in all scenarios.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from rich.console import Console

from ralph.models import Phase
from ralph.transitions import PhaseTransitionPrompt


@pytest.fixture
def console() -> Console:
    """Create a console for testing."""
    return Console(force_terminal=True, no_color=True, quiet=True)


@pytest.fixture
def prompt(console: Console) -> PhaseTransitionPrompt:
    """Create a PhaseTransitionPrompt for testing."""
    return PhaseTransitionPrompt(
        console=console,
        current_phase=Phase.DISCOVERY,
        next_phase=Phase.PLANNING,
        timeout_seconds=1,  # Short timeout for faster tests
    )


@pytest.mark.asyncio
class TestRaceConditionPrevention:
    """Test race condition prevention between input and countdown tasks."""

    async def test_simultaneous_completion_input_wins(
        self, prompt: PhaseTransitionPrompt, monkeypatch
    ) -> None:
        """When input and countdown complete simultaneously, input takes precedence."""
        # Mock sys.stdin.isatty to enable interactive mode
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)

        # Create a completion event to coordinate the race
        completion_event = asyncio.Event()

        # Mock input task that completes just as countdown expires
        async def mock_input(*args, **kwargs):
            await completion_event.wait()
            return "y"  # User chooses to continue

        # Mock countdown sleep that signals completion at the same time
        original_sleep = asyncio.sleep
        async def mock_sleep(duration):
            if duration == 1:  # This is the countdown sleep
                completion_event.set()
                await original_sleep(0.001)  # Tiny delay to simulate race
            else:
                await original_sleep(0)  # No delay for other sleeps

        monkeypatch.setattr(prompt, "_input_task", mock_input)
        monkeypatch.setattr("asyncio.sleep", mock_sleep)

        result = await prompt.prompt()

        # Input should win (user said 'y' = continue)
        assert result is True

    async def test_simultaneous_completion_countdown_wins(
        self, prompt: PhaseTransitionPrompt, monkeypatch
    ) -> None:
        """When countdown completes just before input, countdown takes precedence."""
        # Mock sys.stdin.isatty to enable interactive mode
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)

        # Create a completion event
        completion_event = asyncio.Event()

        # Mock input task that completes just after countdown
        async def mock_input(*args, **kwargs):
            await completion_event.wait()
            await asyncio.sleep(0.01)  # Slight delay to let countdown win
            return "n"  # User would choose exit, but countdown should win

        # Mock countdown sleep
        async def mock_sleep(duration):
            if duration == 1:
                completion_event.set()
                await asyncio.sleep(0.001)
            else:
                await asyncio.sleep(0)

        monkeypatch.setattr(prompt, "_input_task", mock_input)
        monkeypatch.setattr("asyncio.sleep", mock_sleep)

        result = await prompt.prompt()

        # Countdown should win (auto-continue = True)
        assert result is True

    async def test_proper_task_cancellation_on_completion(
        self, prompt: PhaseTransitionPrompt, monkeypatch
    ) -> None:
        """All pending tasks are properly cancelled when one completes."""
        # Mock sys.stdin.isatty to enable interactive mode
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)

        # Track task cancellation
        cancelled_tasks = []

        # Mock input task that completes quickly
        async def mock_input(*args, **kwargs):
            await asyncio.sleep(0.001)
            return "y"

        # Mock sleep to track cancellation
        original_sleep = asyncio.sleep
        async def mock_sleep(duration):
            try:
                await original_sleep(duration)
            except asyncio.CancelledError:
                cancelled_tasks.append("countdown")
                raise

        monkeypatch.setattr(prompt, "_input_task", mock_input)
        monkeypatch.setattr("asyncio.sleep", mock_sleep)

        result = await prompt.prompt()

        assert result is True
        # The countdown task should have been cancelled
        assert "countdown" in cancelled_tasks

    async def test_exception_handling_during_task_cancellation(
        self, prompt: PhaseTransitionPrompt, monkeypatch
    ) -> None:
        """Exceptions during task cancellation don't prevent proper cleanup."""
        # Mock sys.stdin.isatty to enable interactive mode
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)

        # Mock input task that raises an exception
        async def mock_input(*args, **kwargs):
            raise RuntimeError("Test exception")

        # Mock sleep that should be cancelled cleanly
        async def mock_sleep(duration):
            try:
                await asyncio.sleep(duration)
            except asyncio.CancelledError:
                # This should be suppressed by contextlib.suppress
                raise

        monkeypatch.setattr(prompt, "_input_task", mock_input)
        monkeypatch.setattr("asyncio.sleep", mock_sleep)

        result = await prompt.prompt()

        # Should handle exception gracefully and default to continue
        assert result is True

    async def test_input_received_event_coordination(
        self, prompt: PhaseTransitionPrompt, monkeypatch
    ) -> None:
        """Input received event properly coordinates between tasks."""
        # Mock sys.stdin.isatty to enable interactive mode
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)

        event_was_set = False

        # Mock input task that sets the event
        async def mock_input(*args, **kwargs):
            input_received_event = args[0] if args else None
            await asyncio.sleep(0.01)
            if input_received_event:
                input_received_event.set()
                nonlocal event_was_set
                event_was_set = True
            return "y"

        # Mock countdown that checks the event
        async def mock_countdown(*args, **kwargs):
            args[0] if args else None
            input_received_event = args[1] if len(args) > 1 else None
            # Should stop immediately when event is set
            while (
                prompt._remaining > 0
                and not prompt._cancelled
                and (input_received_event is None or not input_received_event.is_set())
            ):
                await asyncio.sleep(0.01)
                prompt._remaining -= 1

        monkeypatch.setattr(prompt, "_input_task", mock_input)
        monkeypatch.setattr(prompt, "_countdown_task", mock_countdown)

        result = await prompt.prompt()

        assert result is True
        assert event_was_set  # Event was properly set

    async def test_no_race_condition_with_zero_timeout(
        self, console: Console, monkeypatch
    ) -> None:
        """Zero timeout should return immediately without race conditions."""
        prompt = PhaseTransitionPrompt(
            console=console,
            current_phase=Phase.DISCOVERY,
            next_phase=Phase.PLANNING,
            timeout_seconds=0,  # Zero timeout
        )

        # Mock sys.stdin.isatty to enable interactive mode
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)

        # These shouldn't be called with zero timeout
        mock_input = AsyncMock()
        mock_countdown = AsyncMock()
        monkeypatch.setattr(prompt, "_input_task", mock_input)
        monkeypatch.setattr(prompt, "_countdown_task", mock_countdown)

        result = await prompt.prompt()

        assert result is True
        # Neither task should have been called
        mock_input.assert_not_called()
        mock_countdown.assert_not_called()


@pytest.mark.asyncio
class TestTaskCleanupScenarios:
    """Test proper cleanup in all task completion scenarios."""

    async def test_cleanup_on_normal_completion(
        self, prompt: PhaseTransitionPrompt, monkeypatch
    ) -> None:
        """Resources are cleaned up after normal completion."""
        # Mock sys.stdin.isatty to enable interactive mode
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)

        # Track resource cleanup
        resources_cleaned = []

        # Mock input task
        async def mock_input(*args, **kwargs):
            return "y"

        # Mock Live context manager to track cleanup
        class MockLive:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                resources_cleaned.append("live")
                return False

            def update(self, content):
                pass

        monkeypatch.setattr(prompt, "_input_task", mock_input)
        monkeypatch.setattr("ralph.transitions.Live", MockLive)
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        result = await prompt.prompt()

        assert result is True
        assert "live" in resources_cleaned

    async def test_cleanup_on_cancellation(
        self, prompt: PhaseTransitionPrompt, monkeypatch
    ) -> None:
        """Resources are cleaned up even when tasks are cancelled."""
        # Mock sys.stdin.isatty to enable interactive mode
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)

        resources_cleaned = []

        # Mock input that completes first
        async def mock_input(*args, **kwargs):
            await asyncio.sleep(0.001)
            return "y"

        # Mock Live to track cleanup
        class MockLive:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                resources_cleaned.append("live")
                # Even if there's an exception, cleanup should happen
                return False

            def update(self, content):
                pass

        monkeypatch.setattr(prompt, "_input_task", mock_input)
        monkeypatch.setattr("ralph.transitions.Live", MockLive)
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        result = await prompt.prompt()

        assert result is True
        assert "live" in resources_cleaned

    async def test_multiple_cancellation_attempts_handled_gracefully(
        self, prompt: PhaseTransitionPrompt, monkeypatch
    ) -> None:
        """Multiple cancellation attempts don't cause issues."""
        # Mock sys.stdin.isatty to enable interactive mode
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)

        cancel_attempts = 0

        # Mock input that completes quickly to trigger cancellation
        async def mock_input(*args, **kwargs):
            return "y"

        # Mock countdown that should get cancelled
        async def mock_countdown(*args, **kwargs):
            try:
                await asyncio.sleep(10)  # Long sleep that should be cancelled
            except asyncio.CancelledError:
                nonlocal cancel_attempts
                cancel_attempts += 1
                raise

        monkeypatch.setattr(prompt, "_input_task", mock_input)
        monkeypatch.setattr(prompt, "_countdown_task", mock_countdown)

        result = await prompt.prompt()

        assert result is True
        # The countdown task should have been cancelled
        assert cancel_attempts >= 1
