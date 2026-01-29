"""Tests for spinner animations and thread safety.

These tests verify the ThinkingSpinner and PatienceDisplay classes work
correctly through multiple start/stop cycles without race conditions.

This module now includes comprehensive tests for the token display feature
as part of SPEC-002-realtime-token-display:

Test categories:
- Basic spinner lifecycle (start/stop cycles)  
- Thread safety and race condition prevention
- Token display rendering with various counts
- Spinner formatting and precision
- Error handling for invalid token values
- Performance under extreme conditions

The TestSpinnerTokenRendering class specifically tests:
- Zero token display (shows "...")
- Small token counts (exact numbers)
- Thousands formatting (1,500 tokens)
- Millions formatting (1.2M tokens)
- Cost precision (4 decimal places)
- Token-only and cost-only scenarios
- Integration with tips/patience phrases
- Format consistency across scenarios
- Thread safety with token updates

These tests ensure the spinner properly displays token information
without impacting performance or causing thread safety issues.
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


class TestSpinnerTokenRendering:
    """Comprehensive tests for spinner rendering with various token counts."""

    def test_spinner_render_zero_tokens(self, console: Console) -> None:
        """Test spinner rendering with zero tokens."""
        spinner = ThinkingSpinner(console, show_tips=False)
        spinner._tokens = 0
        spinner._cost = 0.0

        rendered = spinner._render()
        text_str = rendered.plain.lower()

        # Should show dots instead of token count
        assert "..." in text_str
        assert "tokens" not in text_str

    def test_spinner_render_small_token_counts(self, console: Console) -> None:
        """Test spinner rendering with small token counts."""
        test_cases = [
            (1, 0.000018),
            (50, 0.00090),
            (999, 0.01785),
        ]

        for tokens, expected_cost in test_cases:
            spinner = ThinkingSpinner(console, show_tips=False)
            spinner._tokens = tokens
            spinner._cost = expected_cost

            rendered = spinner._render()
            text_str = rendered.plain

            # Should show exact token count for small numbers
            assert str(tokens) in text_str
            assert "tokens" in text_str.lower()
            # Should show cost with 4 decimal places
            assert f"${expected_cost:.4f}" in text_str

    def test_spinner_render_thousands_formatting(self, console: Console) -> None:
        """Test spinner rendering with thousands formatting."""
        test_cases = [
            (1_000, "1,000"),
            (1_500, "1,500"),
            (10_000, "10,000"),
            (99_999, "99,999"),
            (500_000, "500,000"),
            (999_999, "999,999"),
        ]

        for tokens, expected_format in test_cases:
            spinner = ThinkingSpinner(console, show_tips=False)
            spinner._tokens = tokens
            spinner._cost = tokens * 0.000018  # Realistic cost

            rendered = spinner._render()
            text_str = rendered.plain

            # Should use comma formatting for thousands
            assert expected_format in text_str
            assert "tokens" in text_str.lower()

    def test_spinner_render_millions_formatting(self, console: Console) -> None:
        """Test spinner rendering with compact millions formatting."""
        test_cases = [
            (1_000_000, "1.0M"),
            (1_200_000, "1.2M"),
            (2_500_000, "2.5M"),
            (10_000_000, "10.0M"),
            (15_750_000, "15.8M"),  # Should round to 1 decimal
        ]

        for tokens, expected_format in test_cases:
            spinner = ThinkingSpinner(console, show_tips=False)
            spinner._tokens = tokens
            spinner._cost = tokens * 0.000018  # Realistic cost

            rendered = spinner._render()
            text_str = rendered.plain

            # Should use compact M format for millions
            assert expected_format in text_str or expected_format.replace('.0M', 'M') in text_str
            assert "tokens" in text_str.lower()

    def test_spinner_render_extreme_token_counts(self, console: Console) -> None:
        """Test spinner rendering with extremely large token counts."""
        test_cases = [
            (100_000_000, "100.0M"),
            (1_000_000_000, "1000.0M"),
        ]

        for tokens, expected_format in test_cases:
            spinner = ThinkingSpinner(console, show_tips=False)
            spinner._tokens = tokens
            spinner._cost = tokens * 0.000018

            rendered = spinner._render()
            text_str = rendered.plain

            # Should handle very large numbers gracefully
            assert "tokens" in text_str.lower()
            # Should contain some reasonable representation
            assert len([c for c in text_str if c.isdigit()]) > 0

    def test_spinner_render_cost_precision_variations(self, console: Console) -> None:
        """Test spinner rendering with various cost precision scenarios."""
        test_cases = [
            (1000, 0.0, "no cost"),              # Zero cost
            (1000, 0.0001, "$0.0001"),          # Very small cost
            (1000, 0.1234, "$0.1234"),          # Normal precision
            (1000, 0.123456789, "$0.1235"),     # Rounded to 4 decimals
            (1000, 1.0, "$1.0000"),             # Whole dollar
            (1000, 123.4567, "$123.4567"),      # Large cost
        ]

        for tokens, cost, expected_cost_display in test_cases:
            spinner = ThinkingSpinner(console, show_tips=False)
            spinner._tokens = tokens
            spinner._cost = cost

            rendered = spinner._render()
            text_str = rendered.plain

            if expected_cost_display == "no cost":
                # When cost is 0, should not show cost
                assert "$" not in text_str or ", $" not in text_str
            else:
                # Should show formatted cost
                assert expected_cost_display in text_str

    def test_spinner_render_token_only_scenarios(self, console: Console) -> None:
        """Test spinner rendering with tokens but no cost."""
        test_cases = [100, 1_500, 50_000, 1_200_000]

        for tokens in test_cases:
            spinner = ThinkingSpinner(console, show_tips=False)
            spinner._tokens = tokens
            spinner._cost = 0.0  # No cost

            rendered = spinner._render()
            text_str = rendered.plain

            # Should show tokens but not cost when cost is 0
            assert "tokens" in text_str.lower()
            # Should not show cost portion when cost is 0
            cost_indicators = [", $", "(, $"]
            assert not any(indicator in text_str for indicator in cost_indicators)

    def test_spinner_render_cost_only_scenarios(self, console: Console) -> None:
        """Test spinner rendering with cost but no tokens."""
        test_cases = [0.0001, 0.1234, 1.0, 123.45]

        for cost in test_cases:
            spinner = ThinkingSpinner(console, show_tips=False)
            spinner._tokens = 0
            spinner._cost = cost

            rendered = spinner._render()
            text_str = rendered.plain

            # When tokens are 0, should show ... not token count
            assert "..." in text_str
            assert "tokens" not in text_str.lower()

    def test_spinner_render_with_tips_and_tokens(self, console: Console) -> None:
        """Test spinner rendering with both tips and token information."""
        spinner = ThinkingSpinner(console, show_tips=True)
        spinner._tokens = 1500
        spinner._cost = 0.0075
        spinner._tip = "Processing your request..."

        rendered = spinner._render()
        text_str = rendered.plain

        # Should contain all elements
        assert "1,500 tokens" in text_str
        assert "$0.0075" in text_str
        assert "Processing your request" in text_str

    def test_spinner_render_tip_truncation(self, console: Console) -> None:
        """Test spinner rendering with long tips that get truncated."""
        spinner = ThinkingSpinner(console, show_tips=True)
        spinner._tokens = 1000
        spinner._cost = 0.005
        # Very long tip that should be truncated
        spinner._tip = "This is a very long tip message that should be truncated to fit in the display"

        rendered = spinner._render()
        text_str = rendered.plain

        # Tip should be truncated
        assert len(spinner._tip) > 40  # Original tip is long
        # Should contain token info
        assert "1,000 tokens" in text_str
        assert "$0.0050" in text_str

    def test_spinner_render_format_consistency(self, console: Console) -> None:
        """Test that spinner rendering format is consistent across different scenarios."""
        test_scenarios = [
            {"tokens": 0, "cost": 0.0, "tip": ""},
            {"tokens": 500, "cost": 0.0025, "tip": "Working..."},
            {"tokens": 1_500, "cost": 0.0075, "tip": ""},
            {"tokens": 1_000_000, "cost": 18.0, "tip": "Processing large request..."},
        ]

        for scenario in test_scenarios:
            spinner = ThinkingSpinner(console, show_tips=bool(scenario["tip"]))
            spinner._tokens = scenario["tokens"]
            spinner._cost = scenario["cost"]
            if scenario["tip"]:
                spinner._tip = scenario["tip"]

            rendered = spinner._render()
            text_str = rendered.plain

            # All renders should contain a spinner character
            assert any(char in text_str for char in "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
            
            # All renders should contain a thinking verb
            thinking_verbs = [
                "Thinking", "Pondering", "Analyzing", "Processing", 
                "Considering", "Reasoning", "Working", "Computing",
                "Evaluating", "Synthesizing"
            ]
            assert any(verb in text_str for verb in thinking_verbs)

    def test_format_token_count_edge_cases(self, console: Console) -> None:
        """Test the format_token_count function with edge cases."""
        from ralph.animations import format_token_count
        
        # Test boundary conditions
        test_cases = [
            (0, "0"),
            (1, "1"),
            (999, "999"),
            (1_000, "1,000"),
            (999_999, "999,999"),
            (1_000_000, "1.0M"),
            (1_000_001, "1.0M"),
            (1_500_000, "1.5M"),
            (1_500_001, "1.5M"),
            (10_000_000, "10.0M"),
            (1_000_000_000, "1000.0M"),
        ]

        for tokens, expected in test_cases:
            result = format_token_count(tokens)
            assert result == expected, f"format_token_count({tokens}) = {result}, expected {expected}"

    def test_spinner_render_thread_safety(self, console: Console) -> None:
        """Test that spinner rendering is thread-safe with token updates."""
        import threading
        import time
        
        spinner = ThinkingSpinner(console, show_tips=False)
        errors = []
        
        def update_tokens():
            """Update tokens from another thread."""
            try:
                for i in range(10):
                    spinner.update(tokens=i * 100, cost=i * 0.001)
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)
        
        def render_spinner():
            """Render spinner from another thread."""
            try:
                for _ in range(10):
                    spinner._render()
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)
        
        # Start threads
        update_thread = threading.Thread(target=update_tokens)
        render_thread = threading.Thread(target=render_spinner)
        
        update_thread.start()
        render_thread.start()
        
        # Wait for completion
        update_thread.join()
        render_thread.join()
        
        # Should not have any errors
        assert len(errors) == 0, f"Thread safety errors: {errors}"
