"""Tests for spinner animations and thread safety.

These tests verify the ThinkingSpinner and PatienceDisplay classes work
correctly through multiple start/stop cycles without race conditions.
"""

from __future__ import annotations

import threading
import time

import pytest
from rich.console import Console

from ralph.animations import (
    PatienceDisplay,
    ThinkingSpinner,
    get_random_phrase,
    get_random_thinking_verb,
    get_tool_category,
)


@pytest.fixture
def console() -> Console:
    """Create a console for testing (no terminal output)."""
    return Console(force_terminal=True, no_color=True, quiet=True)


class TestThinkingSpinner:
    """Tests for ThinkingSpinner class."""

    def test_spinner_start_stop(self, console: Console) -> None:
        """Spinner can be started and stopped cleanly."""
        spinner = ThinkingSpinner(console, show_tips=False)

        spinner.start()
        assert spinner._animation_thread is not None
        assert spinner._animation_thread.is_alive()

        spinner.stop()
        # Thread should be stopped and cleaned up
        assert spinner._live is None

    def test_spinner_multiple_cycles(self, console: Console) -> None:
        """Spinner works correctly through multiple start/stop cycles.

        This is the core bug reproduction test - the spinner was failing
        after the first couple of cycles due to thread race conditions.
        """
        spinner = ThinkingSpinner(console, show_tips=False)

        for i in range(5):
            spinner.start()
            time.sleep(0.1)  # Let animation run briefly
            spinner.stop()
            # Verify clean state after each cycle
            assert spinner._live is None, f"Live not cleaned up on cycle {i}"

    def test_spinner_rapid_cycles(self, console: Console) -> None:
        """Rapid start/stop cycles don't cause race conditions."""
        spinner = ThinkingSpinner(console, show_tips=False)

        for _ in range(20):
            spinner.start()
            spinner.stop()

        # Final state should be clean
        assert spinner._live is None

    def test_spinner_update_while_running(self, console: Console) -> None:
        """Updates work while spinner is running."""
        spinner = ThinkingSpinner(console, show_tips=False)

        spinner.start()
        try:
            spinner.update(tokens=1000, cost=0.01, message="Test message")
            assert spinner._tokens == 1000
            assert spinner._cost == 0.01
            assert spinner._tip == "Test message"
        finally:
            spinner.stop()

    def test_spinner_double_start(self, console: Console) -> None:
        """Starting an already-running spinner is safe."""
        spinner = ThinkingSpinner(console, show_tips=False)

        spinner.start()
        try:
            thread1 = spinner._animation_thread
            spinner.start()  # Should handle gracefully
            # Should either be same thread or properly replaced
            assert spinner._animation_thread is not None
        finally:
            spinner.stop()

    def test_spinner_double_stop(self, console: Console) -> None:
        """Stopping an already-stopped spinner is safe."""
        spinner = ThinkingSpinner(console, show_tips=False)

        spinner.start()
        spinner.stop()
        spinner.stop()  # Should not raise
        assert spinner._live is None

    def test_spinner_stop_without_start(self, console: Console) -> None:
        """Stopping a spinner that was never started is safe."""
        spinner = ThinkingSpinner(console, show_tips=False)
        spinner.stop()  # Should not raise
        assert spinner._live is None

    def test_spinner_no_orphan_threads(self, console: Console) -> None:
        """Verify threads are properly cleaned up."""
        initial_threads = threading.active_count()

        for _ in range(3):
            spinner = ThinkingSpinner(console, show_tips=False)
            spinner.start()
            time.sleep(0.05)
            spinner.stop()

        time.sleep(0.3)  # Allow threads to fully terminate
        final_threads = threading.active_count()

        # Should not have accumulated extra threads
        # Allow for 1 extra thread tolerance for test framework
        assert final_threads <= initial_threads + 1, (
            f"Thread leak: started with {initial_threads}, ended with {final_threads}"
        )

    def test_spinner_with_tips(self, console: Console) -> None:
        """Spinner with tips enabled works correctly."""
        spinner = ThinkingSpinner(console, show_tips=True)

        spinner.start()
        try:
            assert spinner._tip  # Should have a tip
        finally:
            spinner.stop()

    def test_spinner_render(self, console: Console) -> None:
        """Spinner renders without error."""
        spinner = ThinkingSpinner(console, show_tips=False)
        spinner._tokens = 500
        spinner._cost = 0.005

        # Should not raise
        text = spinner._render()
        assert text is not None


class TestPatienceDisplay:
    """Tests for PatienceDisplay wrapper class."""

    def test_patience_display_start_stop(self, console: Console) -> None:
        """PatienceDisplay can be started and stopped."""
        display = PatienceDisplay(console)

        display.start("thinking")
        assert display._spinner is not None

        display.stop()
        assert display._spinner is None

    def test_patience_display_multiple_cycles(self, console: Console) -> None:
        """PatienceDisplay works through multiple cycles."""
        display = PatienceDisplay(console)

        for _ in range(3):
            display.start("thinking")
            display.update("reading")
            display.stop()
            assert display._spinner is None

    def test_patience_display_update(self, console: Console) -> None:
        """PatienceDisplay update works correctly."""
        display = PatienceDisplay(console)

        display.start("thinking")
        try:
            display.update("reading")
            display.update("writing", custom_message="Custom message")
        finally:
            display.stop()


class TestHelperFunctions:
    """Tests for helper functions in animations module."""

    def test_get_random_phrase(self) -> None:
        """get_random_phrase returns valid phrases."""
        phrase = get_random_phrase("thinking")
        assert isinstance(phrase, str)
        assert len(phrase) > 0

        # Test unknown category falls back to waiting
        phrase = get_random_phrase("unknown_category")
        assert isinstance(phrase, str)

    def test_get_random_thinking_verb(self) -> None:
        """get_random_thinking_verb returns valid verbs."""
        verb = get_random_thinking_verb()
        assert isinstance(verb, str)
        assert len(verb) > 0

    def test_get_tool_category(self) -> None:
        """get_tool_category maps tools correctly."""
        assert get_tool_category("Read") == "reading"
        assert get_tool_category("Write") == "writing"
        assert get_tool_category("Bash") == "testing"
        assert get_tool_category("unknown_tool") == "thinking"
        assert get_tool_category(None) == "thinking"
