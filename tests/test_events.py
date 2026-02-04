"""Tests for Ralph event streaming infrastructure."""

from ralph.events import (
    StreamEvent,
    StreamEventType,
    SubagentEndEvent,
    SubagentStartEvent,
    context_emergency_event,
    context_warning_event,
    error_event,
    info_event,
    iteration_end_event,
    iteration_start_event,
    subagent_end_event,
    subagent_start_event,
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

    def test_subagent_start_type_exists(self) -> None:
        """SUBAGENT_START event type exists."""
        assert hasattr(StreamEventType, "SUBAGENT_START")
        assert StreamEventType.SUBAGENT_START.value == "subagent_start"

    def test_subagent_end_type_exists(self) -> None:
        """SUBAGENT_END event type exists."""
        assert hasattr(StreamEventType, "SUBAGENT_END")
        assert StreamEventType.SUBAGENT_END.value == "subagent_end"


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


class TestStreamEventSerialization:
    """Tests for StreamEvent serialization with token usage and cost data."""

    def test_iteration_end_event_with_token_fields(self) -> None:
        """iteration_end_event includes token_usage and cost_usd fields."""
        event = iteration_end_event(
            iteration=3,
            phase="building",
            success=True,
            tokens_used=2500,
            cost_usd=0.0375,
        )
        assert event.type == StreamEventType.ITERATION_END
        assert event.iteration == 3
        assert event.phase == "building"
        assert hasattr(event, "token_usage")
        assert hasattr(event, "cost_usd")
        assert event.token_usage == 2500
        assert event.cost_usd == 0.0375

    def test_stream_event_serialization_with_tokens(self) -> None:
        """StreamEvent.to_dict() includes token_usage and cost_usd."""
        event = iteration_end_event(
            iteration=1,
            phase="discovery",
            success=True,
            tokens_used=1200,
            cost_usd=0.018,
        )
        data = event.to_dict()
        assert "token_usage" in data
        assert "cost_usd" in data
        assert data["token_usage"] == 1200
        assert data["cost_usd"] == 0.018

    def test_stream_event_deserialization_with_tokens(self) -> None:
        """StreamEvent.from_dict() restores token_usage and cost_usd."""
        original_event = iteration_end_event(
            iteration=2,
            phase="planning",
            success=False,
            tokens_used=800,
            cost_usd=0.012,
        )
        serialized = original_event.to_dict()
        restored_event = StreamEvent.from_dict(serialized)

        assert restored_event.token_usage == 800
        assert restored_event.cost_usd == 0.012
        assert restored_event.iteration == 2
        assert restored_event.phase == "planning"

    def test_stream_event_serialization_without_token_data(self) -> None:
        """Events without token data serialize properly (None values excluded)."""
        event = text_delta_event("Hello")
        data = event.to_dict()

        # Fields should not be present if None
        assert "token_usage" not in data
        assert "cost_usd" not in data
        assert "text" in data
        assert data["text"] == "Hello"


class TestSubagentEvents:
    """Tests for subagent lifecycle event dataclasses and factory functions."""

    def test_subagent_start_event_dataclass_exists(self) -> None:
        """SubagentStartEvent dataclass exists with correct fields."""
        event = SubagentStartEvent(
            subagent_type="research-specialist",
            task_description="Analyze library options"
        )
        assert event.subagent_type == "research-specialist"
        assert event.task_description == "Analyze library options"

    def test_subagent_start_event_literal_types(self) -> None:
        """SubagentStartEvent uses Literal type annotations for subagent_type."""
        # Test all valid subagent types with explicit type annotations
        event1 = SubagentStartEvent(
            subagent_type="research-specialist",
            task_description="Test task"
        )
        assert event1.subagent_type == "research-specialist"

        event2 = SubagentStartEvent(
            subagent_type="code-reviewer",
            task_description="Test task"
        )
        assert event2.subagent_type == "code-reviewer"

        event3 = SubagentStartEvent(
            subagent_type="test-engineer",
            task_description="Test task"
        )
        assert event3.subagent_type == "test-engineer"

        event4 = SubagentStartEvent(
            subagent_type="documentation-agent",
            task_description="Test task"
        )
        assert event4.subagent_type == "documentation-agent"

        event5 = SubagentStartEvent(
            subagent_type="product-analyst",
            task_description="Test task"
        )
        assert event5.subagent_type == "product-analyst"

    def test_subagent_end_event_dataclass_exists(self) -> None:
        """SubagentEndEvent dataclass exists with correct fields."""
        event = SubagentEndEvent(
            subagent_type="test-engineer",
            success=True,
            report_length=1500
        )
        assert event.subagent_type == "test-engineer"
        assert event.success is True
        assert event.report_length == 1500

    def test_subagent_end_event_literal_types(self) -> None:
        """SubagentEndEvent uses Literal type annotations for subagent_type."""
        # Test all valid subagent types with explicit type annotations
        event1 = SubagentEndEvent(
            subagent_type="research-specialist",
            success=False,
            report_length=0
        )
        assert event1.subagent_type == "research-specialist"

        event2 = SubagentEndEvent(
            subagent_type="code-reviewer",
            success=False,
            report_length=0
        )
        assert event2.subagent_type == "code-reviewer"

        event3 = SubagentEndEvent(
            subagent_type="test-engineer",
            success=False,
            report_length=0
        )
        assert event3.subagent_type == "test-engineer"

        event4 = SubagentEndEvent(
            subagent_type="documentation-agent",
            success=False,
            report_length=0
        )
        assert event4.subagent_type == "documentation-agent"

        event5 = SubagentEndEvent(
            subagent_type="product-analyst",
            success=False,
            report_length=0
        )
        assert event5.subagent_type == "product-analyst"

    def test_subagent_start_event_factory_function(self) -> None:
        """subagent_start_event factory function creates correct event."""
        event = subagent_start_event(
            subagent_type="code-reviewer",
            task_description="Review security vulnerabilities"
        )
        assert event.type == StreamEventType.SUBAGENT_START
        assert event.data["subagent_type"] == "code-reviewer"
        assert event.data["task_description"] == "Review security vulnerabilities"

    def test_subagent_end_event_factory_function(self) -> None:
        """subagent_end_event factory function creates correct event."""
        event = subagent_end_event(
            subagent_type="documentation-agent",
            success=True,
            report_length=2000
        )
        assert event.type == StreamEventType.SUBAGENT_END
        assert event.data["subagent_type"] == "documentation-agent"
        assert event.data["success"] is True
        assert event.data["report_length"] == 2000

    def test_subagent_events_can_be_imported(self) -> None:
        """SubagentStartEvent and SubagentEndEvent can be imported and instantiated."""
        # This test verifies the import functionality works
        start_event = SubagentStartEvent(
            subagent_type="product-analyst",
            task_description="Analyze requirements"
        )
        end_event = SubagentEndEvent(
            subagent_type="product-analyst",
            success=True,
            report_length=800
        )
        assert start_event.subagent_type == "product-analyst"
        assert end_event.subagent_type == "product-analyst"
