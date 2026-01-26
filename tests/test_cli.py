"""Tests for Ralph CLI."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from ralph.cli import app
from ralph.events import StreamEvent, StreamEventType
from ralph.context import load_injections
from ralph.executors import PhaseExecutionResult
from ralph.models import Phase, Task, TaskStatus
from ralph.persistence import (
    initialize_plan,
    initialize_state,
    load_plan,
    load_state,
    save_plan,
    save_state,
    state_exists,
)

runner = CliRunner()


def test_version() -> None:
    """Test version command outputs version."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "Ralph v" in result.stdout


class TestInit:
    """Tests for init command."""

    def test_init_creates_ralph_dir(self, tmp_path: Path) -> None:
        """Test init creates .ralph directory."""
        result = runner.invoke(app, ["init", "-p", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / ".ralph").exists()
        assert (tmp_path / ".ralph" / "state.json").exists()
        assert (tmp_path / ".ralph" / "implementation_plan.json").exists()

    def test_init_outputs_success(self, tmp_path: Path) -> None:
        """Test init outputs success messages."""
        result = runner.invoke(app, ["init", "-p", str(tmp_path)])
        assert result.exit_code == 0
        assert "initialized successfully" in result.stdout.lower()
        assert "state.json" in result.stdout
        assert "implementation_plan.json" in result.stdout

    def test_init_refuses_reinit_without_force(self, tmp_path: Path) -> None:
        """Test init refuses to reinitialize without --force."""
        # First init
        result = runner.invoke(app, ["init", "-p", str(tmp_path)])
        assert result.exit_code == 0

        # Second init without force should fail
        result = runner.invoke(app, ["init", "-p", str(tmp_path)])
        assert result.exit_code == 1
        assert "already initialized" in result.stdout.lower()

    def test_init_with_force_reinitializes(self, tmp_path: Path) -> None:
        """Test init --force reinitializes existing project."""
        # First init
        result = runner.invoke(app, ["init", "-p", str(tmp_path)])
        assert result.exit_code == 0

        # Second init with force should succeed
        result = runner.invoke(app, ["init", "-p", str(tmp_path), "--force"])
        assert result.exit_code == 0
        assert "initialized successfully" in result.stdout.lower()

    def test_init_invalid_path(self) -> None:
        """Test init with non-existent path fails."""
        result = runner.invoke(app, ["init", "-p", "/nonexistent/path/xyz"])
        assert result.exit_code == 1
        assert "does not exist" in result.stdout.lower()


class TestStatus:
    """Tests for status command."""

    def test_status_requires_init(self, tmp_path: Path) -> None:
        """Test status fails if not initialized."""
        result = runner.invoke(app, ["status", "-p", str(tmp_path)])
        assert result.exit_code == 1
        assert "not initialized" in result.stdout.lower()

    def test_status_shows_phase(self, tmp_path: Path) -> None:
        """Test status shows current phase."""
        initialize_state(tmp_path)
        result = runner.invoke(app, ["status", "-p", str(tmp_path)])
        assert result.exit_code == 0
        assert "Phase" in result.stdout
        assert "building" in result.stdout.lower()

    def test_status_shows_iteration_count(self, tmp_path: Path) -> None:
        """Test status shows iteration count."""
        initialize_state(tmp_path)
        result = runner.invoke(app, ["status", "-p", str(tmp_path)])
        assert result.exit_code == 0
        assert "Iteration" in result.stdout

    def test_status_shows_circuit_breaker(self, tmp_path: Path) -> None:
        """Test status shows circuit breaker state."""
        initialize_state(tmp_path)
        result = runner.invoke(app, ["status", "-p", str(tmp_path)])
        assert result.exit_code == 0
        assert "Circuit Breaker" in result.stdout
        assert "closed" in result.stdout.lower()

    def test_status_shows_context_budget(self, tmp_path: Path) -> None:
        """Test status shows context budget."""
        initialize_state(tmp_path)
        result = runner.invoke(app, ["status", "-p", str(tmp_path)])
        assert result.exit_code == 0
        assert "Context Budget" in result.stdout
        assert "Smart Zone" in result.stdout

    def test_status_verbose_shows_tasks(self, tmp_path: Path) -> None:
        """Test status --verbose shows task list."""
        initialize_state(tmp_path)
        plan = initialize_plan(tmp_path)
        plan.tasks.append(
            Task(id="test-1", description="Test task", priority=1)
        )
        save_plan(plan, tmp_path)

        result = runner.invoke(app, ["status", "-p", str(tmp_path), "--verbose"])
        assert result.exit_code == 0
        assert "Implementation Plan" in result.stdout
        assert "Test task" in result.stdout


class TestTasks:
    """Tests for tasks command."""

    def test_tasks_requires_init(self, tmp_path: Path) -> None:
        """Test tasks fails if not initialized."""
        result = runner.invoke(app, ["tasks", "-p", str(tmp_path)])
        assert result.exit_code == 1
        assert "no implementation plan found" in result.stdout.lower()

    def test_tasks_empty_plan(self, tmp_path: Path) -> None:
        """Test tasks with empty plan."""
        initialize_plan(tmp_path)
        result = runner.invoke(app, ["tasks", "-p", str(tmp_path)])
        assert result.exit_code == 0
        assert "no tasks" in result.stdout.lower()

    def test_tasks_shows_pending(self, tmp_path: Path) -> None:
        """Test tasks shows pending tasks."""
        plan = initialize_plan(tmp_path)
        plan.tasks.append(
            Task(id="task-1", description="First task", priority=1)
        )
        plan.tasks.append(
            Task(id="task-2", description="Second task", priority=2)
        )
        save_plan(plan, tmp_path)

        result = runner.invoke(app, ["tasks", "-p", str(tmp_path)])
        assert result.exit_code == 0
        assert "First task" in result.stdout
        assert "Second task" in result.stdout

    def test_tasks_pending_filter(self, tmp_path: Path) -> None:
        """Test tasks --pending shows only pending tasks."""
        plan = initialize_plan(tmp_path)
        plan.tasks.append(
            Task(id="task-1", description="Pending task", priority=1, status=TaskStatus.PENDING)
        )
        plan.tasks.append(
            Task(id="task-2", description="Complete task", priority=2, status=TaskStatus.COMPLETE)
        )
        save_plan(plan, tmp_path)

        result = runner.invoke(app, ["tasks", "-p", str(tmp_path), "--pending"])
        assert result.exit_code == 0
        assert "Pending task" in result.stdout
        assert "Complete task" not in result.stdout

    def test_tasks_all_shows_completed(self, tmp_path: Path) -> None:
        """Test tasks --all shows completed tasks."""
        plan = initialize_plan(tmp_path)
        plan.tasks.append(
            Task(id="task-1", description="Complete task", priority=1, status=TaskStatus.COMPLETE)
        )
        save_plan(plan, tmp_path)

        # Without --all, completed tasks hidden
        result = runner.invoke(app, ["tasks", "-p", str(tmp_path)])
        assert "Complete task" not in result.stdout or "All tasks complete" in result.stdout

        # With --all, completed tasks shown
        result = runner.invoke(app, ["tasks", "-p", str(tmp_path), "--all"])
        assert result.exit_code == 0
        assert "Complete task" in result.stdout

    def test_tasks_shows_next_task(self, tmp_path: Path) -> None:
        """Test tasks shows next available task."""
        plan = initialize_plan(tmp_path)
        plan.tasks.append(
            Task(id="task-1", description="Next available task", priority=1)
        )
        save_plan(plan, tmp_path)

        result = runner.invoke(app, ["tasks", "-p", str(tmp_path)])
        assert result.exit_code == 0
        assert "Next task" in result.stdout
        assert "Next available task" in result.stdout


class TestReset:
    """Tests for reset command."""

    def test_reset_requires_init(self, tmp_path: Path) -> None:
        """Test reset fails if not initialized."""
        result = runner.invoke(app, ["reset", "-p", str(tmp_path)])
        assert result.exit_code == 1
        assert "not initialized" in result.stdout.lower()

    def test_reset_aborts_on_no_confirm(self, tmp_path: Path) -> None:
        """Test reset aborts when user declines confirmation."""
        initialize_state(tmp_path)
        initialize_plan(tmp_path)

        result = runner.invoke(app, ["reset", "-p", str(tmp_path)], input="n\n")
        assert result.exit_code == 0
        assert "aborted" in result.stdout.lower()

    def test_reset_clears_state(self, tmp_path: Path) -> None:
        """Test reset clears state on confirmation."""
        initialize_state(tmp_path)
        initialize_plan(tmp_path)

        result = runner.invoke(app, ["reset", "-p", str(tmp_path)], input="y\n")
        assert result.exit_code == 0
        assert "reset complete" in result.stdout.lower()
        assert state_exists(tmp_path)

    def test_reset_keep_plan_option(self, tmp_path: Path) -> None:
        """Test reset --keep-plan preserves plan."""
        initialize_state(tmp_path)
        plan = initialize_plan(tmp_path)
        plan.tasks.append(
            Task(id="task-1", description="Keep me", priority=1)
        )
        save_plan(plan, tmp_path)

        result = runner.invoke(app, ["reset", "-p", str(tmp_path), "--keep-plan"], input="y\n")
        assert result.exit_code == 0

        # Plan should still have tasks
        reloaded_plan = load_plan(tmp_path)
        assert len(reloaded_plan.tasks) == 1
        assert reloaded_plan.tasks[0].description == "Keep me"


class TestInject:
    """Tests for inject command."""

    def test_inject_requires_init(self, tmp_path: Path) -> None:
        """Test inject fails if not initialized."""
        result = runner.invoke(app, ["inject", "test message", "-p", str(tmp_path)])
        assert result.exit_code == 1
        assert "not initialized" in result.stdout.lower()

    def test_inject_adds_message(self, tmp_path: Path) -> None:
        """Test inject adds message to injections."""
        initialize_state(tmp_path)
        initialize_plan(tmp_path)

        result = runner.invoke(app, ["inject", "Focus on tests", "-p", str(tmp_path)])
        assert result.exit_code == 0
        assert "injected" in result.stdout.lower()

        injections = load_injections(tmp_path)
        assert len(injections) == 1
        assert injections[0].content == "Focus on tests"

    def test_inject_with_priority(self, tmp_path: Path) -> None:
        """Test inject respects priority."""
        initialize_state(tmp_path)
        initialize_plan(tmp_path)

        result = runner.invoke(
            app, ["inject", "High priority", "-p", str(tmp_path), "--priority", "10"]
        )
        assert result.exit_code == 0

        injections = load_injections(tmp_path)
        assert injections[0].priority == 10


class TestPause:
    """Tests for pause command."""

    def test_pause_requires_init(self, tmp_path: Path) -> None:
        """Test pause fails if not initialized."""
        result = runner.invoke(app, ["pause", "-p", str(tmp_path)])
        assert result.exit_code == 1
        assert "not initialized" in result.stdout.lower()

    def test_pause_sets_flag(self, tmp_path: Path) -> None:
        """Test pause sets paused flag."""
        initialize_state(tmp_path)

        result = runner.invoke(app, ["pause", "-p", str(tmp_path)])
        assert result.exit_code == 0
        assert "paused" in result.stdout.lower()

        state = load_state(tmp_path)
        assert state.paused is True


class TestResume:
    """Tests for resume command."""

    def test_resume_requires_init(self, tmp_path: Path) -> None:
        """Test resume fails if not initialized."""
        result = runner.invoke(app, ["resume", "-p", str(tmp_path)])
        assert result.exit_code == 1
        assert "not initialized" in result.stdout.lower()

    def test_resume_unsets_flag(self, tmp_path: Path) -> None:
        """Test resume clears paused flag."""
        state = initialize_state(tmp_path)
        state.paused = True
        save_state(state, tmp_path)

        result = runner.invoke(app, ["resume", "-p", str(tmp_path)])
        assert result.exit_code == 0
        assert "resumed" in result.stdout.lower()

        state = load_state(tmp_path)
        assert state.paused is False

    def test_resume_when_not_paused(self, tmp_path: Path) -> None:
        """Test resume when not paused."""
        initialize_state(tmp_path)

        result = runner.invoke(app, ["resume", "-p", str(tmp_path)])
        assert result.exit_code == 0
        assert "not paused" in result.stdout.lower()


class TestSkip:
    """Tests for skip command."""

    def test_skip_requires_plan(self, tmp_path: Path) -> None:
        """Test skip fails if no plan."""
        result = runner.invoke(app, ["skip", "task-1", "-p", str(tmp_path)])
        assert result.exit_code == 1
        assert "no implementation plan" in result.stdout.lower()

    def test_skip_marks_task_blocked(self, tmp_path: Path) -> None:
        """Test skip marks task as blocked."""
        plan = initialize_plan(tmp_path)
        plan.tasks.append(
            Task(id="task-1", description="Skip this", priority=1)
        )
        save_plan(plan, tmp_path)

        result = runner.invoke(app, ["skip", "task-1", "-p", str(tmp_path)])
        assert result.exit_code == 0
        assert "skipped" in result.stdout.lower()

        plan = load_plan(tmp_path)
        assert plan.tasks[0].status == TaskStatus.BLOCKED

    def test_skip_with_reason(self, tmp_path: Path) -> None:
        """Test skip adds reason."""
        plan = initialize_plan(tmp_path)
        plan.tasks.append(
            Task(id="task-1", description="Skip this", priority=1)
        )
        save_plan(plan, tmp_path)

        result = runner.invoke(
            app, ["skip", "task-1", "-p", str(tmp_path), "-r", "Need API key"]
        )
        assert result.exit_code == 0
        assert "need api key" in result.stdout.lower()

        plan = load_plan(tmp_path)
        assert "Need API key" in plan.tasks[0].blockers

    def test_skip_nonexistent_task(self, tmp_path: Path) -> None:
        """Test skip fails for nonexistent task."""
        initialize_plan(tmp_path)

        result = runner.invoke(app, ["skip", "fake-task", "-p", str(tmp_path)])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()


class TestHistory:
    """Tests for history command."""

    def test_history_empty(self, tmp_path: Path) -> None:
        """Test history with no sessions."""
        result = runner.invoke(app, ["history", "-p", str(tmp_path)])
        assert result.exit_code == 0
        assert "no session history" in result.stdout.lower()


class TestPhaseCommands:
    """Tests for phase commands."""

    def test_run_requires_init(self, tmp_path: Path) -> None:
        """Test run fails if not initialized."""
        result = runner.invoke(app, ["run", "-p", str(tmp_path)])
        assert result.exit_code == 1
        assert "not initialized" in result.stdout.lower()

    @patch("ralph.runner.LoopRunner")
    def test_run_shows_starting(self, mock_runner_cls: MagicMock, tmp_path: Path) -> None:
        """Test run shows starting message."""
        initialize_state(tmp_path)
        initialize_plan(tmp_path)  # Also need to initialize plan

        # Mock the LoopRunner to not make real SDK calls
        mock_runner = MagicMock()
        mock_runner.should_continue.return_value = (False, "test complete")  # Tuple
        mock_runner.current_phase = Phase.BUILDING
        mock_runner.state = MagicMock(session_id="test-session")
        mock_runner.get_system_prompt.return_value = "Test prompt"
        mock_runner.result = MagicMock(status="completed")
        mock_runner_cls.return_value = mock_runner

        result = runner.invoke(app, ["run", "-p", str(tmp_path)])
        assert result.exit_code == 0
        assert "starting" in result.stdout.lower()

    def test_discover_requires_init(self, tmp_path: Path) -> None:
        """Test discover fails if not initialized."""
        result = runner.invoke(app, ["discover", "-p", str(tmp_path)])
        assert result.exit_code == 1
        assert "not initialized" in result.stdout.lower()

    @patch("ralph.cli.DiscoveryExecutor")
    def test_discover_sets_phase(self, mock_executor_cls: MagicMock, tmp_path: Path) -> None:
        """Test discover sets phase to discovery."""
        initialize_state(tmp_path)

        # Mock the executor to return success without making API calls
        # stream_execution is an async generator, so we need to mock it properly
        async def mock_stream_execution(*args: Any, **kwargs: Any) -> Any:
            # Yield a simple info event then stop
            yield StreamEvent(
                type=StreamEventType.INFO,
                data={"message": "Discovery complete"},
            )

        mock_executor = MagicMock()
        mock_executor.stream_execution = mock_stream_execution
        mock_executor_cls.return_value = mock_executor

        result = runner.invoke(app, ["discover", "-p", str(tmp_path), "--no-auto"])
        assert result.exit_code == 0
        assert "discovery" in result.stdout.lower()

        state = load_state(tmp_path)
        assert state.current_phase.value == "discovery"

    @patch("ralph.cli.PlanningExecutor")
    def test_plan_sets_phase(self, mock_executor_cls: MagicMock, tmp_path: Path) -> None:
        """Test plan sets phase to planning."""
        initialize_state(tmp_path)

        # Mock the executor stream_execution as an async generator
        async def mock_stream_execution(*args: Any, **kwargs: Any) -> Any:
            yield StreamEvent(
                type=StreamEventType.INFO,
                data={"message": "Planning complete"},
            )

        mock_executor = MagicMock()
        mock_executor.stream_execution = mock_stream_execution
        mock_executor_cls.return_value = mock_executor

        result = runner.invoke(app, ["plan", "-p", str(tmp_path), "--no-auto"])
        assert result.exit_code == 0
        assert "planning" in result.stdout.lower()

        state = load_state(tmp_path)
        assert state.current_phase.value == "planning"

    @patch("ralph.cli.BuildingExecutor")
    def test_build_sets_phase(self, mock_executor_cls: MagicMock, tmp_path: Path) -> None:
        """Test build sets phase to building."""
        initialize_state(tmp_path)

        # Mock the executor stream_execution as an async generator
        async def mock_stream_execution(*args: Any, **kwargs: Any) -> Any:
            yield StreamEvent(
                type=StreamEventType.INFO,
                data={"message": "Building complete"},
            )

        mock_executor = MagicMock()
        mock_executor.stream_execution = mock_stream_execution
        mock_executor_cls.return_value = mock_executor

        result = runner.invoke(app, ["build", "-p", str(tmp_path), "--no-auto"])
        assert result.exit_code == 0
        assert "building" in result.stdout.lower()

        state = load_state(tmp_path)
        assert state.current_phase.value == "building"

    @patch("ralph.cli.ValidationExecutor")
    def test_validate_sets_phase(self, mock_executor_cls: MagicMock, tmp_path: Path) -> None:
        """Test validate sets phase to validation."""
        initialize_state(tmp_path)

        # Mock the executor stream_execution as an async generator
        async def mock_stream_execution(*args: Any, **kwargs: Any) -> Any:
            yield StreamEvent(
                type=StreamEventType.INFO,
                data={"message": "Validation complete"},
            )

        mock_executor = MagicMock()
        mock_executor.stream_execution = mock_stream_execution
        mock_executor_cls.return_value = mock_executor

        result = runner.invoke(app, ["validate", "-p", str(tmp_path)])
        assert result.exit_code == 0
        assert "validation" in result.stdout.lower()

        state = load_state(tmp_path)
        assert state.current_phase.value == "validation"


class TestHandoff:
    """Tests for handoff command."""

    def test_handoff_requires_init(self, tmp_path: Path) -> None:
        """Test handoff fails if not initialized."""
        result = runner.invoke(app, ["handoff", "-p", str(tmp_path)])
        assert result.exit_code == 1
        assert "not initialized" in result.stdout.lower()

    def test_handoff_creates_memory(self, tmp_path: Path) -> None:
        """Test handoff creates MEMORY.md."""
        initialize_state(tmp_path)
        initialize_plan(tmp_path)

        result = runner.invoke(app, ["handoff", "-p", str(tmp_path)])
        assert result.exit_code == 0
        assert "completed successfully" in result.stdout.lower()
        assert (tmp_path / "MEMORY.md").exists()

    def test_handoff_with_reason(self, tmp_path: Path) -> None:
        """Test handoff with custom reason."""
        initialize_state(tmp_path)
        initialize_plan(tmp_path)

        result = runner.invoke(
            app, ["handoff", "-p", str(tmp_path), "-r", "context_full"]
        )
        assert result.exit_code == 0


class TestRegeneratePlan:
    """Tests for regenerate-plan command."""

    def test_regenerate_plan_requires_init(self, tmp_path: Path) -> None:
        """Test regenerate-plan fails if not initialized."""
        result = runner.invoke(app, ["regenerate-plan", "-p", str(tmp_path)])
        assert result.exit_code == 1
        assert "not initialized" in result.stdout.lower()

    def test_regenerate_plan_resets_plan(self, tmp_path: Path) -> None:
        """Test regenerate-plan resets the plan."""
        state = initialize_state(tmp_path)
        plan = initialize_plan(tmp_path)
        plan.tasks.append(
            Task(id="task-1", description="Pending task", priority=1, status=TaskStatus.PENDING)
        )
        save_plan(plan, tmp_path)
        save_state(state, tmp_path)

        result = runner.invoke(app, ["regenerate-plan", "-p", str(tmp_path)], input="y\n")
        assert result.exit_code == 0
        assert "regenerated" in result.stdout.lower()

        # Check plan was reset
        new_plan = load_plan(tmp_path)
        assert len(new_plan.tasks) == 0

    def test_regenerate_plan_keeps_completed_tasks(self, tmp_path: Path) -> None:
        """Test regenerate-plan preserves completed tasks by default."""
        state = initialize_state(tmp_path)
        plan = initialize_plan(tmp_path)
        plan.tasks.append(
            Task(id="task-1", description="Completed task", priority=1, status=TaskStatus.COMPLETE)
        )
        plan.tasks.append(
            Task(id="task-2", description="Pending task", priority=2, status=TaskStatus.PENDING)
        )
        save_plan(plan, tmp_path)
        save_state(state, tmp_path)

        # Default behavior keeps completed tasks (no --discard-completed flag)
        result = runner.invoke(
            app, ["regenerate-plan", "-p", str(tmp_path)], input="y\n"
        )
        assert result.exit_code == 0
        # The regenerated message shows success
        assert "regenerated" in result.stdout.lower()

        # Check completed task was kept
        new_plan = load_plan(tmp_path)
        assert len(new_plan.tasks) == 1
        assert new_plan.tasks[0].id == "task-1"
        assert new_plan.tasks[0].status == TaskStatus.COMPLETE

    def test_regenerate_plan_discards_completed_tasks(self, tmp_path: Path) -> None:
        """Test regenerate-plan discards completed tasks with --discard-completed."""
        state = initialize_state(tmp_path)
        plan = initialize_plan(tmp_path)
        plan.tasks.append(
            Task(id="task-1", description="Completed task", priority=1, status=TaskStatus.COMPLETE)
        )
        plan.tasks.append(
            Task(id="task-2", description="Pending task", priority=2, status=TaskStatus.PENDING)
        )
        save_plan(plan, tmp_path)
        save_state(state, tmp_path)

        # Explicitly discard completed tasks
        result = runner.invoke(
            app, ["regenerate-plan", "-p", str(tmp_path), "--discard-completed"], input="y\n"
        )
        assert result.exit_code == 0

        # Check all tasks were discarded
        new_plan = load_plan(tmp_path)
        assert len(new_plan.tasks) == 0

    def test_regenerate_plan_aborts_on_no_confirm(self, tmp_path: Path) -> None:
        """Test regenerate-plan aborts when user declines confirmation."""
        state = initialize_state(tmp_path)
        plan = initialize_plan(tmp_path)
        plan.tasks.append(
            Task(id="task-1", description="Pending task", priority=1, status=TaskStatus.PENDING)
        )
        save_plan(plan, tmp_path)
        save_state(state, tmp_path)

        result = runner.invoke(app, ["regenerate-plan", "-p", str(tmp_path)], input="n\n")
        assert result.exit_code == 0
        assert "aborted" in result.stdout.lower()

        # Check plan was NOT reset
        existing_plan = load_plan(tmp_path)
        assert len(existing_plan.tasks) == 1

    def test_regenerate_plan_sets_phase_to_planning(self, tmp_path: Path) -> None:
        """Test regenerate-plan sets phase to planning."""
        from ralph.models import Phase
        state = initialize_state(tmp_path)
        state.current_phase = Phase.BUILDING
        save_state(state, tmp_path)
        initialize_plan(tmp_path)

        result = runner.invoke(app, ["regenerate-plan", "-p", str(tmp_path)])
        assert result.exit_code == 0

        # Check phase was set to planning
        new_state = load_state(tmp_path)
        assert new_state.current_phase == Phase.PLANNING


class TestRunCommand:
    """Tests for run command with loop orchestration."""

    def test_run_dry_run_mode(self, tmp_path: Path) -> None:
        """Test run --dry-run shows what would be done."""
        initialize_state(tmp_path)
        initialize_plan(tmp_path)

        result = runner.invoke(app, ["run", "-p", str(tmp_path), "--dry-run"])
        assert result.exit_code == 0
        assert "dry run mode" in result.stdout.lower()
        assert "current phase" in result.stdout.lower()

    def test_run_with_phase_option(self, tmp_path: Path) -> None:
        """Test run --phase sets starting phase."""
        initialize_state(tmp_path)
        initialize_plan(tmp_path)

        result = runner.invoke(
            app, ["run", "-p", str(tmp_path), "--phase", "discovery", "--dry-run"]
        )
        assert result.exit_code == 0
        assert "starting from phase: discovery" in result.stdout.lower()

        state = load_state(tmp_path)
        assert state.current_phase.value == "discovery"

    def test_run_invalid_phase(self, tmp_path: Path) -> None:
        """Test run with invalid phase fails."""
        initialize_state(tmp_path)
        initialize_plan(tmp_path)

        result = runner.invoke(app, ["run", "-p", str(tmp_path), "--phase", "invalid"])
        assert result.exit_code == 1
        assert "invalid phase" in result.stdout.lower()

    @patch("ralph.runner.LoopRunner")
    def test_run_shows_loop_status(self, mock_runner_cls: MagicMock, tmp_path: Path) -> None:
        """Test run shows loop status."""
        from ralph.runner import LoopStatus
        initialize_state(tmp_path)
        initialize_plan(tmp_path)

        # Mock the LoopRunner to not make real SDK calls
        mock_runner = MagicMock()
        mock_runner.should_continue.return_value = (False, "test complete")  # Tuple
        mock_runner.current_phase = Phase.BUILDING
        mock_runner.state = MagicMock(session_id="test-session")
        mock_runner.get_system_prompt.return_value = "Test prompt"
        mock_runner.result = MagicMock(status=LoopStatus.COMPLETED)
        mock_runner_cls.return_value = mock_runner

        result = runner.invoke(app, ["run", "-p", str(tmp_path)])
        assert result.exit_code == 0
        assert "loop status" in result.stdout.lower()
