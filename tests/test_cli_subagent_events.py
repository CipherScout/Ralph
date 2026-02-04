"""Tests for CLI subagent event display functionality."""

from rich.console import Console

from ralph.cli import RalphLiveDisplay
from ralph.events import StreamEvent, StreamEventType


class TestSubagentEventDisplay:
    """Tests for RalphLiveDisplay subagent event handling."""

    def test_subagent_start_event_display(self) -> None:
        """Test SUBAGENT_START event displays with proper styling."""
        console = Console(force_terminal=True, no_color=True, quiet=True)
        display = RalphLiveDisplay(console, verbosity=1)

        # Track console output
        outputs = []
        console.print = lambda *args, **kwargs: outputs.append(str(args[0]) if args else "")
        event = StreamEvent(
            type=StreamEventType.SUBAGENT_START,
            data={
                "subagent_type": "research-specialist",
                "task_description": "Analyze API documentation for security patterns",
            },
        )

        result = display.handle_event(event)

        # Should return None (no user input required)
        assert result is None

        # Should display subagent invocation with blue styling and robot emoji
        assert len(outputs) >= 1
        output_text = " ".join(outputs).lower()
        assert "🤖" in outputs[0] or "robot" in output_text
        assert "invoking" in output_text or "starting" in output_text
        assert "research-specialist" in output_text

        # Should include task description
        assert "analyze api documentation" in output_text

    def test_subagent_start_event_verbosity_control(self) -> None:
        """Test SUBAGENT_START event respects verbosity settings."""
        console = Console(force_terminal=True, no_color=True, quiet=True)
        display = RalphLiveDisplay(console, verbosity=0)  # quiet mode

        outputs = []
        console.print = lambda *args, **kwargs: outputs.append(str(args[0]) if args else "")
        event = StreamEvent(
            type=StreamEventType.SUBAGENT_START,
            data={
                "subagent_type": "code-reviewer",
                "task_description": "Review pull request changes",
            },
        )

        display.handle_event(event)

        # Should not display anything in quiet mode
        assert len(outputs) == 0

    def test_subagent_end_event_success_display(self) -> None:
        """Test SUBAGENT_END event displays success status."""
        console = Console(force_terminal=True, no_color=True, quiet=True)
        display = RalphLiveDisplay(console, verbosity=1)

        outputs = []
        console.print = lambda *args, **kwargs: outputs.append(str(args[0]) if args else "")
        event = StreamEvent(
            type=StreamEventType.SUBAGENT_END,
            data={
                "subagent_type": "test-engineer",
                "success": True,
                "report_length": 1250,
            },
        )

        result = display.handle_event(event)

        assert result is None
        assert len(outputs) >= 1
        output_text = " ".join(outputs).lower()

        # Should show completion status with checkmark or success indicator
        assert "✓" in outputs[0] or "success" in output_text or "completed" in output_text
        assert "test-engineer" in output_text

        # Should include report length information
        assert "1250" in output_text or "1,250" in output_text

    def test_subagent_end_event_failure_display(self) -> None:
        """Test SUBAGENT_END event displays failure status."""
        console = Console(force_terminal=True, no_color=True, quiet=True)
        display = RalphLiveDisplay(console, verbosity=1)

        outputs = []
        console.print = lambda *args, **kwargs: outputs.append(str(args[0]) if args else "")
        event = StreamEvent(
            type=StreamEventType.SUBAGENT_END,
            data={
                "subagent_type": "documentation-agent",
                "success": False,
                "report_length": 0,
            },
        )

        display.handle_event(event)

        output_text = " ".join(outputs).lower()

        # Should show failure status with error indicator
        assert "✗" in outputs[0] or "failed" in output_text or "error" in output_text
        assert "documentation-agent" in output_text

    def test_subagent_events_are_visually_distinct(self) -> None:
        """Test subagent events are visually distinct from regular tool calls."""
        console = Console(force_terminal=True, no_color=True, quiet=True)
        display = RalphLiveDisplay(console, verbosity=1)

        outputs = []
        console.print = lambda *args, **kwargs: outputs.append(str(args[0]) if args else "")
        # Regular tool call
        tool_event = StreamEvent(
            type=StreamEventType.TOOL_USE_START,
            tool_name="Read",
            tool_input={"file_path": "/test.py"},
        )

        # Subagent event
        subagent_event = StreamEvent(
            type=StreamEventType.SUBAGENT_START,
            data={
                "subagent_type": "product-analyst",
                "task_description": "Analyze user requirements",
            },
        )

        display.handle_event(tool_event)
        tool_output_count = len(outputs)

        display.handle_event(subagent_event)
        subagent_outputs = outputs[tool_output_count:] if len(outputs) > tool_output_count else []

        # Subagent events should be visually distinct
        # Tool events typically show "-> ToolName:" format
        # Subagent events should use different styling (emoji, different format)
        assert len(subagent_outputs) > 0, "Subagent should produce output"

        # Check that any of the subagent outputs contains the robot emoji
        subagent_text = " ".join(subagent_outputs)
        assert "🤖" in subagent_text or "robot" in subagent_text.lower()

        # Tool output should not contain robot emoji
        tool_text = " ".join(outputs[:tool_output_count])
        assert "🤖" not in tool_text

    def test_subagent_events_maintain_existing_structure(self) -> None:
        """Test subagent events don't break existing event handling structure."""
        console = Console(force_terminal=True, no_color=True, quiet=True)
        display = RalphLiveDisplay(console, verbosity=2)

        outputs = []
        console.print = lambda *args, **kwargs: outputs.append(str(args[0]) if args else "")
        # Mix of event types to ensure no interference
        events = [
            StreamEvent(type=StreamEventType.ITERATION_START, iteration=1, phase="building"),
            StreamEvent(
                type=StreamEventType.SUBAGENT_START,
                data={"subagent_type": "research-specialist", "task_description": "Research task"}
            ),
            StreamEvent(type=StreamEventType.TEXT_DELTA, text="Some text output"),
            StreamEvent(
                type=StreamEventType.SUBAGENT_END,
                data={"subagent_type": "research-specialist", "success": True, "report_length": 500}
            ),
            StreamEvent(
                type=StreamEventType.ITERATION_END,
                iteration=1,
                data={"success": True, "tokens_used": 100, "cost_usd": 0.01}
            ),
        ]

        # Should handle all events without errors
        for event in events:
            result = display.handle_event(event)
            # Only NEEDS_INPUT events should return non-None
            if event.type != StreamEventType.NEEDS_INPUT:
                assert result is None

        # Should have produced some output
        assert len(outputs) > 0

    def test_subagent_events_with_verbose_mode(self) -> None:
        """Test subagent events in verbose mode (verbosity=2)."""
        console = Console(force_terminal=True, no_color=True, quiet=True)
        display = RalphLiveDisplay(console, verbosity=2)

        outputs = []
        console.print = lambda *args, **kwargs: outputs.append(str(args[0]) if args else "")
        # Test verbose subagent start
        start_event = StreamEvent(
            type=StreamEventType.SUBAGENT_START,
            data={
                "subagent_type": "code-reviewer",
                "task_description": "Review security implementation patterns",
            },
        )

        display.handle_event(start_event)

        # In verbose mode, should show full task description
        output_text = " ".join(outputs).lower()
        assert "security implementation patterns" in output_text
        assert "code-reviewer" in output_text

    def test_subagent_types_all_supported(self) -> None:
        """Test all valid subagent types are handled properly."""

        console = Console(force_terminal=True, no_color=True, quiet=True)
        display = RalphLiveDisplay(console, verbosity=1)

        outputs = []
        console.print = lambda *args, **kwargs: outputs.append(str(args[0]) if args else "")
        # Test all valid subagent types
        valid_types = [
            "research-specialist", "code-reviewer", "test-engineer",
            "documentation-agent", "product-analyst"
        ]

        for subagent_type in valid_types:
            event = StreamEvent(
                type=StreamEventType.SUBAGENT_START,
                data={
                    "subagent_type": subagent_type,
                    "task_description": f"Task for {subagent_type}",
                },
            )

            display.handle_event(event)

            # Should display the subagent type without errors
            output_text = " ".join(outputs).lower()
            assert subagent_type in output_text

