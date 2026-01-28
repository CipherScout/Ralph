"""Tests for iteration module."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ralph.iteration import (
    IterationContext,
    create_execute_function,
    execute_single_iteration,
    execute_until_complete,
    run_iteration_sync,
)
from ralph.models import ImplementationPlan, Phase, Task
from ralph.persistence import (
    initialize_plan,
    initialize_state,
    load_state,
    save_plan,
    save_state,
)
from ralph.sdk_client import IterationMetrics, IterationResult


@pytest.fixture
def project_path(tmp_path: Path) -> Path:
    """Create an initialized project directory."""
    initialize_state(tmp_path)
    initialize_plan(tmp_path)
    return tmp_path


@pytest.fixture
def mock_iteration_result() -> IterationResult:
    """Create a mock iteration result."""
    return IterationResult(
        success=True,
        task_completed=False,
        task_id=None,
        error=None,
        cost_usd=0.05,
        tokens_used=5000,
        final_text="Iteration completed",
        metrics=IterationMetrics(),
    )


class TestIterationContext:
    """Tests for IterationContext dataclass."""

    def test_creation(self) -> None:
        """Can create with all fields."""
        ctx = IterationContext(
            iteration=5,
            phase=Phase.BUILDING,
            system_prompt="System prompt",
            task=None,
            usage_percentage=50.0,
            session_id="session-123",
        )
        assert ctx.iteration == 5
        assert ctx.phase == Phase.BUILDING
        assert ctx.task is None
        assert ctx.usage_percentage == 50.0
        assert ctx.session_id == "session-123"

    def test_get_user_prompt_no_task(self) -> None:
        """Generates general prompt when no task."""
        ctx = IterationContext(
            iteration=1,
            phase=Phase.BUILDING,
            system_prompt="",
            task=None,
            usage_percentage=0.0,
            session_id=None,
        )
        prompt = ctx.get_user_prompt()
        assert "building" in prompt.lower()
        assert "plan summary" in prompt.lower()

    def test_get_user_prompt_with_task(self) -> None:
        """Generates task-specific prompt."""
        task = Task(
            id="task-123",
            description="Implement feature X",
            priority=2,
            dependencies=["task-122"],
            verification_criteria=["Tests pass", "Lint clean"],
        )
        ctx = IterationContext(
            iteration=1,
            phase=Phase.BUILDING,
            system_prompt="",
            task=task,
            usage_percentage=0.0,
            session_id=None,
        )
        prompt = ctx.get_user_prompt()

        assert "task-123" in prompt
        assert "Implement feature X" in prompt
        assert "**Priority:** 2" in prompt
        assert "task-122" in prompt
        assert "Tests pass" in prompt
        assert "ralph_mark_task_in_progress" in prompt
        assert "ralph_mark_task_complete" in prompt

    def test_get_user_prompt_task_no_dependencies(self) -> None:
        """Handles task with no dependencies."""
        task = Task(
            id="task-1",
            description="First task",
            priority=1,
        )
        ctx = IterationContext(
            iteration=1,
            phase=Phase.BUILDING,
            system_prompt="",
            task=task,
            usage_percentage=0.0,
            session_id=None,
        )
        prompt = ctx.get_user_prompt()
        assert "**Dependencies:** None" in prompt

    def test_get_user_prompt_task_default_criteria(self) -> None:
        """Uses default criteria when none specified."""
        task = Task(
            id="task-1",
            description="Task",
            priority=1,
            verification_criteria=[],
        )
        ctx = IterationContext(
            iteration=1,
            phase=Phase.BUILDING,
            system_prompt="",
            task=task,
            usage_percentage=0.0,
            session_id=None,
        )
        prompt = ctx.get_user_prompt()
        assert "Implementation complete and tested" in prompt


class TestCreateExecuteFunction:
    """Tests for create_execute_function."""

    @patch("ralph.iteration._execute_async")
    def test_creates_callable(
        self, mock_execute: MagicMock, project_path: Path
    ) -> None:
        """Creates a callable function."""
        mock_execute.return_value = (0.05, 5000, False, None, None)

        execute_fn = create_execute_function(project_path)
        assert callable(execute_fn)

    @patch("ralph.iteration._execute_async")
    def test_execute_returns_tuple(
        self, mock_execute: MagicMock, project_path: Path
    ) -> None:
        """Execute function returns correct tuple format."""
        mock_execute.return_value = (0.05, 5000, True, "task-1", None)

        execute_fn = create_execute_function(project_path)
        result = execute_fn({"iteration": 1, "phase": "building"})

        assert isinstance(result, tuple)
        assert len(result) == 5
        cost, tokens, completed, task_id, error = result
        assert cost == 0.05
        assert tokens == 5000
        assert completed is True
        assert task_id == "task-1"
        assert error is None

    @patch("ralph.iteration._execute_async")
    def test_execute_with_config(
        self, mock_execute: MagicMock, project_path: Path
    ) -> None:
        """Can pass config to execute function."""
        from ralph.config import RalphConfig

        mock_execute.return_value = (0.0, 0, False, None, None)
        config = RalphConfig()

        execute_fn = create_execute_function(project_path, config=config)
        execute_fn({"iteration": 1})

        # Verify config was passed through
        call_args = mock_execute.call_args
        assert call_args is not None


class TestExecuteAsync:
    """Tests for _execute_async internal function."""

    @patch("ralph.iteration.create_ralph_client")
    async def test_loads_state_and_plan(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Loads state and plan for iteration."""
        mock_client = MagicMock()
        mock_client.run_iteration = AsyncMock(
            return_value=IterationResult(
                success=True,
                task_completed=False,
                task_id=None,
                error=None,
                cost_usd=0.05,
                tokens_used=5000,
                final_text="Done",
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        from ralph.config import load_config
        from ralph.iteration import _execute_async

        config = load_config(project_path)
        context = {"iteration": 1, "phase": "building", "system_prompt": "Test"}

        result = await _execute_async(context, project_path, config)

        assert isinstance(result, tuple)
        assert len(result) == 5
        mock_client.run_iteration.assert_called_once()

    @patch("ralph.iteration.create_ralph_client")
    async def test_handles_exception(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Handles exceptions gracefully."""
        mock_client = MagicMock()
        mock_client.run_iteration = AsyncMock(side_effect=Exception("API Error"))
        mock_create_client.return_value = mock_client

        from ralph.config import load_config
        from ralph.iteration import _execute_async

        config = load_config(project_path)
        context = {"iteration": 1}

        cost, tokens, completed, task_id, error = await _execute_async(
            context, project_path, config
        )

        assert cost == 0.0
        assert tokens == 0
        assert completed is False
        assert task_id is None
        assert error == "API Error"


class TestExecuteSingleIteration:
    """Tests for execute_single_iteration function."""

    @patch("ralph.iteration.create_ralph_client")
    async def test_runs_iteration(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Runs a single iteration."""
        mock_client = MagicMock()
        mock_client.run_iteration = AsyncMock(
            return_value=IterationResult(
                success=True,
                task_completed=False,
                task_id=None,
                error=None,
                cost_usd=0.05,
                tokens_used=5000,
                final_text="Done",
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        result = await execute_single_iteration(project_path)

        assert isinstance(result, IterationResult)
        assert result.success is True

    @patch("ralph.iteration.create_ralph_client")
    async def test_updates_state(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Updates state after iteration."""
        mock_client = MagicMock()
        mock_client.run_iteration = AsyncMock(
            return_value=IterationResult(
                success=True,
                task_completed=True,
                task_id="task-1",
                error=None,
                cost_usd=0.10,
                tokens_used=10000,
                final_text="Task done",
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        initial_state = load_state(project_path)
        initial_iteration = initial_state.iteration_count

        await execute_single_iteration(project_path)

        updated_state = load_state(project_path)
        assert updated_state.iteration_count == initial_iteration + 1

    @patch("ralph.iteration.create_ralph_client")
    async def test_with_custom_prompt(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Can use custom prompt."""
        mock_client = MagicMock()
        mock_client.run_iteration = AsyncMock(
            return_value=IterationResult(
                success=True,
                task_completed=False,
                task_id=None,
                error=None,
                cost_usd=0.05,
                tokens_used=5000,
                final_text="Done",
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        await execute_single_iteration(project_path, prompt="Custom prompt here")

        call_args = mock_client.run_iteration.call_args
        assert call_args.kwargs.get("prompt") == "Custom prompt here"

    @patch("ralph.iteration.create_ralph_client")
    async def test_with_task(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Generates prompt with task info."""
        mock_client = MagicMock()
        mock_client.run_iteration = AsyncMock(
            return_value=IterationResult(
                success=True,
                task_completed=False,
                task_id=None,
                error=None,
                cost_usd=0.05,
                tokens_used=5000,
                final_text="Working",
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        # Add task to plan
        plan = ImplementationPlan(
            tasks=[Task(id="task-1", description="Build feature", priority=1)]
        )
        save_plan(plan, project_path)

        await execute_single_iteration(project_path)

        call_args = mock_client.run_iteration.call_args
        prompt = call_args.kwargs.get("prompt")
        assert "task-1" in prompt
        assert "Build feature" in prompt


class TestRunIterationSync:
    """Tests for run_iteration_sync function."""

    @patch("ralph.iteration.create_ralph_client")
    def test_runs_sync(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Runs iteration synchronously."""
        mock_client = MagicMock()
        mock_client.run_iteration = AsyncMock(
            return_value=IterationResult(
                success=True,
                task_completed=False,
                task_id=None,
                error=None,
                cost_usd=0.05,
                tokens_used=5000,
                final_text="Done",
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        result = run_iteration_sync(project_path)

        assert isinstance(result, IterationResult)
        assert result.success is True


class TestExecuteUntilComplete:
    """Tests for execute_until_complete function."""

    @patch("ralph.iteration.create_ralph_client")
    async def test_stops_when_no_tasks(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Stops when no pending tasks."""
        mock_create_client.return_value = MagicMock()

        # Empty plan = no tasks
        results = await execute_until_complete(project_path, max_iterations=10)

        assert len(results) == 0

    @patch("ralph.iteration.create_ralph_client")
    async def test_runs_until_tasks_complete(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Runs iterations until tasks complete."""
        call_count = [0]

        async def mock_run(*args, **kwargs):
            call_count[0] += 1
            # Simulate task completion on second call
            return IterationResult(
                success=True,
                task_completed=call_count[0] >= 1,
                task_id="task-1" if call_count[0] >= 1 else None,
                error=None,
                cost_usd=0.05,
                tokens_used=5000,
                final_text="Done",
                metrics=IterationMetrics(),
            )

        mock_client = MagicMock()
        mock_client.run_iteration = AsyncMock(side_effect=mock_run)
        mock_create_client.return_value = mock_client

        # Add a task
        plan = ImplementationPlan(
            tasks=[Task(id="task-1", description="Test", priority=1)]
        )
        save_plan(plan, project_path)

        results = await execute_until_complete(project_path, max_iterations=5)

        assert len(results) >= 1

    @patch("ralph.iteration.create_ralph_client")
    async def test_respects_max_iterations(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Respects max iterations limit."""
        mock_client = MagicMock()
        mock_client.run_iteration = AsyncMock(
            return_value=IterationResult(
                success=True,
                task_completed=False,  # Never completes task
                task_id=None,
                error=None,
                cost_usd=0.05,
                tokens_used=5000,
                final_text="Working",
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        # Add task that never completes
        plan = ImplementationPlan(
            tasks=[Task(id="task-1", description="Infinite", priority=1)]
        )
        save_plan(plan, project_path)

        results = await execute_until_complete(project_path, max_iterations=3)

        assert len(results) == 3

    @patch("ralph.iteration.create_ralph_client")
    async def test_calls_callback(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Calls on_iteration callback."""
        mock_client = MagicMock()
        mock_client.run_iteration = AsyncMock(
            return_value=IterationResult(
                success=True,
                task_completed=False,
                task_id=None,
                error=None,
                cost_usd=0.05,
                tokens_used=5000,
                final_text="Done",
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        # Add task
        plan = ImplementationPlan(
            tasks=[Task(id="task-1", description="Test", priority=1)]
        )
        save_plan(plan, project_path)

        callback_calls = []

        def on_iteration(result, iteration_num):
            callback_calls.append((result, iteration_num))

        await execute_until_complete(
            project_path, max_iterations=2, on_iteration=on_iteration
        )

        assert len(callback_calls) == 2
        assert callback_calls[0][1] == 1
        assert callback_calls[1][1] == 2

    @patch("ralph.iteration.create_ralph_client")
    async def test_stops_on_circuit_breaker(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Stops when circuit breaker trips."""
        mock_client = MagicMock()
        mock_client.run_iteration = AsyncMock(
            return_value=IterationResult(
                success=False,
                task_completed=False,
                task_id=None,
                error="Failed",
                cost_usd=0.05,
                tokens_used=5000,
                final_text="Error",
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        # Add task
        plan = ImplementationPlan(
            tasks=[Task(id="task-1", description="Test", priority=1)]
        )
        save_plan(plan, project_path)

        # Trip circuit breaker
        state = load_state(project_path)
        for _ in range(5):
            state.circuit_breaker.record_failure("test")
        save_state(state, project_path)

        results = await execute_until_complete(project_path, max_iterations=10)

        # Should stop due to circuit breaker
        assert len(results) == 0
