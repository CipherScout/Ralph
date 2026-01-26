"""Tests for phase executors."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ralph.executors import (
    BuildingExecutor,
    DiscoveryExecutor,
    PhaseExecutionResult,
    PlanningExecutor,
    ValidationExecutor,
    get_executor_for_phase,
    run_full_workflow,
)
from ralph.models import ImplementationPlan, Phase, Task
from ralph.persistence import initialize_plan, initialize_state, save_plan
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
        final_text="Completed iteration",
        needs_handoff=False,
        metrics=IterationMetrics(),
    )


class TestPhaseExecutionResult:
    """Tests for PhaseExecutionResult dataclass."""

    def test_default_values(self) -> None:
        """Has correct default values."""
        result = PhaseExecutionResult(success=True, phase=Phase.BUILDING)
        assert result.iterations_run == 0
        assert result.tasks_completed == 0
        assert result.cost_usd == 0.0
        assert result.tokens_used == 0
        assert result.error is None
        assert result.completion_notes is None
        assert result.needs_phase_transition is False
        assert result.next_phase is None
        assert result.artifacts == {}

    def test_with_all_fields(self) -> None:
        """Can set all fields."""
        result = PhaseExecutionResult(
            success=True,
            phase=Phase.BUILDING,
            iterations_run=5,
            tasks_completed=3,
            cost_usd=0.50,
            tokens_used=25000,
            error=None,
            completion_notes="All done",
            needs_phase_transition=True,
            next_phase=Phase.VALIDATION,
            artifacts={"key": "value"},
        )
        assert result.success is True
        assert result.iterations_run == 5
        assert result.tasks_completed == 3
        assert result.needs_phase_transition is True
        assert result.next_phase == Phase.VALIDATION


class TestDiscoveryExecutor:
    """Tests for DiscoveryExecutor."""

    def test_phase_property(self, project_path: Path) -> None:
        """Returns correct phase."""
        executor = DiscoveryExecutor(project_path)
        assert executor.phase == Phase.DISCOVERY

    def test_state_property_loads(self, project_path: Path) -> None:
        """State property lazy loads state."""
        executor = DiscoveryExecutor(project_path)
        state = executor.state
        assert state.project_root == project_path

    def test_plan_property_loads(self, project_path: Path) -> None:
        """Plan property lazy loads plan."""
        executor = DiscoveryExecutor(project_path)
        plan = executor.plan
        assert isinstance(plan, ImplementationPlan)

    def test_get_system_prompt(self, project_path: Path) -> None:
        """Gets system prompt for discovery phase."""
        executor = DiscoveryExecutor(project_path)
        prompt = executor.get_system_prompt()
        assert "Discovery" in prompt

    @patch("ralph.executors.create_ralph_client")
    async def test_execute_success(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Execute completes successfully."""
        # Mock client
        mock_client = MagicMock()
        mock_client.run_iteration = AsyncMock(
            return_value=IterationResult(
                success=True,
                task_completed=False,
                task_id=None,
                error=None,
                cost_usd=0.05,
                tokens_used=5000,
                final_text="Discovery complete",
                needs_handoff=False,
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        executor = DiscoveryExecutor(project_path)
        result = await executor.execute(initial_goal="Build a CLI tool")

        assert result.success is True
        assert result.phase == Phase.DISCOVERY
        assert result.iterations_run >= 1
        assert result.needs_phase_transition is True
        assert result.next_phase == Phase.PLANNING

    @patch("ralph.executors.create_ralph_client")
    async def test_execute_with_failure(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Execute handles iteration failure."""
        mock_client = MagicMock()
        mock_client.run_iteration = AsyncMock(
            return_value=IterationResult(
                success=False,
                task_completed=False,
                task_id=None,
                error="API error",
                cost_usd=0.01,
                tokens_used=1000,
                final_text="",
                needs_handoff=False,
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        executor = DiscoveryExecutor(project_path)
        result = await executor.execute()

        assert result.success is False
        assert result.error == "API error"


class TestPlanningExecutor:
    """Tests for PlanningExecutor."""

    def test_phase_property(self, project_path: Path) -> None:
        """Returns correct phase."""
        executor = PlanningExecutor(project_path)
        assert executor.phase == Phase.PLANNING

    def test_get_system_prompt(self, project_path: Path) -> None:
        """Gets system prompt for planning phase."""
        executor = PlanningExecutor(project_path)
        prompt = executor.get_system_prompt()
        assert "Planning" in prompt

    @patch("ralph.executors.create_ralph_client")
    async def test_execute_creates_tasks(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Execute completes and reports task count."""
        mock_client = MagicMock()
        mock_client.run_iteration = AsyncMock(
            return_value=IterationResult(
                success=True,
                task_completed=False,
                task_id=None,
                error=None,
                cost_usd=0.10,
                tokens_used=10000,
                final_text="Planning complete",
                needs_handoff=False,
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        # Add a task to the plan
        plan = ImplementationPlan(
            tasks=[
                Task(id="task-1", description="Test task", priority=1),
            ]
        )
        save_plan(plan, project_path)

        executor = PlanningExecutor(project_path)
        result = await executor.execute()

        assert result.success is True
        assert result.phase == Phase.PLANNING
        assert result.needs_phase_transition is True
        assert result.next_phase == Phase.BUILDING
        assert result.artifacts.get("tasks_created") == 1


class TestBuildingExecutor:
    """Tests for BuildingExecutor."""

    def test_phase_property(self, project_path: Path) -> None:
        """Returns correct phase."""
        executor = BuildingExecutor(project_path)
        assert executor.phase == Phase.BUILDING

    def test_format_criteria_with_list(self, project_path: Path) -> None:
        """Formats verification criteria from list."""
        executor = BuildingExecutor(project_path)
        task = Task(
            id="task-1",
            description="Test",
            priority=1,
            verification_criteria=["Tests pass", "Lint clean"],
        )
        criteria = executor._format_criteria(task)
        assert "Tests pass" in criteria
        assert "Lint clean" in criteria

    def test_format_criteria_empty(self, project_path: Path) -> None:
        """Formats empty verification criteria."""
        executor = BuildingExecutor(project_path)
        task = Task(id="task-1", description="Test", priority=1)
        criteria = executor._format_criteria(task)
        assert criteria == "Implement and test"

    @patch("ralph.executors.create_ralph_client")
    async def test_execute_completes_task(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Execute completes a task successfully."""
        mock_client = MagicMock()
        mock_client.run_iteration = AsyncMock(
            return_value=IterationResult(
                success=True,
                task_completed=True,
                task_id="task-1",
                error=None,
                cost_usd=0.15,
                tokens_used=15000,
                final_text="Task completed",
                needs_handoff=False,
                metrics=IterationMetrics(),
            )
        )
        mock_client.reset_session = MagicMock()
        mock_create_client.return_value = mock_client

        # Add task to plan
        plan = ImplementationPlan(
            tasks=[
                Task(id="task-1", description="Build feature", priority=1),
            ]
        )
        save_plan(plan, project_path)

        executor = BuildingExecutor(project_path)
        result = await executor.execute()

        assert result.success is True
        assert result.phase == Phase.BUILDING
        assert result.tasks_completed >= 1

    @patch("ralph.executors.create_ralph_client")
    async def test_execute_target_task(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Execute can target a specific task."""
        mock_client = MagicMock()
        mock_client.run_iteration = AsyncMock(
            return_value=IterationResult(
                success=True,
                task_completed=True,
                task_id="task-2",
                error=None,
                cost_usd=0.10,
                tokens_used=10000,
                final_text="Task done",
                needs_handoff=False,
                metrics=IterationMetrics(),
            )
        )
        mock_client.reset_session = MagicMock()
        mock_create_client.return_value = mock_client

        # Add multiple tasks
        plan = ImplementationPlan(
            tasks=[
                Task(id="task-1", description="First", priority=1),
                Task(id="task-2", description="Second", priority=2),
            ]
        )
        save_plan(plan, project_path)

        executor = BuildingExecutor(project_path)
        result = await executor.execute(target_task_id="task-2")

        assert result.success is True
        # Should have attempted to work on task-2

    @patch("ralph.executors.create_ralph_client")
    async def test_execute_handles_not_found_task(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Execute fails gracefully for non-existent task."""
        mock_create_client.return_value = MagicMock()

        executor = BuildingExecutor(project_path)
        result = await executor.execute(target_task_id="nonexistent")

        assert result.success is False
        assert "not found" in result.error.lower()

    @patch("ralph.executors.create_ralph_client")
    async def test_execute_no_tasks(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Execute completes when no tasks available."""
        mock_create_client.return_value = MagicMock()

        executor = BuildingExecutor(project_path)
        result = await executor.execute()

        assert result.success is True
        assert result.tasks_completed == 0


class TestValidationExecutor:
    """Tests for ValidationExecutor."""

    def test_phase_property(self, project_path: Path) -> None:
        """Returns correct phase."""
        executor = ValidationExecutor(project_path)
        assert executor.phase == Phase.VALIDATION

    def test_get_system_prompt(self, project_path: Path) -> None:
        """Gets system prompt for validation phase."""
        executor = ValidationExecutor(project_path)
        prompt = executor.get_system_prompt()
        assert "Validation" in prompt

    @patch("ralph.executors.create_ralph_client")
    async def test_execute_passes_validation(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Execute passes when validation complete."""
        mock_client = MagicMock()
        mock_client.run_iteration = AsyncMock(
            return_value=IterationResult(
                success=True,
                task_completed=False,
                task_id=None,
                error=None,
                cost_usd=0.08,
                tokens_used=8000,
                final_text="Validation complete - all tests pass",
                needs_handoff=False,
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        executor = ValidationExecutor(project_path)
        # Ensure human approval is not required for this test
        executor.config.validation.require_human_approval = False
        result = await executor.execute()

        assert result.success is True
        assert result.phase == Phase.VALIDATION

    @patch("ralph.executors.create_ralph_client")
    async def test_execute_fails_validation(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Execute fails when validation incomplete."""
        mock_client = MagicMock()
        mock_client.run_iteration = AsyncMock(
            return_value=IterationResult(
                success=True,
                task_completed=False,
                task_id=None,
                error=None,
                cost_usd=0.08,
                tokens_used=8000,
                final_text="Tests failing",
                needs_handoff=True,  # Forces exit before completion
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        executor = ValidationExecutor(project_path)
        result = await executor.execute()

        # Not explicitly failed, but not all_passed
        assert result.success is False


class TestGetExecutorForPhase:
    """Tests for get_executor_for_phase function."""

    def test_discovery_executor(self, project_path: Path) -> None:
        """Returns DiscoveryExecutor for DISCOVERY phase."""
        executor = get_executor_for_phase(Phase.DISCOVERY, project_path)
        assert isinstance(executor, DiscoveryExecutor)

    def test_planning_executor(self, project_path: Path) -> None:
        """Returns PlanningExecutor for PLANNING phase."""
        executor = get_executor_for_phase(Phase.PLANNING, project_path)
        assert isinstance(executor, PlanningExecutor)

    def test_building_executor(self, project_path: Path) -> None:
        """Returns BuildingExecutor for BUILDING phase."""
        executor = get_executor_for_phase(Phase.BUILDING, project_path)
        assert isinstance(executor, BuildingExecutor)

    def test_validation_executor(self, project_path: Path) -> None:
        """Returns ValidationExecutor for VALIDATION phase."""
        executor = get_executor_for_phase(Phase.VALIDATION, project_path)
        assert isinstance(executor, ValidationExecutor)

    def test_with_preloaded_state(self, project_path: Path) -> None:
        """Can pass preloaded state."""
        from ralph.persistence import load_state

        state = load_state(project_path)
        executor = get_executor_for_phase(Phase.BUILDING, project_path, state=state)
        assert executor._state is state


class TestRunFullWorkflow:
    """Tests for run_full_workflow function."""

    @patch("ralph.executors.get_executor_for_phase")
    async def test_runs_all_phases(
        self, mock_get_executor: MagicMock, project_path: Path
    ) -> None:
        """Runs through all phases when successful."""
        # Create mock executors that return success and transition
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(
            return_value=PhaseExecutionResult(
                success=True,
                phase=Phase.DISCOVERY,
                needs_phase_transition=True,
                next_phase=Phase.PLANNING,
            )
        )
        mock_get_executor.return_value = mock_executor

        results = await run_full_workflow(project_path, initial_goal="Test")

        assert len(results) >= 1
        assert mock_get_executor.called

    @patch("ralph.executors.get_executor_for_phase")
    async def test_stops_on_failure(
        self, mock_get_executor: MagicMock, project_path: Path
    ) -> None:
        """Stops when a phase fails."""
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(
            return_value=PhaseExecutionResult(
                success=False,
                phase=Phase.PLANNING,
                error="Failed to create plan",
            )
        )
        mock_get_executor.return_value = mock_executor

        results = await run_full_workflow(project_path, start_phase=Phase.PLANNING)

        assert len(results) == 1
        assert results[0].success is False

    @patch("ralph.executors.get_executor_for_phase")
    async def test_stops_when_no_transition(
        self, mock_get_executor: MagicMock, project_path: Path
    ) -> None:
        """Stops when phase doesn't need transition."""
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(
            return_value=PhaseExecutionResult(
                success=True,
                phase=Phase.BUILDING,
                needs_phase_transition=False,  # No transition
            )
        )
        mock_get_executor.return_value = mock_executor

        results = await run_full_workflow(project_path, start_phase=Phase.BUILDING)

        assert len(results) == 1

    @patch("ralph.executors.get_executor_for_phase")
    async def test_start_from_specific_phase(
        self, mock_get_executor: MagicMock, project_path: Path
    ) -> None:
        """Can start from a specific phase."""
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(
            return_value=PhaseExecutionResult(
                success=True,
                phase=Phase.VALIDATION,
                needs_phase_transition=False,
            )
        )
        mock_get_executor.return_value = mock_executor

        results = await run_full_workflow(project_path, start_phase=Phase.VALIDATION)

        # Should only call executor once (for VALIDATION)
        assert len(results) == 1


class TestPhaseExecutorSaveOperations:
    """Tests for save operations in PhaseExecutor."""

    def test_save_state(self, project_path: Path) -> None:
        """save_state persists changes."""
        from ralph.persistence import load_state

        executor = DiscoveryExecutor(project_path)
        executor.state.iteration_count = 42
        executor.save_state()

        reloaded = load_state(project_path)
        assert reloaded.iteration_count == 42

    def test_save_plan(self, project_path: Path) -> None:
        """save_plan persists changes."""
        from ralph.persistence import load_plan

        executor = PlanningExecutor(project_path)
        executor.plan.tasks.append(
            Task(id="new-task", description="New", priority=1)
        )
        executor.save_plan()

        reloaded = load_plan(project_path)
        assert len(reloaded.tasks) == 1
        assert reloaded.tasks[0].id == "new-task"
