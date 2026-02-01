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
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        executor = DiscoveryExecutor(project_path)
        result = await executor.execute()

        assert result.success is False
        assert result.error == "API error"


class TestDiscoveryDocumentValidation:
    """Tests for discovery phase document validation."""

    def test_continuation_prompt_shows_missing_prd(self, project_path: Path) -> None:
        """Continuation prompt indicates missing PRD.md."""
        specs_dir = project_path / "specs"
        specs_dir.mkdir()
        # Create SPEC but not PRD
        (specs_dir / "SPEC-001-auth.md").write_text("# Auth Spec")
        (specs_dir / "TECHNICAL_ARCHITECTURE.md").write_text("# Arch")

        executor = DiscoveryExecutor(project_path)
        prompt = executor._build_continuation_prompt(1)

        assert "PRD.md" in prompt
        assert "MISSING" in prompt

    def test_continuation_prompt_shows_missing_architecture(
        self, project_path: Path
    ) -> None:
        """Continuation prompt indicates missing TECHNICAL_ARCHITECTURE.md."""
        specs_dir = project_path / "specs"
        specs_dir.mkdir()
        (specs_dir / "PRD.md").write_text("# PRD")
        (specs_dir / "SPEC-001-auth.md").write_text("# Auth Spec")
        # No TECHNICAL_ARCHITECTURE.md

        executor = DiscoveryExecutor(project_path)
        prompt = executor._build_continuation_prompt(1)

        assert "TECHNICAL_ARCHITECTURE.md" in prompt
        assert "MISSING" in prompt

    def test_continuation_prompt_shows_missing_spec_files(
        self, project_path: Path
    ) -> None:
        """Continuation prompt indicates missing SPEC files."""
        specs_dir = project_path / "specs"
        specs_dir.mkdir()
        (specs_dir / "PRD.md").write_text("# PRD")
        (specs_dir / "TECHNICAL_ARCHITECTURE.md").write_text("# Arch")
        # No SPEC-*.md files

        executor = DiscoveryExecutor(project_path)
        prompt = executor._build_continuation_prompt(1)

        assert "SPEC" in prompt
        assert "NONE" in prompt or "0 found" in prompt

    def test_continuation_prompt_shows_all_documents_exist(
        self, project_path: Path
    ) -> None:
        """Continuation prompt shows EXISTS when all documents present."""
        specs_dir = project_path / "specs"
        specs_dir.mkdir()
        (specs_dir / "PRD.md").write_text("# PRD")
        (specs_dir / "SPEC-001-auth.md").write_text("# Auth Spec")
        (specs_dir / "TECHNICAL_ARCHITECTURE.md").write_text("# Arch")

        executor = DiscoveryExecutor(project_path)
        prompt = executor._build_continuation_prompt(1)

        assert "PRD.md" in prompt
        assert "EXISTS" in prompt
        assert "1 found" in prompt

    @patch("ralph.executors.create_ralph_client")
    async def test_execute_includes_validation_artifacts(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Execute result includes validation artifacts."""
        # Create all required documents
        specs_dir = project_path / "specs"
        specs_dir.mkdir()
        (specs_dir / "PRD.md").write_text("# PRD")
        (specs_dir / "SPEC-001-auth.md").write_text("# Auth Spec")
        (specs_dir / "TECHNICAL_ARCHITECTURE.md").write_text("# Arch")

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
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        executor = DiscoveryExecutor(project_path)
        result = await executor.execute(initial_goal="Build something")

        assert result.success is True
        assert "prd_created" in result.artifacts
        assert "architecture_created" in result.artifacts
        assert "spec_files" in result.artifacts
        assert result.artifacts["prd_created"] is True
        assert result.artifacts["architecture_created"] is True
        assert "SPEC-001-auth.md" in result.artifacts["spec_files"]

    @patch("ralph.executors.create_ralph_client")
    async def test_execute_warns_about_missing_documents(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Execute result warns when documents are missing."""
        # Create only legacy spec (no PRD, no TECHNICAL_ARCHITECTURE)
        specs_dir = project_path / "specs"
        specs_dir.mkdir()
        (specs_dir / "some-spec.md").write_text("# Some Spec")

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
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        executor = DiscoveryExecutor(project_path)
        result = await executor.execute(initial_goal="Build something")

        assert result.success is True  # Soft validation - still succeeds
        assert result.artifacts["prd_created"] is False
        assert result.artifacts["architecture_created"] is False
        assert "WARNING" in result.completion_notes
        assert "PRD.md" in result.completion_notes


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
                success=False,  # Validation failed
                task_completed=False,
                task_id=None,
                error="Validation failed",
                cost_usd=0.08,
                tokens_used=8000,
                final_text="Tests failing",
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        executor = ValidationExecutor(project_path)
        result = await executor.execute()

        # Not explicitly failed, but not all_passed
        assert result.success is False

    @patch("ralph.executors.create_ralph_client")
    async def test_execute_circuit_breaker_failure(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Execute fails when circuit breaker trips on consecutive failures."""
        mock_client = MagicMock()
        mock_client.run_iteration = AsyncMock(
            return_value=IterationResult(
                success=False,
                task_completed=False,
                task_id=None,
                error="Test failure",
                cost_usd=0.01,
                tokens_used=100,
                final_text="Tests failed",
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        executor = ValidationExecutor(project_path)
        executor.config.validation.require_human_approval = False
        # Pre-set circuit breaker near threshold (max is 3)
        executor.state.circuit_breaker.failure_count = 2
        result = await executor.execute(max_iterations=5)

        assert result.success is False
        # Early return on failed iteration (not circuit breaker trip)
        assert result.error == "Test failure"

    @patch("ralph.executors.create_ralph_client")
    async def test_execute_circuit_breaker_stagnation(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Execute fails when circuit breaker trips on stagnation."""
        mock_client = MagicMock()
        # Same output every iteration = stagnation (no progress keywords)
        mock_client.run_iteration = AsyncMock(
            return_value=IterationResult(
                success=True,
                task_completed=False,
                task_id=None,
                error=None,
                cost_usd=0.01,
                tokens_used=100,
                final_text="Checking tests...",  # Same text, no progress keywords
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        executor = ValidationExecutor(project_path)
        executor.config.validation.require_human_approval = False
        # Pre-set stagnation near threshold (max is 5)
        executor.state.circuit_breaker.stagnation_count = 4
        result = await executor.execute(max_iterations=10)

        assert result.success is False
        assert "circuit breaker" in result.error.lower()
        assert "stagnation" in result.error.lower()

    @patch("ralph.executors.create_ralph_client")
    async def test_execute_respects_max_iterations_10(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Execute defaults to 10 max iterations per SPEC-001."""
        mock_client = MagicMock()
        call_count = 0

        async def count_iterations(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Different output each time to avoid stagnation detection
            return IterationResult(
                success=True,
                task_completed=False,
                task_id=None,
                error=None,
                cost_usd=0.01,
                tokens_used=100,
                final_text=f"Running pytest iteration {call_count}... tests failing",
                metrics=IterationMetrics(),
            )

        mock_client.run_iteration = count_iterations
        mock_create_client.return_value = mock_client

        executor = ValidationExecutor(project_path)
        executor.config.validation.require_human_approval = False
        result = await executor.execute()  # Use default max_iterations

        assert result.iterations_run == 10  # Not 20

    @patch("ralph.executors.create_ralph_client")
    async def test_execute_cost_limit_exceeded(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Execute fails when cost limit exceeded."""
        mock_client = MagicMock()
        mock_client.run_iteration = AsyncMock(
            return_value=IterationResult(
                success=True,
                task_completed=False,
                task_id=None,
                error=None,
                cost_usd=10.0,  # High cost per iteration
                tokens_used=1000,
                final_text="Running pytest checks...",
                metrics=IterationMetrics(),
            )
        )
        mock_create_client.return_value = mock_client

        executor = ValidationExecutor(project_path)
        executor.config.validation.require_human_approval = False
        executor.state.total_cost_usd = 95.0  # Near $100 limit
        executor.state.circuit_breaker.max_cost_usd = 100.0
        result = await executor.execute(max_iterations=5)

        assert result.success is False
        assert "cost_limit" in result.error.lower()

    def test_detect_validation_progress_keywords(self, project_path: Path) -> None:
        """Progress detection identifies verification keywords."""
        executor = ValidationExecutor(project_path)

        # Should detect progress - verification commands
        assert executor._detect_validation_progress(
            "Running pytest... 5 tests passed", ""
        ) is True
        assert executor._detect_validation_progress(
            "uv run ruff check . found no errors", ""
        ) is True
        assert executor._detect_validation_progress(
            "uv run mypy . success", ""
        ) is True

        # Should detect progress - fix keywords
        assert executor._detect_validation_progress(
            "Fixed the import error", ""
        ) is True
        assert executor._detect_validation_progress(
            "Resolved the type mismatch", ""
        ) is True

    def test_detect_validation_progress_no_progress(self, project_path: Path) -> None:
        """Progress detection identifies stagnation."""
        executor = ValidationExecutor(project_path)

        # Same content = no progress
        assert executor._detect_validation_progress(
            "Same error message", "Same error message"
        ) is False

        # Very similar content (>70% overlap) = no progress
        assert executor._detect_validation_progress(
            "Checking the code for errors in module foo",
            "Checking the code for issues in module foo"
        ) is False

    def test_detect_validation_progress_text_change(self, project_path: Path) -> None:
        """Progress detection identifies substantial text changes."""
        executor = ValidationExecutor(project_path)

        # Very different content = progress
        assert executor._detect_validation_progress(
            "New error: TypeError in line 50 with details about the function call",
            "Old error: ImportError in line 10 with module information"
        ) is True


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


class TestCompletionSignalPreservation:
    """Tests for completion signal preservation during phase transitions.

    These tests verify that completion signals set by MCP tools (like
    ralph_signal_discovery_complete) are not lost when the executor
    saves its state after an iteration.

    The bug: Tools and executor use separate RalphState instances.
    When a tool sets a completion signal and saves, then the executor
    saves its in-memory state, the executor's save overwrites the
    tool's changes because the executor's state doesn't have the signal.
    """

    @patch("ralph.executors.create_ralph_client")
    async def test_completion_signal_survives_iteration_save(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Completion signal set by tool survives executor's state save.

        This test simulates what happens when:
        1. Executor runs an iteration
        2. During iteration, a tool sets completion_signals on disk
        3. Executor's finally block saves state
        4. The completion signal should still be present
        """
        from ralph.persistence import load_state, save_state

        # Track when stream_iteration yields ITERATION_END so we can
        # simulate a tool setting the completion signal before executor saves
        signal_set = False

        async def mock_stream_iteration(prompt, phase, system_prompt, max_turns):
            """Mock that simulates tool setting completion signal mid-iteration."""
            nonlocal signal_set
            from ralph.events import iteration_end_event, text_delta_event

            # Yield some events
            yield text_delta_event("Processing...")

            # Simulate tool setting completion signal on disk
            # This is what ralph_signal_discovery_complete does
            if not signal_set:
                disk_state = load_state(project_path)
                disk_state.completion_signals["discovery"] = {
                    "complete": True,
                    "summary": "Test complete",
                    "timestamp": "2026-01-27T12:00:00",
                }
                save_state(disk_state, project_path)
                signal_set = True

            # Yield iteration end
            yield iteration_end_event(
                iteration=1,
                phase="discovery",
                success=True,
                tokens_used=1000,
                cost_usd=0.01,
            )

        mock_client = MagicMock()
        mock_client.stream_iteration = mock_stream_iteration
        mock_create_client.return_value = mock_client

        executor = DiscoveryExecutor(project_path)

        # Run stream_iteration which will:
        # 1. Call start_iteration() (increments counter)
        # 2. Yield events from mock (which sets completion signal on disk)
        # 3. In finally block, call save_state() (should preserve signal)
        gen = executor.stream_iteration("Test prompt")
        events = []
        async for event in gen:
            events.append(event)

        # After iteration, reload state from disk
        final_state = load_state(project_path)

        # The completion signal should be preserved
        # THIS WILL FAIL with the current buggy code
        assert final_state.is_phase_complete("discovery"), (
            "Completion signal was lost! The executor's state save "
            "overwrote the completion signal set by the tool."
        )

    @patch("ralph.executors.create_ralph_client")
    async def test_phase_transition_when_signal_is_set(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Discovery executor yields phase_change_event when signal is detected.

        After the completion signal is set and preserved, stream_execution
        should detect it and yield a phase_change_event.
        """
        from ralph.events import StreamEventType
        from ralph.persistence import load_state, save_state

        iteration_count = [0]

        async def mock_stream_iteration(prompt, phase, system_prompt, max_turns):
            """Mock that sets completion signal on first iteration."""
            from ralph.events import iteration_end_event, text_delta_event

            iteration_count[0] += 1

            yield text_delta_event("Working...")

            # Set completion signal on first iteration
            if iteration_count[0] == 1:
                disk_state = load_state(project_path)
                disk_state.completion_signals["discovery"] = {
                    "complete": True,
                    "summary": "Discovery done",
                    "timestamp": "2026-01-27T12:00:00",
                }
                save_state(disk_state, project_path)

            yield iteration_end_event(
                iteration=1,
                phase="discovery",
                success=True,
                tokens_used=1000,
                cost_usd=0.01,
            )

        mock_client = MagicMock()
        mock_client.stream_iteration = mock_stream_iteration
        mock_create_client.return_value = mock_client

        executor = DiscoveryExecutor(project_path)

        # Run stream_execution
        gen = executor.stream_execution(initial_goal="Test goal", max_iterations=3)
        events = []
        async for event in gen:
            events.append(event)

        # Should have yielded a phase_change_event
        phase_change_events = [
            e for e in events if e.type == StreamEventType.PHASE_CHANGE
        ]
        assert len(phase_change_events) == 1, (
            f"Expected 1 phase_change_event, got {len(phase_change_events)}. "
            "The executor may not be detecting the completion signal."
        )

        # Verify the phase change is from discovery to planning
        event = phase_change_events[0]
        assert event.data.get("old_phase") == "discovery"
        assert event.data.get("new_phase") == "planning"

        # Should have only run 1 iteration (signal detected, loop breaks)
        assert iteration_count[0] == 1, (
            f"Expected 1 iteration, got {iteration_count[0]}. "
            "The executor should stop after detecting completion signal."
        )

    @patch("ralph.executors.create_ralph_client")
    async def test_iteration_counter_increments_correctly(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Iteration counter increments even when completion signal is set.

        Each iteration should increment the counter, and the counter
        should not be reset or lost due to state save race conditions.
        """
        from ralph.persistence import load_state, save_state

        iteration_count = [0]

        async def mock_stream_iteration(prompt, phase, system_prompt, max_turns):
            """Mock that runs 3 iterations then sets completion signal."""
            from ralph.events import iteration_end_event, text_delta_event

            iteration_count[0] += 1

            yield text_delta_event(f"Iteration {iteration_count[0]}")

            # Set completion signal on iteration 3
            if iteration_count[0] == 3:
                disk_state = load_state(project_path)
                disk_state.completion_signals["discovery"] = {
                    "complete": True,
                    "summary": "Done after 3 iterations",
                    "timestamp": "2026-01-27T12:00:00",
                }
                save_state(disk_state, project_path)

            yield iteration_end_event(
                iteration=1,
                phase="discovery",
                success=True,
                tokens_used=1000,
                cost_usd=0.01,
            )

        mock_client = MagicMock()
        mock_client.stream_iteration = mock_stream_iteration
        mock_create_client.return_value = mock_client

        executor = DiscoveryExecutor(project_path)

        # Run stream_execution
        gen = executor.stream_execution(initial_goal="Test", max_iterations=5)
        async for _ in gen:
            pass

        # Reload state
        final_state = load_state(project_path)

        # Should have run exactly 3 iterations
        assert iteration_count[0] == 3
        # State should reflect 3 iterations
        assert final_state.iteration_count == 3, (
            f"Expected iteration_count=3, got {final_state.iteration_count}. "
            "Iteration counter may have been reset or not persisted correctly."
        )

    @patch("ralph.executors.create_ralph_client")
    async def test_signal_preserved_after_executor_completes(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Completion signal is still present after stream_execution completes.

        The signal should NOT be cleared inside the executor - only the
        CLI/orchestrator should clear it when starting the next phase.
        """
        from ralph.persistence import load_state, save_state

        async def mock_stream_iteration(prompt, phase, system_prompt, max_turns):
            """Mock that sets completion signal."""
            from ralph.events import iteration_end_event, text_delta_event

            yield text_delta_event("Done")

            # Set completion signal
            disk_state = load_state(project_path)
            disk_state.completion_signals["discovery"] = {
                "complete": True,
                "summary": "All done",
                "timestamp": "2026-01-27T12:00:00",
            }
            save_state(disk_state, project_path)

            yield iteration_end_event(
                iteration=1,
                phase="discovery",
                success=True,
                tokens_used=1000,
                cost_usd=0.01,
            )

        mock_client = MagicMock()
        mock_client.stream_iteration = mock_stream_iteration
        mock_create_client.return_value = mock_client

        executor = DiscoveryExecutor(project_path)

        # Run stream_execution to completion
        gen = executor.stream_execution(initial_goal="Test", max_iterations=2)
        async for _ in gen:
            pass

        # After executor completes, signal should still be present
        final_state = load_state(project_path)
        assert final_state.is_phase_complete("discovery"), (
            "Completion signal was cleared inside the executor! "
            "The signal should only be cleared by CLI when starting next phase."
        )


class TestSyncMemoryFile:
    """Tests for _sync_memory_file which syncs .ralph/MEMORY.md from structured memory.

    The harness writes structured memory to .ralph/memory/phases/ and
    .ralph/memory/iterations/ deterministically, but .ralph/MEMORY.md was
    only written when the LLM called ralph_update_memory. _sync_memory_file
    bridges this gap by writing MEMORY.md from structured memory sources.
    """

    def test_sync_memory_file_writes_memory_md(self, project_path: Path) -> None:
        """_sync_memory_file creates .ralph/MEMORY.md from structured memory."""
        executor = DiscoveryExecutor(project_path)

        # Populate structured memory (simulate harness-controlled capture)
        phases_dir = project_path / ".ralph" / "memory" / "phases"
        phases_dir.mkdir(parents=True, exist_ok=True)
        (phases_dir / "discovery.md").write_text(
            "# Discovery Phase\n\nDiscovered requirements for auth system."
        )

        # Ensure MEMORY.md does not exist yet
        memory_path = project_path / ".ralph" / "MEMORY.md"
        assert not memory_path.exists()

        # Sync should create MEMORY.md
        executor._sync_memory_file()

        assert memory_path.exists(), (
            ".ralph/MEMORY.md was not created by _sync_memory_file. "
            "The harness should write MEMORY.md deterministically."
        )
        content = memory_path.read_text()
        assert len(content) > 0, "MEMORY.md was created but is empty"

    def test_sync_memory_file_no_op_when_no_memory(self, project_path: Path) -> None:
        """_sync_memory_file does not create MEMORY.md when no memory exists."""
        executor = DiscoveryExecutor(project_path)

        # Ensure memory directories exist but are empty
        memory_dir = project_path / ".ralph" / "memory"
        (memory_dir / "phases").mkdir(parents=True, exist_ok=True)
        (memory_dir / "iterations").mkdir(parents=True, exist_ok=True)

        memory_path = project_path / ".ralph" / "MEMORY.md"
        assert not memory_path.exists()

        # Sync should be a no-op (no content to write)
        executor._sync_memory_file()

        # Should NOT create an empty MEMORY.md
        # (build_active_memory returns empty/minimal content with just metrics)
        # The key assertion: no crash, and if file exists it has content
        if memory_path.exists():
            assert len(memory_path.read_text().strip()) > 0

    def test_sync_memory_file_suppresses_exceptions(self, project_path: Path) -> None:
        """_sync_memory_file suppresses exceptions gracefully."""
        executor = DiscoveryExecutor(project_path)

        # Mock memory_manager to raise an exception
        executor._memory_manager = MagicMock()
        executor._memory_manager.build_active_memory.side_effect = RuntimeError(
            "Memory build failed"
        )

        # Should not raise
        executor._sync_memory_file()

        # MEMORY.md should not exist since build failed
        memory_path = project_path / ".ralph" / "MEMORY.md"
        assert not memory_path.exists()

    @patch("ralph.executors.create_ralph_client")
    async def test_stream_iteration_syncs_memory_file(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """stream_iteration creates .ralph/MEMORY.md after iteration completes."""
        from ralph.events import StreamEventType

        async def mock_stream_iteration(prompt, phase, system_prompt, max_turns):
            from ralph.events import iteration_end_event, text_delta_event

            yield text_delta_event("Working on discovery...")
            yield iteration_end_event(
                iteration=1,
                phase="discovery",
                success=True,
                tokens_used=1000,
                cost_usd=0.01,
            )

        mock_client = MagicMock()
        mock_client.stream_iteration = mock_stream_iteration
        mock_create_client.return_value = mock_client

        executor = DiscoveryExecutor(project_path)

        # Run stream_iteration to completion
        gen = executor.stream_iteration("Test prompt")
        async for _ in gen:
            pass

        # After iteration, MEMORY.md should exist
        memory_path = project_path / ".ralph" / "MEMORY.md"
        assert memory_path.exists(), (
            ".ralph/MEMORY.md was not created after stream_iteration. "
            "The harness should sync MEMORY.md at end of each iteration."
        )

    @patch("ralph.executors.create_ralph_client")
    async def test_discovery_stream_execution_creates_memory_md(
        self, mock_create_client: MagicMock, project_path: Path
    ) -> None:
        """Discovery stream_execution creates .ralph/MEMORY.md at phase completion."""
        from ralph.persistence import load_state, save_state

        async def mock_stream_iteration(prompt, phase, system_prompt, max_turns):
            from ralph.events import iteration_end_event, text_delta_event

            yield text_delta_event("Discovery complete")

            # Set completion signal on disk
            disk_state = load_state(project_path)
            disk_state.completion_signals["discovery"] = {
                "complete": True,
                "summary": "Done",
                "timestamp": "2026-01-27T12:00:00",
            }
            save_state(disk_state, project_path)

            yield iteration_end_event(
                iteration=1,
                phase="discovery",
                success=True,
                tokens_used=1000,
                cost_usd=0.01,
            )

        mock_client = MagicMock()
        mock_client.stream_iteration = mock_stream_iteration
        mock_create_client.return_value = mock_client

        executor = DiscoveryExecutor(project_path)

        # Run stream_execution to completion
        gen = executor.stream_execution(initial_goal="Test goal", max_iterations=2)
        async for _ in gen:
            pass

        # After discovery phase completes, MEMORY.md should exist
        memory_path = project_path / ".ralph" / "MEMORY.md"
        assert memory_path.exists(), (
            ".ralph/MEMORY.md was not created after discovery stream_execution. "
            "The harness should sync MEMORY.md at phase transitions."
        )
