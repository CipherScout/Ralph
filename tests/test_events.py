"""Tests for Ralph event streaming infrastructure."""

from ralph.events import (
    StreamEvent,
    StreamEventType,
    context_emergency_event,
    context_warning_event,
    error_event,
    info_event,
    iteration_end_event,
    iteration_start_event,
    text_delta_event,
    tool_end_event,
    tool_start_event,
    warning_event,
)


class TestStreamEventType:
    """Tests for StreamEventType enum."""

    def test_context_warning_type_exists(self) -> None:
        """CONTEXT_WARNING event type exists (SPEC-005)."""
        assert hasattr(StreamEventType, "CONTEXT_WARNING")
        assert StreamEventType.CONTEXT_WARNING.value == "context_warning"

    def test_context_emergency_type_exists(self) -> None:
        """CONTEXT_EMERGENCY event type exists (SPEC-005)."""
        assert hasattr(StreamEventType, "CONTEXT_EMERGENCY")
        assert StreamEventType.CONTEXT_EMERGENCY.value == "context_emergency"


class TestStreamEvent:
    """Tests for StreamEvent dataclass."""

    def test_basic_event_creation(self) -> None:
        """Basic event creation works."""
        event = StreamEvent(type=StreamEventType.INFO)
        assert event.type == StreamEventType.INFO
        assert event.data == {}

    def test_event_with_data(self) -> None:
        """Event with data dictionary."""
        event = StreamEvent(
            type=StreamEventType.INFO,
            data={"key": "value"},
        )
        assert event.data["key"] == "value"


class TestContextWarningEvents:
    """Tests for context warning events (SPEC-005)."""

    def test_context_warning_event_creation(self) -> None:
        """context_warning_event creates correct event."""
        event = context_warning_event(
            usage_percent=75.5,
            current_tokens=151_000,
            threshold_percent=80.0,
        )
        assert event.type == StreamEventType.CONTEXT_WARNING
        assert event.data["usage_percent"] == 75.5
        assert event.data["current_tokens"] == 151_000
        assert event.data["threshold_percent"] == 80.0
        assert "message" in event.data

    def test_context_warning_event_default_threshold(self) -> None:
        """context_warning_event has sensible default threshold."""
        event = context_warning_event(
            usage_percent=72.0,
            current_tokens=144_000,
        )
        assert event.data["threshold_percent"] == 80.0

    def test_context_emergency_event_creation(self) -> None:
        """context_emergency_event creates correct event."""
        event = context_emergency_event(
            usage_percent=92.0,
            current_tokens=184_000,
        )
        assert event.type == StreamEventType.CONTEXT_EMERGENCY
        assert event.data["usage_percent"] == 92.0
        assert event.data["current_tokens"] == 184_000
        assert "message" in event.data
        assert "Emergency" in event.data["message"]


class TestIterationEvents:
    """Tests for iteration event factory functions."""

    def test_iteration_start_event(self) -> None:
        """iteration_start_event creates correct event."""
        event = iteration_start_event(
            iteration=5,
            phase="building",
            session_id="session-123",
        )
        assert event.type == StreamEventType.ITERATION_START
        assert event.iteration == 5
        assert event.phase == "building"
        assert event.session_id == "session-123"

    def test_iteration_end_event(self) -> None:
        """iteration_end_event creates correct event."""
        event = iteration_end_event(
            iteration=5,
            phase="building",
            success=True,
            tokens_used=1500,
            cost_usd=0.025,
        )
        assert event.type == StreamEventType.ITERATION_END
        assert event.iteration == 5
        assert event.phase == "building"
        assert event.data["success"] is True
        assert event.data["tokens_used"] == 1500
        assert event.data["cost_usd"] == 0.025


class TestToolEvents:
    """Tests for tool event factory functions."""

    def test_tool_start_event(self) -> None:
        """tool_start_event creates correct event."""
        event = tool_start_event(
            tool_name="Read",
            tool_input={"path": "/test/file.py"},
            tool_id="tool-123",
        )
        assert event.type == StreamEventType.TOOL_USE_START
        assert event.tool_name == "Read"
        assert event.tool_input == {"path": "/test/file.py"}
        assert event.tool_id == "tool-123"

    def test_tool_end_event(self) -> None:
        """tool_end_event creates correct event."""
        event = tool_end_event(
            tool_name="Read",
            tool_id="tool-123",
            success=True,
        )
        assert event.type == StreamEventType.TOOL_USE_END
        assert event.tool_name == "Read"
        assert event.data["success"] is True


class TestTextEvents:
    """Tests for text event factory functions."""

    def test_text_delta_event(self) -> None:
        """text_delta_event creates correct event."""
        event = text_delta_event("Hello, world!")
        assert event.type == StreamEventType.TEXT_DELTA
        assert event.text == "Hello, world!"


class TestErrorEvents:
    """Tests for error/warning/info event factory functions."""

    def test_error_event(self) -> None:
        """error_event creates correct event."""
        event = error_event("Something went wrong", error_type="connection")
        assert event.type == StreamEventType.ERROR
        assert event.error_message == "Something went wrong"
        assert event.data["error_type"] == "connection"

    def test_warning_event(self) -> None:
        """warning_event creates correct event."""
        event = warning_event("This might be a problem")
        assert event.type == StreamEventType.WARNING
        assert event.error_message == "This might be a problem"

    def test_info_event(self) -> None:
        """info_event creates correct event."""
        event = info_event("Just FYI")
        assert event.type == StreamEventType.INFO
        assert event.data["message"] == "Just FYI"
