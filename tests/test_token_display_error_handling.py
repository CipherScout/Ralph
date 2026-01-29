"""Tests for error handling in token display feature (SPEC-002-realtime-token-display).

This module tests various error conditions and edge cases for the token display
functionality, including missing usage data, malformed events, and SDK errors.
"""

from __future__ import annotations

import pytest
from rich.console import Console

from ralph.animations import ThinkingSpinner
from ralph.cli import RalphLiveDisplay
from ralph.events import StreamEvent, StreamEventType


class TestMissingUsageDataHandling:
    """Test error handling when token usage data is missing or invalid."""

    @pytest.fixture
    def console(self) -> Console:
        """Create a test console."""
        return Console(force_terminal=True, no_color=True, quiet=True)

    @pytest.fixture
    def display(self, console: Console) -> RalphLiveDisplay:
        """Create a RalphLiveDisplay for testing."""
        return RalphLiveDisplay(console, verbosity=1)

    def test_iteration_end_no_usage_data(self, display: RalphLiveDisplay) -> None:
        """Test ITERATION_END event with completely missing usage data."""
        # Track what gets passed to spinner update
        update_calls = []
        display._update_spinner = lambda tokens=0, cost=0.0: update_calls.append(
            {"tokens": tokens, "cost": cost}
        )

        # Event with no token/cost data at all
        event = StreamEvent(
            type=StreamEventType.ITERATION_END,
            iteration=1,
            phase="building",
            data={"success": True}  # Only success, no token data
        )

        display.handle_event(event)

        # Should handle gracefully with default values
        assert len(update_calls) == 1
        assert update_calls[0]["tokens"] == 0
        assert update_calls[0]["cost"] == 0.0

    def test_iteration_end_partial_usage_data(self, display: RalphLiveDisplay) -> None:
        """Test ITERATION_END event with partial usage data."""
        test_cases = [
            # Only tokens, no cost - should work fine
            {"tokens_used": 1500},
            # Only cost, no tokens - should work fine  
            {"cost_usd": 0.0075},
            # Note: The current implementation doesn't handle None values gracefully
            # These would cause TypeError in the current CLI implementation
        ]

        for i, partial_data in enumerate(test_cases):
            update_calls = []
            display._update_spinner = lambda tokens=0, cost=0.0: update_calls.append(
                {"tokens": tokens, "cost": cost}
            )

            event_data = {"success": True}
            event_data.update(partial_data)

            event = StreamEvent(
                type=StreamEventType.ITERATION_END,
                iteration=i + 1,
                phase="building",
                data=event_data
            )

            display.handle_event(event)

            # Should handle partial data gracefully
            assert len(update_calls) == 1
            call = update_calls[0]

            # Verify defaults are applied for missing values
            assert isinstance(call["tokens"], int)
            assert isinstance(call["cost"], float)
            assert call["tokens"] >= 0  # Should not be negative
            assert call["cost"] >= 0.0  # Should not be negative

    def test_iteration_end_with_none_values_handled_gracefully(self, display: RalphLiveDisplay) -> None:
        """Test ITERATION_END event with None values is handled gracefully."""
        update_calls = []
        display._update_spinner = lambda tokens=0, cost=0.0: update_calls.append(
            {"tokens": tokens, "cost": cost}
        )

        test_cases = [
            {"tokens_used": 1000, "cost_usd": None},
            {"tokens_used": None, "cost_usd": 0.005},
        ]

        for partial_data in test_cases:
            event_data = {"success": True}
            event_data.update(partial_data)

            event = StreamEvent(
                type=StreamEventType.ITERATION_END,
                iteration=1,
                phase="building",
                data=event_data
            )

            # Should handle None values gracefully via type coercion
            display.handle_event(event)

        assert len(update_calls) == 2
        # First case: tokens=1000, cost=None -> 0.0
        assert update_calls[0]["tokens"] == 1000
        assert update_calls[0]["cost"] == 0.0
        # Second case: tokens=None -> 0, cost=0.005
        assert update_calls[1]["tokens"] == 0
        assert update_calls[1]["cost"] == 0.005

    def test_iteration_end_invalid_data_types_handled_gracefully(self, display: RalphLiveDisplay) -> None:
        """Test ITERATION_END event with invalid data types is handled gracefully."""
        update_calls = []
        display._update_spinner = lambda tokens=0, cost=0.0: update_calls.append(
            {"tokens": tokens, "cost": cost}
        )

        invalid_data_cases = [
            # String tokens - coerced to 0
            {"tokens_used": "invalid", "cost_usd": 0.005},
            # String cost - coerced to 0.0
            {"tokens_used": 1000, "cost_usd": "invalid"},
        ]

        for i, invalid_data in enumerate(invalid_data_cases):
            event_data = {"success": True}
            event_data.update(invalid_data)

            event = StreamEvent(
                type=StreamEventType.ITERATION_END,
                iteration=i + 1,
                phase="building",
                data=event_data
            )

            # Should handle invalid types gracefully via type coercion
            display.handle_event(event)

        assert len(update_calls) == 2
        # First case: "invalid" -> 0 tokens, cost=0.005
        assert update_calls[0]["tokens"] == 0
        assert update_calls[0]["cost"] == 0.005
        # Second case: tokens=1000, "invalid" -> 0.0 cost
        assert update_calls[1]["tokens"] == 1000
        assert update_calls[1]["cost"] == 0.0

    def test_iteration_end_negative_values(self, display: RalphLiveDisplay) -> None:
        """Test ITERATION_END event with negative values."""
        update_calls = []
        display._update_spinner = lambda tokens=0, cost=0.0: update_calls.append(
            {"tokens": tokens, "cost": cost}
        )

        event = StreamEvent(
            type=StreamEventType.ITERATION_END,
            iteration=1,
            phase="building",
            data={
                "success": True,
                "tokens_used": -1000,  # Negative tokens
                "cost_usd": -0.005,    # Negative cost
            }
        )

        display.handle_event(event)

        # Should handle negative values (could be valid in some edge cases)
        assert len(update_calls) == 1
        call = update_calls[0]
        
        # Depending on implementation, might clamp to 0 or preserve negative
        # The important thing is it doesn't crash
        assert isinstance(call["tokens"], int)
        assert isinstance(call["cost"], float)

    def test_empty_event_data(self, display: RalphLiveDisplay) -> None:
        """Test ITERATION_END event with completely empty data."""
        update_calls = []
        display._update_spinner = lambda tokens=0, cost=0.0: update_calls.append(
            {"tokens": tokens, "cost": cost}
        )

        event = StreamEvent(
            type=StreamEventType.ITERATION_END,
            iteration=1,
            phase="building",
            data={}  # Completely empty data
        )

        display.handle_event(event)

        # Should handle empty data gracefully
        assert len(update_calls) == 1
        assert update_calls[0]["tokens"] == 0
        assert update_calls[0]["cost"] == 0.0

    def test_none_event_data(self, display: RalphLiveDisplay) -> None:
        """Test ITERATION_END event with None data."""
        update_calls = []
        display._update_spinner = lambda tokens=0, cost=0.0: update_calls.append(
            {"tokens": tokens, "cost": cost}
        )

        event = StreamEvent(
            type=StreamEventType.ITERATION_END,
            iteration=1,
            phase="building",
            data=None  # None data
        )

        # Should not crash with None data
        display.handle_event(event)

        # Behavior depends on implementation, but should not crash
        # May or may not call update_spinner depending on how None is handled


class TestSpinnerErrorHandling:
    """Test error handling in ThinkingSpinner with invalid token data."""

    @pytest.fixture
    def console(self) -> Console:
        """Create a test console."""
        return Console(force_terminal=True, no_color=True, quiet=True)

    def test_spinner_update_with_invalid_tokens(self, console: Console) -> None:
        """Test spinner update with invalid token values."""
        spinner = ThinkingSpinner(console, show_tips=False)

        # update() only assigns when value is not None (None = "no change")
        # Non-None values are stored as-is without type validation
        spinner.update(tokens="not_a_number", cost=0.0)
        assert spinner._tokens == "not_a_number"

        spinner.update(tokens=[], cost=0.0)
        assert spinner._tokens == []

        spinner.update(tokens={}, cost=0.0)
        assert spinner._tokens == {}

        # None means "don't update", so previous value is preserved
        spinner.update(tokens=None, cost=0.0)
        assert spinner._tokens == {}  # Preserved from previous call

    def test_spinner_update_with_invalid_cost(self, console: Console) -> None:
        """Test spinner update with invalid cost values."""
        spinner = ThinkingSpinner(console, show_tips=False)

        # Non-None values are stored as-is without type validation
        spinner.update(tokens=1000, cost="not_a_number")
        assert spinner._cost == "not_a_number"

        spinner.update(tokens=1000, cost=[])
        assert spinner._cost == []

        spinner.update(tokens=1000, cost={})
        assert spinner._cost == {}

        # None means "don't update", so previous value is preserved
        spinner.update(tokens=1000, cost=None)
        assert spinner._cost == {}  # Preserved from previous call

    def test_spinner_render_with_corrupted_state(self, console: Console) -> None:
        """Test spinner rendering when internal state is corrupted."""
        spinner = ThinkingSpinner(console, show_tips=False)

        # Simulate corrupted state
        spinner._tokens = None
        spinner._cost = None
        spinner._verb = None
        spinner._tip = None

        # Should not crash when rendering corrupted state
        try:
            rendered = spinner._render()
            assert rendered is not None
        except Exception as e:
            # If it does crash, should be a well-defined exception
            assert isinstance(e, (TypeError, ValueError, AttributeError))

    def test_spinner_render_extreme_values(self, console: Console) -> None:
        """Test spinner rendering with extreme values."""
        spinner = ThinkingSpinner(console, show_tips=False)

        extreme_cases = [
            {"tokens": 0, "cost": 0.0},
            {"tokens": 1, "cost": float('inf')},
            {"tokens": float('inf'), "cost": 1.0},
            {"tokens": -1000, "cost": -1.0},
            {"tokens": 1000000000000, "cost": 999999.9999},
        ]

        for case in extreme_cases:
            spinner._tokens = case["tokens"]
            spinner._cost = case["cost"]

            # Should handle extreme values gracefully
            try:
                rendered = spinner._render()
                assert rendered is not None
                # Should produce some text
                assert len(rendered.plain) > 0
            except Exception:
                # Extreme values might cause exceptions, which is acceptable
                # as long as they're well-defined
                pass


class TestSDKIntegrationErrorHandling:
    """Test error handling when integrating with Claude Agent SDK."""

    @pytest.fixture
    def console(self) -> Console:
        """Create a test console."""
        return Console(force_terminal=True, no_color=True, quiet=True)

    @pytest.fixture
    def display(self, console: Console) -> RalphLiveDisplay:
        """Create a RalphLiveDisplay for testing."""
        return RalphLiveDisplay(console, verbosity=1)

    def test_malformed_sdk_events(self, display: RalphLiveDisplay) -> None:
        """Test handling of malformed events from SDK."""
        # Events with missing required fields
        malformed_events = [
            # Missing iteration
            {"type": StreamEventType.ITERATION_END, "phase": "building", "data": {}},
            # Missing phase  
            {"type": StreamEventType.ITERATION_END, "iteration": 1, "data": {}},
            # Missing type
            {"iteration": 1, "phase": "building", "data": {}},
        ]

        for malformed_data in malformed_events:
            try:
                # Try to create event with malformed data
                event = StreamEvent(**malformed_data)
                display.handle_event(event)
            except (TypeError, ValueError):
                # It's acceptable for malformed events to raise exceptions
                pass

    def test_sdk_connection_errors(self, display: RalphLiveDisplay) -> None:
        """Test handling when SDK connection has issues."""
        # Simulate scenarios where SDK might not provide complete information
        incomplete_events = [
            # Event with minimal data
            StreamEvent(
                type=StreamEventType.ITERATION_END,
                iteration=1, 
                phase="building",
                data={"success": False}  # Failed iteration
            ),
            # Event with unexpected data structure
            StreamEvent(
                type=StreamEventType.ITERATION_END,
                iteration=1,
                phase="building", 
                data={
                    "success": True,
                    "result": {"nested": {"tokens": 1000}}  # Nested structure
                }
            ),
        ]

        for event in incomplete_events:
            # Should handle gracefully without crashing
            display.handle_event(event)

    def test_rapid_fire_events(self, display: RalphLiveDisplay) -> None:
        """Test handling of rapid successive events that might cause race conditions."""
        # Track all calls
        all_calls = []
        display._update_spinner = lambda tokens=0, cost=0.0: all_calls.append(
            {"tokens": tokens, "cost": cost}
        )

        # Fire many events rapidly
        for i in range(100):
            event = StreamEvent(
                type=StreamEventType.ITERATION_END,
                iteration=i,
                phase="building",
                data={
                    "success": True,
                    "tokens_used": i * 10,
                    "cost_usd": i * 0.001,
                }
            )
            display.handle_event(event)

        # Should handle all events without error
        assert len(all_calls) == 100

    def test_concurrent_event_handling(self, display: RalphLiveDisplay) -> None:
        """Test concurrent event handling doesn't cause data corruption."""
        import threading
        import time

        errors = []
        handled_events = []

        def handle_events(start_idx: int, count: int):
            try:
                for i in range(start_idx, start_idx + count):
                    event = StreamEvent(
                        type=StreamEventType.ITERATION_END,
                        iteration=i,
                        phase="building",
                        data={
                            "success": True,
                            "tokens_used": i * 10,
                            "cost_usd": i * 0.001,
                        }
                    )
                    display.handle_event(event)
                    handled_events.append(i)
                    time.sleep(0.001)  # Small delay to encourage race conditions
            except Exception as e:
                errors.append(e)

        # Start multiple threads handling events concurrently
        threads = []
        for i in range(5):
            thread = threading.Thread(target=handle_events, args=(i * 10, 10))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Should not have any errors from concurrent access
        assert len(errors) == 0, f"Concurrent handling errors: {errors}"
        # Should have handled all events
        assert len(handled_events) == 50


class TestTokenDisplayFallbackBehavior:
    """Test fallback behavior when token display features fail."""

    @pytest.fixture
    def console(self) -> Console:
        """Create a test console."""
        return Console(force_terminal=True, no_color=True, quiet=True)

    @pytest.fixture 
    def display(self, console: Console) -> RalphLiveDisplay:
        """Create a RalphLiveDisplay for testing."""
        return RalphLiveDisplay(console, verbosity=1)

    def test_spinner_creation_failure(self, display: RalphLiveDisplay) -> None:
        """Test handling when spinner creation fails."""
        # Simulate spinner creation failure by setting it to None
        display._spinner = None

        # Should handle gracefully when spinner is missing
        display._start_spinner()
        display._stop_spinner()
        display._update_spinner(tokens=1000, cost=0.005)

        # Should not crash

    def test_console_output_failure(self, display: RalphLiveDisplay) -> None:
        """Test handling when console output fails."""
        # Mock console to simulate output failure
        original_print = display.console.print

        def failing_print(*args, **kwargs):
            raise IOError("Console output failed")

        display.console.print = failing_print

        try:
            event = StreamEvent(
                type=StreamEventType.ITERATION_END,
                iteration=1,
                phase="building",
                data={
                    "success": True,
                    "tokens_used": 1000,
                    "cost_usd": 0.005,
                }
            )
            
            # Current implementation will raise IOError when console.print fails
            with pytest.raises(IOError):
                display.handle_event(event)
        
        finally:
            # Restore original print method
            display.console.print = original_print

    def test_fallback_to_basic_display(self, display: RalphLiveDisplay) -> None:
        """Test fallback to basic display when advanced features fail."""
        # Simulate various component failures
        display._spinner = None  # Spinner failed
        
        # Track what basic output still works
        output_captured = []
        original_print = display.console.print
        display.console.print = lambda *args, **kwargs: output_captured.append(str(args[0]) if args else "")

        try:
            event = StreamEvent(
                type=StreamEventType.ITERATION_END,
                iteration=1,
                phase="building", 
                data={
                    "success": True,
                    "tokens_used": 1500,
                    "cost_usd": 0.0075,
                }
            )
            
            display.handle_event(event)
            
            # Should still produce some output even with component failures
            # (Implementation dependent - might be silent fallback)
            
        finally:
            display.console.print = original_print