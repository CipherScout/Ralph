"""Test race condition scenarios in PhaseTransitionPrompt.

This module tests that the simplified auto-continue phase transition
behaves correctly under concurrent and edge-case scenarios.
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
        timeout_seconds=1,
    )


@pytest.mark.asyncio
class TestAutoContiueBehavior:
    """Test auto-continue behavior under various conditions."""

    async def test_concurrent_prompt_calls(
        self, console: Console, monkeypatch
    ) -> None:
        """Multiple concurrent prompt calls all return True."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        prompts = [
            PhaseTransitionPrompt(
                console=console,
                current_phase=Phase.DISCOVERY,
                next_phase=Phase.PLANNING,
            )
            for _ in range(5)
        ]

        results = await asyncio.gather(*(p.prompt() for p in prompts))

        assert all(r is True for r in results)

    async def test_zero_timeout_returns_immediately(
        self, console: Console, monkeypatch
    ) -> None:
        """Zero timeout should return immediately without race conditions."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)

        prompt = PhaseTransitionPrompt(
            console=console,
            current_phase=Phase.DISCOVERY,
            next_phase=Phase.PLANNING,
            timeout_seconds=0,
        )

        result = await prompt.prompt()
        assert result is True

    async def test_non_interactive_returns_immediately(
        self, prompt: PhaseTransitionPrompt, monkeypatch
    ) -> None:
        """Non-interactive mode returns immediately without delay."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)

        result = await prompt.prompt()
        assert result is True

    async def test_interactive_mode_sleeps_then_continues(
        self, prompt: PhaseTransitionPrompt, monkeypatch
    ) -> None:
        """Interactive mode sleeps briefly then auto-continues."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        mock_sleep = AsyncMock()
        monkeypatch.setattr("asyncio.sleep", mock_sleep)

        result = await prompt.prompt()

        assert result is True
        mock_sleep.assert_called_once_with(2)
