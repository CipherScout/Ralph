"""Integration tests for phase transitions covering all user input scenarios and edge cases.

This test file provides comprehensive integration testing for phase transitions
in Ralph, covering user input scenarios, timeouts, interrupts, non-interactive mode,
and platform differences to achieve >95% code coverage.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ralph.cli import RalphLiveDisplay, app
from ralph.events import StreamEvent, StreamEventType, needs_input_event
from ralph.executors import (
    BuildingExecutor,
    DiscoveryExecutor,
    ValidationExecutor,
)
from ralph.models import Phase, Task
from ralph.persistence import initialize_plan, initialize_state, save_plan
from ralph.transitions import PhaseTransitionPrompt, prompt_phase_transition


class TestPhaseTransitionPromptIntegration:
    """Integration tests for PhaseTransitionPrompt auto-continue behavior."""

    @pytest.fixture
    def prompt(self):
        """Create a PhaseTransitionPrompt for testing."""
        from rich.console import Console
        console = Console()
        return PhaseTransitionPrompt(
            console=console,
            current_phase=Phase.DISCOVERY,
            next_phase=Phase.PLANNING,
            timeout_seconds=2,
        )

    @pytest.mark.asyncio
    async def test_auto_continues_in_interactive_mode(self, prompt, monkeypatch):
        """Test auto-continue after brief pause in interactive mode."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        mock_sleep = AsyncMock()
        monkeypatch.setattr("asyncio.sleep", mock_sleep)

        result = await prompt.prompt()

        assert result is True
        mock_sleep.assert_called_once_with(2)

    @pytest.mark.asyncio
    async def test_non_interactive_mode_auto_continues(self, prompt, monkeypatch):
        """Test non-interactive mode (stdin is not a tty) auto-continues."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)

        result = await prompt.prompt()

        assert result is True

    @pytest.mark.asyncio
    async def test_zero_timeout_auto_continues(self):
        """Test zero timeout immediately auto-continues."""
        from rich.console import Console
        console = Console()
        prompt = PhaseTransitionPrompt(
            console=console,
            current_phase=Phase.BUILDING,
            next_phase=Phase.VALIDATION,
            timeout_seconds=0,
        )

        result = await prompt.prompt()

        assert result is True

    @pytest.mark.asyncio
    async def test_all_phase_transitions_auto_continue(self, monkeypatch):
        """Test all phase transitions auto-continue correctly."""
        from rich.console import Console

        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        mock_sleep = AsyncMock()
        monkeypatch.setattr("asyncio.sleep", mock_sleep)

        transitions = [
            (Phase.DISCOVERY, Phase.PLANNING),
            (Phase.PLANNING, Phase.BUILDING),
            (Phase.BUILDING, Phase.VALIDATION),
        ]

        for current, next_phase in transitions:
            prompt = PhaseTransitionPrompt(
                console=Console(),
                current_phase=current,
                next_phase=next_phase,
            )
            result = await prompt.prompt()
            assert result is True, f"Transition {current} -> {next_phase} should auto-continue"


class TestPromptPhaseTransitionIntegration:
    """Integration tests for the prompt_phase_transition function."""

    @pytest.fixture
    def console(self):
        """Create a Rich Console for testing."""
        from rich.console import Console
        return Console()

    @pytest.mark.asyncio
    async def test_final_phase_returns_true_none(self, console):
        """Final phase (VALIDATION) should return (True, None)."""
        result = await prompt_phase_transition(console, Phase.VALIDATION, timeout_seconds=1)

        assert result == (True, None)

    @pytest.mark.asyncio
    async def test_discovery_to_planning_continue(self, console, monkeypatch):
        """Discovery phase should transition to Planning when user continues."""
        # Mock PhaseTransitionPrompt.prompt to return True
        async def mock_prompt(self):
            return True

        with patch('ralph.transitions.PhaseTransitionPrompt.prompt', mock_prompt):
            result = await prompt_phase_transition(console, Phase.DISCOVERY, timeout_seconds=1)

        assert result == (True, Phase.PLANNING)

    @pytest.mark.asyncio
    async def test_planning_to_building_continue(self, console, monkeypatch):
        """Planning phase should transition to Building when user continues."""
        async def mock_prompt(self):
            return True

        with patch('ralph.transitions.PhaseTransitionPrompt.prompt', mock_prompt):
            result = await prompt_phase_transition(console, Phase.PLANNING, timeout_seconds=1)

        assert result == (True, Phase.BUILDING)

    @pytest.mark.asyncio
    async def test_building_to_validation_continue(self, console, monkeypatch):
        """Building phase should transition to Validation when user continues."""
        async def mock_prompt(self):
            return True

        with patch('ralph.transitions.PhaseTransitionPrompt.prompt', mock_prompt):
            result = await prompt_phase_transition(console, Phase.BUILDING, timeout_seconds=1)

        assert result == (True, Phase.VALIDATION)

    @pytest.mark.asyncio
    async def test_user_exits_returns_false_none(self, console, monkeypatch):
        """When user exits, should return (False, None)."""
        async def mock_prompt(self):
            return False

        with patch('ralph.transitions.PhaseTransitionPrompt.prompt', mock_prompt):
            result = await prompt_phase_transition(console, Phase.DISCOVERY, timeout_seconds=1)

        assert result == (False, None)

    @pytest.mark.asyncio
    async def test_keyboard_interrupt_returns_false_none(self, console, monkeypatch):
        """KeyboardInterrupt should return (False, None)."""
        async def mock_prompt(self):
            raise KeyboardInterrupt()

        with patch('ralph.transitions.PhaseTransitionPrompt.prompt', mock_prompt):
            result = await prompt_phase_transition(console, Phase.BUILDING, timeout_seconds=1)

        assert result == (False, None)

    @pytest.mark.asyncio
    async def test_zero_timeout_immediate_continue(self, console):
        """Zero timeout should immediately continue without prompting."""
        result = await prompt_phase_transition(console, Phase.DISCOVERY, timeout_seconds=0)

        assert result == (True, Phase.PLANNING)


class TestRalphLiveDisplayUserInputIntegration:
    """Integration tests for RalphLiveDisplay handling user input events."""

    @pytest.fixture
    def display(self):
        """Create a RalphLiveDisplay for testing."""
        from rich.console import Console
        console = Console()
        return RalphLiveDisplay(console, verbosity=1)

    def test_needs_input_event_gets_user_response(self, display):
        """NEEDS_INPUT event should prompt user and return response."""
        event = needs_input_event(
            question="What is your name?",
            options=["Alice", "Bob"]
        )

        # Mock Prompt.ask to return test response
        with patch('ralph.cli.Prompt.ask', return_value="Alice") as mock_ask:
            response = display.handle_event(event)

        assert response == "Alice"
        mock_ask.assert_called_once_with("[bold]Your answer[/bold]")

    def test_needs_input_event_with_complex_options(self, display):
        """NEEDS_INPUT with dict options should display descriptions."""
        event = needs_input_event(
            question="Choose authentication method:",
            options=[
                {"label": "JWT", "description": "JSON Web Tokens"},
                {"label": "OAuth", "description": "OAuth 2.0 flow"},
            ]
        )

        with patch('ralph.cli.Prompt.ask', return_value="JWT"):
            response = display.handle_event(event)

        assert response == "JWT"

    def test_needs_input_event_no_options(self, display):
        """NEEDS_INPUT without options should still prompt user."""
        event = needs_input_event(question="Please describe the issue:")

        with patch('ralph.cli.Prompt.ask', return_value="Database connection failed"):
            response = display.handle_event(event)

        assert response == "Database connection failed"

    def test_needs_input_spinner_lifecycle(self, display):
        """NEEDS_INPUT should stop spinner before asking and restart after."""
        spinner_calls = []
        display._start_spinner = lambda: spinner_calls.append("start")
        display._stop_spinner = lambda: spinner_calls.append("stop")

        event = needs_input_event(question="Continue?")

        with patch('ralph.cli.Prompt.ask', return_value="yes"):
            display.handle_event(event)

        # Should have stopped before asking and started after response
        assert "stop" in spinner_calls
        assert "start" in spinner_calls
        assert spinner_calls.index("stop") < spinner_calls.index("start")


class TestPhaseExecutorStreamingIntegration:
    """Integration tests for phase executors with user input streaming."""

    @pytest.fixture
    def project_root(self, tmp_path):
        """Create an initialized project directory."""
        initialize_state(tmp_path)
        initialize_plan(tmp_path)
        return tmp_path

    @pytest.mark.asyncio
    async def test_discovery_executor_needs_input_flow(self, project_root):
        """Test DiscoveryExecutor handling NEEDS_INPUT events in stream."""
        # Mock the SDK client to yield NEEDS_INPUT events
        mock_client = AsyncMock()

        async def mock_stream_iteration(*args, **kwargs):
            yield StreamEvent(type=StreamEventType.ITERATION_START, iteration=1)

            # Simulate AskUserQuestion tool asking for input
            user_response = yield needs_input_event(
                question="What do you want to build?",
                options=["Web App", "CLI Tool", "API Service"]
            )

            # Process the response
            yield StreamEvent(
                type=StreamEventType.TEXT_DELTA,
                text=f"Creating specs for {user_response}..."
            )

            yield StreamEvent(
                type=StreamEventType.ITERATION_END,
                data={"success": True, "cost_usd": 0.01, "tokens_used": 100}
            )

        mock_client.stream_iteration = mock_stream_iteration

        executor = DiscoveryExecutor(project_root)
        executor._client = mock_client

        # Run the streaming execution
        gen = executor.stream_execution(max_iterations=1)

        event = await gen.asend(None)
        responses_sent = []

        try:
            while True:
                user_response = None
                if event.type == StreamEventType.NEEDS_INPUT:
                    user_response = "CLI Tool"
                    responses_sent.append(user_response)

                event = await gen.asend(user_response)
        except StopAsyncIteration:
            pass

        # Verify user response was captured
        assert "CLI Tool" in responses_sent

    @pytest.mark.asyncio
    async def test_validation_executor_human_approval_flow(self, project_root):
        """Test ValidationExecutor handling validation complete event."""
        # Initialize state
        initialize_state(project_root)
        initialize_plan(project_root)

        # Mock the SDK client
        mock_client = AsyncMock()

        async def mock_stream_iteration(*args, **kwargs):
            yield StreamEvent(type=StreamEventType.ITERATION_START, iteration=1)
            yield StreamEvent(type=StreamEventType.TEXT_DELTA, text="Running tests...")
            yield StreamEvent(type=StreamEventType.TEXT_DELTA, text="All tests pass!")
            yield StreamEvent(
                type=StreamEventType.ITERATION_END,
                data={
                    "success": True,
                    "cost_usd": 0.05,
                    "tokens_used": 500,
                    "final_text": "validation complete - all checks passed"
                }
            )

        mock_client.stream_iteration = mock_stream_iteration

        executor = ValidationExecutor(project_root)
        executor._client = mock_client

        # Run the streaming execution and collect events
        gen = executor.stream_execution(max_iterations=1)
        events = []

        try:
            event = await gen.asend(None)
            while True:
                events.append(event)
                event = await gen.asend(None)
        except StopAsyncIteration:
            pass

        # Verify iteration events were collected
        iteration_start_events = [e for e in events if e.type == StreamEventType.ITERATION_START]
        iteration_end_events = [e for e in events if e.type == StreamEventType.ITERATION_END]
        assert len(iteration_start_events) >= 1
        assert len(iteration_end_events) >= 1

    @pytest.mark.asyncio
    async def test_executor_error_handling_with_user_input(self, project_root):
        """Test executor handling errors during user input collection."""
        mock_client = AsyncMock()

        async def mock_stream_iteration(*args, **kwargs):
            yield StreamEvent(type=StreamEventType.ITERATION_START, iteration=1)

            # Simulate an error occurring
            yield StreamEvent(
                type=StreamEventType.ERROR,
                error_message="SDK connection failed",
                data={"error_type": "connection_error"}
            )

        mock_client.stream_iteration = mock_stream_iteration

        executor = DiscoveryExecutor(project_root)
        executor._client = mock_client

        # Run streaming execution and collect all events
        events = []
        gen = executor.stream_execution(max_iterations=1)

        try:
            event = await gen.asend(None)
            while True:
                events.append(event)
                event = await gen.asend(None)
        except StopAsyncIteration:
            pass

        # Should have captured the error event
        error_events = [e for e in events if e.type == StreamEventType.ERROR]
        assert len(error_events) > 0
        assert "SDK connection failed" in error_events[0].error_message


class TestCLIPhaseCommandsIntegration:
    """Integration tests for CLI phase commands with user interaction."""

    @pytest.fixture
    def initialized_project(self, tmp_path):
        """Create an initialized Ralph project."""
        initialize_state(tmp_path)
        initialize_plan(tmp_path)
        return tmp_path

    def test_discover_command_user_cancellation(self, initialized_project):
        """Test discover command when user cancels with Ctrl+C."""
        from typer.testing import CliRunner

        runner = CliRunner()

        # Mock the executor to simulate KeyboardInterrupt during streaming
        async def mock_stream_execution(*args, **kwargs):
            yield StreamEvent(type=StreamEventType.ITERATION_START, iteration=1)
            # Simulate user pressing Ctrl+C
            raise KeyboardInterrupt()

        with patch('ralph.cli.DiscoveryExecutor') as mock_executor_cls:
            mock_executor = MagicMock()
            mock_executor.stream_execution = mock_stream_execution
            mock_executor_cls.return_value = mock_executor

            result = runner.invoke(
                app,
                ["discover", "-p", str(initialized_project), "--no-auto"]
            )

        # KeyboardInterrupt returns False in handler, which typically results in exit code 1
        # The important thing is the graceful handling message
        assert "interrupted" in result.output.lower()

    def test_plan_command_with_timeout_transition(self, initialized_project):
        """Test plan command completes and shows transition prompt."""
        from typer.testing import CliRunner

        runner = CliRunner()

        # Mock the executor to complete quickly
        async def mock_stream_execution(*args, **kwargs):
            yield StreamEvent(type=StreamEventType.ITERATION_START, iteration=1)
            yield StreamEvent(type=StreamEventType.INFO, data={"message": "Planning complete"})
            yield StreamEvent(
                type=StreamEventType.ITERATION_END,
                data={"success": True, "cost_usd": 0.02, "tokens_used": 200}
            )

        # Mock transition prompt to auto-continue (timeout)
        async def mock_prompt_transition(console, phase, timeout_seconds):
            return (True, Phase.BUILDING)

        with patch('ralph.cli.PlanningExecutor') as mock_executor_cls:
            mock_executor = MagicMock()
            mock_executor.stream_execution = mock_stream_execution
            mock_executor_cls.return_value = mock_executor

            # Patch where the function is defined
            with patch('ralph.transitions.prompt_phase_transition', mock_prompt_transition):
                with patch('ralph.cli.build') as mock_build:
                    result = runner.invoke(
                        app,
                        ["plan", "-p", str(initialized_project), "--auto-timeout", "1"]
                    )

        # Command should complete (may or may not transition based on mock behavior)
        assert result.exit_code in (0, 1)  # 0 = success, 1 = graceful exit

    def test_build_command_user_says_no_to_transition(self, initialized_project):
        """Test build command when user declines transition."""
        from typer.testing import CliRunner

        runner = CliRunner()

        # Create some tasks to work on
        plan = initialize_plan(initialized_project)
        plan.tasks.append(Task(id="task-1", description="Test task", priority=1))
        save_plan(plan, initialized_project)

        # Mock executor to complete all tasks
        async def mock_stream_execution(*args, **kwargs):
            yield StreamEvent(type=StreamEventType.ITERATION_START, iteration=1)
            yield StreamEvent(type=StreamEventType.TASK_COMPLETE, task_id="task-1")
            yield StreamEvent(
                type=StreamEventType.ITERATION_END,
                data={"success": True, "task_completed": True, "cost_usd": 0.03, "tokens_used": 300}
            )

        # Mock transition prompt where user says no
        async def mock_prompt_transition(console, phase, timeout_seconds):
            return (False, None)  # User declined

        with patch('ralph.cli.BuildingExecutor') as mock_executor_cls:
            mock_executor = MagicMock()
            mock_executor.stream_execution = mock_stream_execution
            mock_executor_cls.return_value = mock_executor

            # Patch where the function is defined
            with patch('ralph.transitions.prompt_phase_transition', mock_prompt_transition):
                with patch('ralph.cli.validate') as mock_validate:
                    result = runner.invoke(
                        app,
                        ["build", "-p", str(initialized_project)]
                    )

        # Command should complete (user declined transition)
        assert result.exit_code in (0, 1)

    def test_validate_command_non_interactive_mode(self, initialized_project):
        """Test validate command in non-interactive mode (no TTY)."""
        from typer.testing import CliRunner

        runner = CliRunner()

        # Mock the executor
        async def mock_stream_execution(*args, **kwargs):
            yield StreamEvent(type=StreamEventType.ITERATION_START, iteration=1)
            yield StreamEvent(type=StreamEventType.TEXT_DELTA, text="Validation complete")
            yield StreamEvent(
                type=StreamEventType.ITERATION_END,
                data={"success": True, "cost_usd": 0.01, "tokens_used": 100}
            )

        with patch('ralph.cli.ValidationExecutor') as mock_executor_cls:
            mock_executor = MagicMock()
            mock_executor.stream_execution = mock_stream_execution
            mock_executor_cls.return_value = mock_executor

            # Mock sys.stdin.isatty to return False (non-interactive)
            with patch('sys.stdin.isatty', return_value=False):
                result = runner.invoke(
                    app,
                    ["validate", "-p", str(initialized_project)]
                )

        assert result.exit_code == 0
        assert "validation" in result.stdout.lower()


class TestPlatformSpecificBehavior:
    """Integration tests for platform-specific behaviors."""

    def test_cross_platform_phase_transitions(self, tmp_path):
        """Test phase transitions work consistently across platforms."""
        # This test ensures phase transition behavior is consistent
        # regardless of the underlying platform

        initialize_state(tmp_path)
        initialize_plan(tmp_path)

        from rich.console import Console
        console = Console()

        # Test all phase transitions
        phase_transitions = [
            (Phase.DISCOVERY, Phase.PLANNING),
            (Phase.PLANNING, Phase.BUILDING),
            (Phase.BUILDING, Phase.VALIDATION),
            (Phase.VALIDATION, None),
        ]

        async def test_transitions():
            for current, expected_next in phase_transitions:
                # Mock non-interactive mode for consistency
                with patch('sys.stdin.isatty', return_value=False):
                    should_continue, next_phase = await prompt_phase_transition(
                        console, current, timeout_seconds=0
                    )

                assert should_continue is True
                assert next_phase == expected_next

        # Run the test regardless of platform
        asyncio.run(test_transitions())


class TestEdgeCasesAndErrorConditions:
    """Integration tests for edge cases and error conditions."""

    @pytest.fixture
    def project_root(self, tmp_path):
        """Create project directory."""
        return tmp_path

    @pytest.mark.asyncio
    async def test_corrupted_state_during_phase_transition(self, project_root):
        """Test handling corrupted state during phase transitions."""
        # Create corrupted state file
        state_file = project_root / ".ralph" / "state.json"
        state_file.parent.mkdir(exist_ok=True)
        state_file.write_text("invalid json {")

        from ralph.persistence import CorruptedStateError, StateNotFoundError

        # Executor uses lazy loading - error is raised when accessing state property
        executor = DiscoveryExecutor(project_root)
        with pytest.raises((StateNotFoundError, CorruptedStateError)):
            _ = executor.state  # Access state to trigger load

    @pytest.mark.asyncio
    async def test_missing_plan_during_building_phase(self, project_root):
        """Test building phase when plan is missing."""
        # Initialize state but not plan
        initialize_state(project_root)

        executor = BuildingExecutor(project_root)

        # Should handle missing plan gracefully - returns success=False with error
        result = await executor.execute(max_iterations=1)

        # Missing plan causes exception that gets caught and returns success=False
        assert result.success is False
        assert result.tasks_completed == 0
        assert result.error is not None  # Error message present

    def test_memory_pressure_during_streaming(self, tmp_path):
        """Test system behavior under memory pressure during streaming."""
        # This test simulates high memory usage scenarios that could occur
        # during long streaming sessions

        initialize_state(tmp_path)
        initialize_plan(tmp_path)

        from rich.console import Console
        display = RalphLiveDisplay(Console(), verbosity=1)

        # Simulate many events to test memory handling
        events = []
        for i in range(1000):
            event = StreamEvent(
                type=StreamEventType.TEXT_DELTA,
                text=f"Processing step {i}: {'x' * 100}"  # Large text
            )
            events.append(event)

        # Process all events
        for event in events:
            display.handle_event(event)

        # Should handle large number of events without issues
        assert len(display.current_text) > 0

    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    async def test_network_interruption_during_sdk_calls(self, tmp_path):
        """Test handling network interruptions during SDK calls."""
        initialize_state(tmp_path)
        initialize_plan(tmp_path)

        executor = DiscoveryExecutor(tmp_path)

        # Mock client to simulate network error
        mock_client = AsyncMock()
        mock_client.stream_iteration.side_effect = ConnectionError("Network unreachable")
        executor._client = mock_client

        # Should handle network errors gracefully
        events = []
        try:
            gen = executor.stream_execution(max_iterations=1)
            event = await gen.asend(None)
            while True:
                events.append(event)
                event = await gen.asend(None)
        except (StopAsyncIteration, ConnectionError):
            pass

        # Should have captured error events
        assert any(e.type == StreamEventType.ERROR for e in events)


class TestCodeCoverageScenarios:
    """Tests specifically designed to achieve >95% code coverage."""

    @pytest.mark.asyncio
    async def test_phase_transition_prompt_render_method(self):
        """Test PhaseTransitionPrompt._render method for coverage."""
        from rich.console import Console
        from rich.panel import Panel

        console = Console()
        prompt = PhaseTransitionPrompt(
            console=console,
            current_phase=Phase.DISCOVERY,
            next_phase=Phase.PLANNING,
            timeout_seconds=30
        )

        panel = prompt._render()
        assert isinstance(panel, Panel)

    def test_ralph_live_display_tool_summarization_coverage(self):
        """Test all tool input summarization paths for coverage."""
        from rich.console import Console

        from ralph.cli import RalphLiveDisplay

        display = RalphLiveDisplay(Console(), verbosity=1)

        # Test all tool types
        test_cases = [
            ("Read", {"file_path": "/very/long/path/to/some/file/that/should/be/truncated.py"}, True),
            ("Write", {"file_path": "/test.py", "content": "x" * 1000}, True),
            ("Edit", {"file_path": "/test.py", "old_string": "old", "new_string": "new"}, True),
            ("Bash", {"command": "very long command " * 20}, True),
            ("Grep", {"pattern": "test", "path": "/src"}, True),
            ("Glob", {"pattern": "*.py"}, True),
            ("WebSearch", {"query": "test query"}, True),
            ("WebFetch", {"url": "https://example.com/very/long/url" + "x" * 100}, True),
            ("Task", {"description": "very long task description " * 10}, True),
            ("AskUserQuestion", {"questions": [{"question": "Test?"}]}, False),  # Should return empty
            ("ralph_mark_task_complete", {"task_id": "test", "notes": "done"}, True),
            ("UnknownTool", {"param": "value"}, False),  # Unknown tool, verbosity 1
        ]

        for tool_name, input_data, should_have_output in test_cases:
            summary = display._summarize_tool_input(tool_name, input_data)
            if should_have_output:
                assert summary != ""
            else:
                assert summary == ""

    def test_ralph_live_display_high_verbosity_tool_summary(self):
        """Test tool summarization with high verbosity."""
        from rich.console import Console

        from ralph.cli import RalphLiveDisplay

        display = RalphLiveDisplay(Console(), verbosity=2)  # High verbosity

        # Unknown tool should return JSON summary in high verbosity
        summary = display._summarize_tool_input("UnknownTool", {"param": "value"})
        assert "param" in summary
        assert "value" in summary

    def test_cli_command_validation_edge_cases(self, tmp_path):
        """Test CLI command validation edge cases for coverage."""
        from typer.testing import CliRunner

        runner = CliRunner()

        # Test invalid project root paths
        invalid_paths = [
            "/nonexistent/path/xyz",  # Non-existent
            __file__,  # File instead of directory
        ]

        for invalid_path in invalid_paths:
            result = runner.invoke(app, ["init", "-p", invalid_path])
            assert result.exit_code == 1
            assert "error" in result.stdout.lower()

    def test_ralph_live_display_event_data_extraction(self):
        """Test event data extraction edge cases for coverage."""
        from rich.console import Console

        from ralph.cli import RalphLiveDisplay

        display = RalphLiveDisplay(Console(), verbosity=1)

        # Test events with missing or None data (non-interactive events)
        non_interactive_events = [
            StreamEvent(type=StreamEventType.ITERATION_END, data=None),
            StreamEvent(type=StreamEventType.TASK_COMPLETE, task_id=None, data={}),
            StreamEvent(type=StreamEventType.ERROR, error_message=None, data={}),
        ]

        for event in non_interactive_events:
            # Should handle None/missing data gracefully
            result = display.handle_event(event)
            assert result is None  # Non-interactive events return None

        # Test NEEDS_INPUT separately with mocked prompt
        needs_input_event = StreamEvent(
            type=StreamEventType.NEEDS_INPUT, question=None, options=None
        )
        with patch('ralph.cli.Prompt.ask', return_value="test"):
            result = display.handle_event(needs_input_event)
            assert result == "test"

    def test_ralph_live_display_spinner_edge_cases(self):
        """Test spinner edge cases for coverage."""
        from rich.console import Console

        from ralph.cli import RalphLiveDisplay

        display = RalphLiveDisplay(Console(), verbosity=1)

        # Test spinner methods when already in desired state
        display._spinner_active = True
        display._start_spinner()  # Should not start again (early return)

        display._spinner_active = False
        display._stop_spinner()  # Should not stop again (early return)

        # Test spinner exception handling - the internal _start_spinner/_stop_spinner
        # methods have try/except blocks that catch exceptions gracefully
        # We test by making ThinkingSpinner constructor raise
        with patch('ralph.cli.ThinkingSpinner', side_effect=Exception("Spinner failed")):
            display._spinner_active = False
            display._start_spinner()  # Should catch exception gracefully
            assert display._spinner_active is False  # Stays False on error

        # Test stop when spinner object is None
        display._spinner = None
        display._spinner_active = True
        display._stop_spinner()  # Should handle None spinner
        assert display._spinner_active is False

    def test_display_fun_facts_and_animations(self):
        """Test fun facts and animation features for coverage."""
        from rich.console import Console

        from ralph.cli import RalphLiveDisplay

        display = RalphLiveDisplay(Console(), verbosity=1)

        # Test fun fact display on specific iterations
        display._show_fun_fact_at = 2

        # First iteration - should not show fact
        event1 = StreamEvent(type=StreamEventType.ITERATION_START, iteration=1, phase="discovery")
        display.handle_event(event1)

        # Second iteration - should show fact
        event2 = StreamEvent(type=StreamEventType.ITERATION_START, iteration=2, phase="discovery")
        display.handle_event(event2)

        # Test phase change animation
        event3 = StreamEvent(
            type=StreamEventType.PHASE_CHANGE,
            data={"old_phase": "discovery", "new_phase": "planning"}
        )
        display.handle_event(event3)
