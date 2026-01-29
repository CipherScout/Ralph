"""Tests for CLI token display feature (SPEC-002-realtime-token-display).

This module contains comprehensive tests for the real-time token usage display
feature that shows token counts and costs in the CLI spinner during iterations.

Test categories:
- RalphLiveDisplay token handling for ITERATION_END events
- ThinkingSpinner token display formatting and rendering
- Integration tests for complete event flow from SDK to display
- Event data validation and error handling
- Token data extraction and type conversion

The tests verify that the token display feature:
1. Updates spinner with token and cost data from events
2. Shows token information in console output 
3. Handles large token counts with proper formatting
4. Accumulates totals across multiple iterations
5. Gracefully handles missing or malformed token data
6. Integrates properly with the SDK event streaming system

Key verification criteria from SPEC-002:
- Token count displayed alongside spinner animation
- Token count updates in real-time as streaming progresses  
- Cost calculated using current Claude pricing
- Counters reset at each iteration start
- Display integrated with existing ThinkingSpinner
- All existing tests continue to pass
- No performance impact on iteration processing
"""

from __future__ import annotations

import pytest
from rich.console import Console

from ralph.cli import RalphLiveDisplay
from ralph.events import StreamEvent, StreamEventType


class TestRalphLiveDisplayTokens:
    """Tests for RalphLiveDisplay token handling in ITERATION_END events."""

    @pytest.fixture
    def console(self) -> Console:
        """Create a test console."""
        return Console(force_terminal=True, no_color=True, quiet=True)

    @pytest.fixture
    def display(self, console: Console) -> RalphLiveDisplay:
        """Create a RalphLiveDisplay for testing."""
        return RalphLiveDisplay(console, verbosity=1)

    def test_iteration_end_updates_spinner_with_tokens(
        self, display: RalphLiveDisplay
    ) -> None:
        """ITERATION_END event should update spinner with tokens and cost."""
        # Mock the spinner update method
        update_calls = []
        display._update_spinner = lambda tokens=0, cost=0.0: update_calls.append(
            {"tokens": tokens, "cost": cost}
        )

        # Mock spinner stop
        stop_calls = []
        display._stop_spinner = lambda: stop_calls.append(True)

        # Create ITERATION_END event with token data
        event = StreamEvent(
            type=StreamEventType.ITERATION_END,
            iteration=1,
            phase="building",
            data={
                "success": True,
                "tokens_used": 1500,
                "cost_usd": 0.0075,
            },
        )

        display.handle_event(event)

        # Should have stopped spinner
        assert len(stop_calls) == 1

        # Should have called update_spinner with token data
        assert len(update_calls) == 1
        assert update_calls[0]["tokens"] == 1500
        assert update_calls[0]["cost"] == 0.0075

    def test_iteration_end_shows_token_display_in_output(
        self, display: RalphLiveDisplay
    ) -> None:
        """ITERATION_END should show tokens and cost in console output."""
        # Create ITERATION_END event with token data
        event = StreamEvent(
            type=StreamEventType.ITERATION_END,
            iteration=1,
            phase="building",
            data={
                "success": True,
                "tokens_used": 2500,
                "cost_usd": 0.0125,
            },
        )

        # Capture console output by mocking print
        output_lines = []
        original_print = display.console.print
        display.console.print = lambda *args, **kwargs: output_lines.append(str(args[0]) if args else "")

        try:
            display.handle_event(event)

            # Should have printed token information
            output = " ".join(output_lines).lower()
            assert "2,500 tokens" in output or "2500 tokens" in output
            assert "$0.0125" in output
        finally:
            display.console.print = original_print

    def test_iteration_end_handles_large_token_counts(
        self, display: RalphLiveDisplay
    ) -> None:
        """ITERATION_END should format large token counts nicely."""
        # Create ITERATION_END event with large token count
        event = StreamEvent(
            type=StreamEventType.ITERATION_END,
            iteration=1,
            phase="building",
            data={
                "success": True,
                "tokens_used": 1_250_000,  # 1.25M tokens
                "cost_usd": 6.25,
            },
        )

        # Capture console output
        output_lines = []
        original_print = display.console.print
        display.console.print = lambda *args, **kwargs: output_lines.append(str(args[0]) if args else "")

        try:
            display.handle_event(event)

            # Should format large numbers with commas
            output = " ".join(output_lines)
            # Python's :, formatter should add commas
            assert "1,250,000" in output
            assert "$6.2500" in output
        finally:
            display.console.print = original_print

    def test_iteration_end_updates_display_totals(
        self, display: RalphLiveDisplay
    ) -> None:
        """ITERATION_END should update display total tokens and cost."""
        # First iteration
        event1 = StreamEvent(
            type=StreamEventType.ITERATION_END,
            iteration=1,
            phase="building",
            data={
                "success": True,
                "tokens_used": 1000,
                "cost_usd": 0.005,
            },
        )

        display.handle_event(event1)
        assert display._total_tokens == 1000
        assert display._total_cost == 0.005

        # Second iteration - should accumulate
        event2 = StreamEvent(
            type=StreamEventType.ITERATION_END,
            iteration=2,
            phase="building",
            data={
                "success": True,
                "tokens_used": 1500,
                "cost_usd": 0.0075,
            },
        )

        display.handle_event(event2)
        assert display._total_tokens == 2500
        assert display._total_cost == 0.0125

    def test_update_spinner_method_exists(
        self, display: RalphLiveDisplay
    ) -> None:
        """_update_spinner method should exist and accept tokens/cost parameters."""
        # Should not raise an error
        display._update_spinner(tokens=100, cost=0.001)

        # Method should exist on the class
        assert hasattr(display, "_update_spinner")
        assert callable(display._update_spinner)


class TestThinkingSpinnerTokenDisplay:
    """Tests for ThinkingSpinner token display formatting."""

    @pytest.fixture
    def console(self) -> Console:
        """Create a test console."""
        return Console(force_terminal=True, no_color=True, quiet=True)

    def test_spinner_update_with_tokens_and_cost(self, console: Console) -> None:
        """ThinkingSpinner should update display with tokens and cost."""
        from ralph.animations import ThinkingSpinner

        spinner = ThinkingSpinner(console, show_tips=False)

        # Update with token data
        spinner.update(tokens=1500, cost=0.0075)

        assert spinner._tokens == 1500
        assert spinner._cost == 0.0075

    def test_spinner_render_with_tokens(self, console: Console) -> None:
        """ThinkingSpinner should render tokens and cost in display."""
        from ralph.animations import ThinkingSpinner

        spinner = ThinkingSpinner(console, show_tips=False)
        spinner._tokens = 1500
        spinner._cost = 0.0075

        rendered = spinner._render()
        text_str = rendered.plain.lower()

        # Should include token count and cost
        assert "1,500 tokens" in text_str
        assert "$0.0075" in text_str

    def test_spinner_render_large_token_format(self, console: Console) -> None:
        """ThinkingSpinner should format large token counts nicely."""
        from ralph.animations import ThinkingSpinner

        spinner = ThinkingSpinner(console, show_tips=False)

        # Test different large numbers - should use compact format for millions
        test_cases = [
            (1_200_000, "1.2M"),  # Should use compact format
            (2_500_000, "2.5M"),  # Should use compact format
            (500_000, "500,000"),  # Should use comma format (less than 1M)
            (1_000, "1,000"),  # Should use comma format
        ]

        for tokens, expected_format in test_cases:
            spinner._tokens = tokens
            rendered = spinner._render()
            text_str = rendered.plain

            # Should format correctly
            assert expected_format in text_str, f"Expected {expected_format} in {text_str}"

    def test_spinner_render_no_tokens_shows_dots(self, console: Console) -> None:
        """ThinkingSpinner should show '...' when no tokens."""
        from ralph.animations import ThinkingSpinner

        spinner = ThinkingSpinner(console, show_tips=False)
        spinner._tokens = 0
        spinner._cost = 0.0

        rendered = spinner._render()
        text_str = rendered.plain

        # Should show dots instead of token count
        assert "..." in text_str
        assert "tokens" not in text_str.lower()

    def test_spinner_render_cost_precision(self, console: Console) -> None:
        """ThinkingSpinner should show cost with 4 decimal places."""
        from ralph.animations import ThinkingSpinner

        spinner = ThinkingSpinner(console, show_tips=False)
        spinner._tokens = 1000
        spinner._cost = 0.12345678  # More precision than needed

        rendered = spinner._render()
        text_str = rendered.plain

        # Should format to 4 decimal places
        assert "$0.1235" in text_str

    def test_spinner_render_tokens_without_cost(self, console: Console) -> None:
        """ThinkingSpinner should show tokens even without cost."""
        from ralph.animations import ThinkingSpinner

        spinner = ThinkingSpinner(console, show_tips=False)
        spinner._tokens = 500
        spinner._cost = 0.0

        rendered = spinner._render()
        text_str = rendered.plain.lower()

        # Should show token count
        assert "500 tokens" in text_str
        # Should not show cost when 0
        assert ")" not in text_str or ", $" not in text_str


class TestTokenFormatting:
    """Tests for token formatting utilities."""

    def test_large_number_formatting(self) -> None:
        """Test that Python's built-in formatting works for large numbers."""
        # Test that the :, formatter works as expected
        assert f"{1_250_000:,}" == "1,250,000"
        assert f"{2_500_000:,}" == "2,500,000"
        assert f"{500_000:,}" == "500,000"
        assert f"{1_000:,}" == "1,000"
        assert f"{500:,}" == "500"  # No comma for small numbers


class TestSDKEventFlowIntegration:
    """Integration tests for event flow from SDK to display components."""

    @pytest.fixture
    def console(self) -> Console:
        """Create a test console."""
        return Console(force_terminal=True, no_color=True, quiet=True)

    @pytest.fixture
    def display(self, console: Console) -> RalphLiveDisplay:
        """Create a RalphLiveDisplay for testing."""
        return RalphLiveDisplay(console, verbosity=2)

    def test_complete_iteration_event_flow(
        self, display: RalphLiveDisplay
    ) -> None:
        """Test complete flow from iteration start to end with token tracking."""
        # Track all state changes
        state_changes = []
        
        # Mock spinner methods to track calls
        original_start_spinner = display._start_spinner
        original_stop_spinner = display._stop_spinner
        original_update_spinner = display._update_spinner
        
        def track_start_spinner():
            state_changes.append("start_spinner")
            original_start_spinner()
            
        def track_stop_spinner():
            state_changes.append("stop_spinner")
            original_stop_spinner()
            
        def track_update_spinner(tokens=0, cost=0.0):
            state_changes.append(f"update_spinner({tokens}, {cost})")
            original_update_spinner(tokens, cost)
        
        display._start_spinner = track_start_spinner
        display._stop_spinner = track_stop_spinner
        display._update_spinner = track_update_spinner

        # Simulate complete iteration flow
        # 1. Iteration start
        start_event = StreamEvent(
            type=StreamEventType.ITERATION_START,
            iteration=1,
            phase="building",
            data={}
        )
        display.handle_event(start_event)

        # 2. Tool use start
        tool_start_event = StreamEvent(
            type=StreamEventType.TOOL_USE_START,
            iteration=1,
            phase="building",
            data={"tool_name": "Read", "input": {"file_path": "test.py"}}
        )
        display.handle_event(tool_start_event)

        # 3. Tool use end
        tool_end_event = StreamEvent(
            type=StreamEventType.TOOL_USE_END,
            iteration=1,
            phase="building",
            data={"tool_name": "Read", "output": "file contents"}
        )
        display.handle_event(tool_end_event)

        # 4. Iteration end with token data
        end_event = StreamEvent(
            type=StreamEventType.ITERATION_END,
            iteration=1,
            phase="building",
            data={
                "success": True,
                "tokens_used": 1500,
                "cost_usd": 0.0075,
            }
        )
        display.handle_event(end_event)

        # Verify the complete flow
        assert "start_spinner" in state_changes
        assert "stop_spinner" in state_changes
        assert "update_spinner(1500, 0.0075)" in state_changes
        
        # Verify display state
        assert display._total_tokens == 1500
        assert display._total_cost == 0.0075

    def test_multiple_iteration_accumulation(
        self, display: RalphLiveDisplay
    ) -> None:
        """Test token accumulation across multiple iterations."""
        iterations = [
            {"tokens": 1000, "cost": 0.005},
            {"tokens": 2000, "cost": 0.010},
            {"tokens": 1500, "cost": 0.0075},
        ]

        for i, iteration_data in enumerate(iterations, 1):
            event = StreamEvent(
                type=StreamEventType.ITERATION_END,
                iteration=i,
                phase="building",
                data={
                    "success": True,
                    "tokens_used": iteration_data["tokens"],
                    "cost_usd": iteration_data["cost"],
                }
            )
            display.handle_event(event)

        # Verify accumulation
        expected_tokens = sum(data["tokens"] for data in iterations)
        expected_cost = sum(data["cost"] for data in iterations)
        
        assert display._total_tokens == expected_tokens
        assert display._total_cost == expected_cost

    def test_event_flow_with_missing_token_data(
        self, display: RalphLiveDisplay
    ) -> None:
        """Test event flow when token data is missing from events."""
        # Track update calls
        update_calls = []
        display._update_spinner = lambda tokens=0, cost=0.0: update_calls.append(
            {"tokens": tokens, "cost": cost}
        )

        # Event without token data
        event = StreamEvent(
            type=StreamEventType.ITERATION_END,
            iteration=1,
            phase="building",
            data={"success": True}  # No token data
        )
        
        display.handle_event(event)

        # Should handle gracefully with zeros
        assert len(update_calls) == 1
        assert update_calls[0]["tokens"] == 0
        assert update_calls[0]["cost"] == 0.0

    def test_event_flow_with_malformed_token_data(
        self, display: RalphLiveDisplay
    ) -> None:
        """Test event flow with malformed token data."""
        # Track update calls
        update_calls = []
        display._update_spinner = lambda tokens=0, cost=0.0: update_calls.append(
            {"tokens": tokens, "cost": cost}
        )

        # Event with malformed token data
        event = StreamEvent(
            type=StreamEventType.ITERATION_END,
            iteration=1,
            phase="building",
            data={
                "success": True,
                "tokens_used": "not_a_number",  # Invalid
                "cost_usd": None,  # Invalid
            }
        )
        
        display.handle_event(event)

        # Should handle gracefully by defaulting to zeros
        assert len(update_calls) == 1
        assert update_calls[0]["tokens"] == 0
        assert update_calls[0]["cost"] == 0.0

    def test_spinner_lifecycle_with_token_updates(
        self, display: RalphLiveDisplay
    ) -> None:
        """Test spinner lifecycle with real-time token updates."""
        from unittest.mock import patch

        # Mock the ThinkingSpinner to track its state
        spinner_state = {"started": False, "stopped": False, "tokens": 0, "cost": 0.0}

        class MockSpinner:
            def start(self):
                spinner_state["started"] = True
                spinner_state["stopped"] = False

            def stop(self):
                spinner_state["stopped"] = True
                spinner_state["started"] = False

            def update(self, tokens=None, cost=None, message=None):
                if tokens is not None:
                    spinner_state["tokens"] = tokens
                if cost is not None:
                    spinner_state["cost"] = cost

        mock_spinner = MockSpinner()

        with patch("ralph.cli.ThinkingSpinner", return_value=mock_spinner):
            # Test complete lifecycle
            # Start iteration
            start_event = StreamEvent(
                type=StreamEventType.ITERATION_START,
                iteration=1,
                phase="building",
                data={}
            )
            display.handle_event(start_event)
            assert spinner_state["started"]

            # End iteration with tokens
            end_event = StreamEvent(
                type=StreamEventType.ITERATION_END,
                iteration=1,
                phase="building",
                data={
                    "success": True,
                    "tokens_used": 2500,
                    "cost_usd": 0.0125,
                }
            )
            display.handle_event(end_event)

        # Verify final spinner state
        assert spinner_state["stopped"]
        assert spinner_state["tokens"] == 2500
        assert spinner_state["cost"] == 0.0125


class TestEventDataValidation:
    """Test validation and handling of event data for token display."""

    @pytest.fixture
    def console(self) -> Console:
        """Create a test console."""
        return Console(force_terminal=True, no_color=True, quiet=True)

    @pytest.fixture
    def display(self, console: Console) -> RalphLiveDisplay:
        """Create a RalphLiveDisplay for testing."""
        return RalphLiveDisplay(console, verbosity=1)

    def test_extract_token_data_valid(self, display: RalphLiveDisplay) -> None:
        """Test extracting valid token data from event."""
        event_data = {
            "success": True,
            "tokens_used": 1500,
            "cost_usd": 0.0075,
        }
        
        # Test the internal method if it exists, or the actual behavior
        event = StreamEvent(
            type=StreamEventType.ITERATION_END,
            iteration=1,
            phase="building",
            data=event_data
        )
        
        # Track the data that gets processed
        processed_data = {}
        original_update = display._update_spinner
        
        def capture_update(tokens=0, cost=0.0):
            processed_data["tokens"] = tokens
            processed_data["cost"] = cost
            original_update(tokens, cost)
            
        display._update_spinner = capture_update
        display.handle_event(event)
        
        assert processed_data["tokens"] == 1500
        assert processed_data["cost"] == 0.0075

    def test_extract_token_data_partial(self, display: RalphLiveDisplay) -> None:
        """Test extracting partial token data from event."""
        event_data = {
            "success": True,
            "tokens_used": 1000,
            # Missing cost_usd
        }
        
        processed_data = {}
        display._update_spinner = lambda tokens=0, cost=0.0: processed_data.update({
            "tokens": tokens, "cost": cost
        })
        
        event = StreamEvent(
            type=StreamEventType.ITERATION_END,
            iteration=1,
            phase="building",
            data=event_data
        )
        display.handle_event(event)
        
        assert processed_data["tokens"] == 1000
        assert processed_data["cost"] == 0.0  # Should default to 0

    def test_extract_token_data_empty(self, display: RalphLiveDisplay) -> None:
        """Test extracting token data from empty event data."""
        event_data = {"success": True}  # No token data
        
        processed_data = {}
        display._update_spinner = lambda tokens=0, cost=0.0: processed_data.update({
            "tokens": tokens, "cost": cost
        })
        
        event = StreamEvent(
            type=StreamEventType.ITERATION_END,
            iteration=1,
            phase="building",
            data=event_data
        )
        display.handle_event(event)
        
        assert processed_data["tokens"] == 0
        assert processed_data["cost"] == 0.0

    def test_token_data_type_conversion(self, display: RalphLiveDisplay) -> None:
        """Test type conversion for token data."""
        # Test with string numbers (should convert)
        event_data = {
            "success": True,
            "tokens_used": "1500",  # String
            "cost_usd": "0.0075",   # String
        }
        
        processed_data = {}
        display._update_spinner = lambda tokens=0, cost=0.0: processed_data.update({
            "tokens": tokens, "cost": cost
        })
        
        event = StreamEvent(
            type=StreamEventType.ITERATION_END,
            iteration=1,
            phase="building",
            data=event_data
        )
        display.handle_event(event)
        
        # Should convert strings to numbers or default to 0 if conversion fails
        assert isinstance(processed_data["tokens"], int)
        assert isinstance(processed_data["cost"], float)
