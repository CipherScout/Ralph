"""Tests for phase implementations."""

from pathlib import Path

import pytest

from ralph.models import ImplementationPlan, Phase, RalphState, Task, TaskStatus
from ralph.persistence import initialize_plan, initialize_state, save_plan, save_state
from ralph.phases import (
    PhaseOrchestrator,
    PhaseResult,
    build_building_prompt,
    build_discovery_prompt,
    build_planning_prompt,
    build_validation_prompt,
    get_phase_prompt,
)


@pytest.fixture
def project_path(tmp_path: Path) -> Path:
    """Create an initialized project directory."""
    initialize_state(tmp_path)
    initialize_plan(tmp_path)
    return tmp_path


@pytest.fixture
def state(project_path: Path) -> RalphState:
    """Create a test state."""
    return RalphState(
        project_root=project_path,
        iteration_count=5,
        session_id="test-session",
    )


@pytest.fixture
def plan_with_tasks(project_path: Path) -> ImplementationPlan:
    """Create a plan with tasks."""
    plan = ImplementationPlan(
        tasks=[
            Task(
                id="task-1",
                description="First task",
                priority=1,
                status=TaskStatus.COMPLETE,
            ),
            Task(
                id="task-2",
                description="Second task",
                priority=2,
                status=TaskStatus.PENDING,
                dependencies=["task-1"],
            ),
            Task(
                id="task-3",
                description="Third task",
                priority=3,
                status=TaskStatus.PENDING,
                dependencies=["task-2"],
            ),
        ]
    )
    save_plan(plan, project_path)
    return plan


class TestPhaseOrchestrator:
    """Tests for PhaseOrchestrator."""

    def test_creation(self, project_path: Path) -> None:
        """Creates orchestrator successfully."""
        orchestrator = PhaseOrchestrator(project_path)
        assert orchestrator.project_root == project_path

    def test_lazy_loads_state(self, project_path: Path) -> None:
        """Lazily loads state on access."""
        orchestrator = PhaseOrchestrator(project_path)
        assert orchestrator._state is None
        _ = orchestrator.state
        assert orchestrator._state is not None

    def test_lazy_loads_plan(self, project_path: Path) -> None:
        """Lazily loads plan on access."""
        orchestrator = PhaseOrchestrator(project_path)
        assert orchestrator._plan is None
        _ = orchestrator.plan
        assert orchestrator._plan is not None

    def test_get_current_phase(self, project_path: Path) -> None:
        """Returns current phase."""
        orchestrator = PhaseOrchestrator(project_path)
        assert orchestrator.get_current_phase() == Phase.BUILDING

    def test_transition_to_phase(self, project_path: Path) -> None:
        """Transitions to new phase."""
        orchestrator = PhaseOrchestrator(project_path)
        orchestrator.transition_to(Phase.VALIDATION)
        assert orchestrator.state.current_phase == Phase.VALIDATION

    def test_should_pause(self, project_path: Path) -> None:
        """Checks paused state."""
        orchestrator = PhaseOrchestrator(project_path)
        assert orchestrator.should_pause() is False

        orchestrator.state.paused = True
        assert orchestrator.should_pause() is True

    def test_start_iteration(self, project_path: Path) -> None:
        """Starts iteration and returns context."""
        orchestrator = PhaseOrchestrator(project_path)
        context = orchestrator.start_iteration()

        assert context["iteration"] == 1
        assert context["phase"] == "building"
        assert "usage_percentage" in context

    def test_end_iteration_success(
        self, project_path: Path, plan_with_tasks: ImplementationPlan
    ) -> None:
        """Ends iteration successfully."""
        orchestrator = PhaseOrchestrator(project_path)
        orchestrator.start_iteration()

        result = orchestrator.end_iteration(
            cost_usd=0.05,
            tokens_used=5000,
            task_completed=True,
        )

        assert result.success is True
        assert result.tasks_completed == 1

    def test_end_iteration_triggers_handoff(self, project_path: Path) -> None:
        """Detects when handoff is needed."""
        orchestrator = PhaseOrchestrator(project_path)
        orchestrator.state.context_budget.add_usage(130_000)  # > 60%

        result = orchestrator.end_iteration(
            cost_usd=0.05,
            tokens_used=5000,
            task_completed=False,
        )

        assert result.needs_handoff is True
        assert result.handoff_reason is not None

    def test_check_circuit_breaker_closed(self, project_path: Path) -> None:
        """Circuit breaker closed by default."""
        orchestrator = PhaseOrchestrator(project_path)
        should_halt, reason = orchestrator.check_circuit_breaker()
        assert should_halt is False
        assert reason is None

    def test_check_circuit_breaker_open(self, project_path: Path) -> None:
        """Circuit breaker opens on failures."""
        orchestrator = PhaseOrchestrator(project_path)
        for _ in range(3):
            orchestrator.state.circuit_breaker.record_failure("test")

        should_halt, reason = orchestrator.check_circuit_breaker()
        assert should_halt is True
        assert "consecutive_failures" in reason


class TestPhaseTransitions:
    """Tests for phase transition logic."""

    def test_building_to_validation_when_complete(
        self, project_path: Path
    ) -> None:
        """Transitions from Building to Validation when all tasks done."""
        plan = initialize_plan(project_path)
        plan.tasks.append(
            Task(
                id="task-1",
                description="Only task",
                priority=1,
                status=TaskStatus.COMPLETE,
            )
        )
        save_plan(plan, project_path)

        orchestrator = PhaseOrchestrator(project_path)
        should_transition, next_phase = orchestrator._check_phase_transition()

        assert should_transition is True
        assert next_phase == Phase.VALIDATION

    def test_building_continues_with_pending_tasks(
        self, project_path: Path, plan_with_tasks: ImplementationPlan
    ) -> None:
        """Continues Building with pending tasks."""
        orchestrator = PhaseOrchestrator(project_path)
        should_transition, next_phase = orchestrator._check_phase_transition()

        assert should_transition is False
        assert next_phase is None

    def test_planning_to_building_when_tasks_ready(
        self, project_path: Path
    ) -> None:
        """Transitions from Planning to Building when tasks defined."""
        state = initialize_state(project_path)
        state.current_phase = Phase.PLANNING
        save_state(state, project_path)

        plan = initialize_plan(project_path)
        plan.tasks.append(
            Task(id="task-1", description="Ready task", priority=1)
        )
        save_plan(plan, project_path)

        orchestrator = PhaseOrchestrator(project_path)
        should_transition, next_phase = orchestrator._check_phase_transition()

        assert should_transition is True
        assert next_phase == Phase.BUILDING


class TestPhaseResult:
    """Tests for PhaseResult dataclass."""

    def test_default_values(self) -> None:
        """Has correct default values."""
        result = PhaseResult(success=True, phase=Phase.BUILDING)

        assert result.tasks_completed == 0
        assert result.tasks_blocked == 0
        assert result.error is None
        assert result.should_transition is False
        assert result.needs_handoff is False


class TestBuildDiscoveryPrompt:
    """Tests for build_discovery_prompt."""

    def test_includes_phase_name(self, project_path: Path) -> None:
        """Includes Discovery phase name."""
        prompt = build_discovery_prompt(project_path)
        assert "Discovery Phase" in prompt
        assert "JTBD" in prompt or "Jobs-to-be-Done" in prompt

    def test_includes_project_root(self, project_path: Path) -> None:
        """Includes project root path."""
        prompt = build_discovery_prompt(project_path)
        assert str(project_path) in prompt

    def test_includes_goal_when_provided(self, project_path: Path) -> None:
        """Includes goal when provided."""
        prompt = build_discovery_prompt(project_path, goal="Build a CLI tool")
        assert "Build a CLI tool" in prompt

    def test_includes_output_format(self, project_path: Path) -> None:
        """Includes requirements output format."""
        prompt = build_discovery_prompt(project_path)
        assert "FUNCTIONAL REQUIREMENTS" in prompt
        assert "NON-FUNCTIONAL REQUIREMENTS" in prompt


class TestBuildPlanningPrompt:
    """Tests for build_planning_prompt."""

    def test_includes_phase_name(self, project_path: Path) -> None:
        """Includes Planning phase name."""
        prompt = build_planning_prompt(project_path)
        assert "Planning Phase" in prompt

    def test_includes_task_sizing(self, project_path: Path) -> None:
        """Includes task sizing guidelines."""
        prompt = build_planning_prompt(project_path)
        assert "30,000 tokens" in prompt or "30000" in prompt

    def test_includes_dependency_rules(self, project_path: Path) -> None:
        """Includes dependency handling."""
        prompt = build_planning_prompt(project_path)
        assert "dependencies" in prompt.lower()

    def test_includes_memory_content(self, project_path: Path) -> None:
        """Includes MEMORY.md content if present."""
        memory_path = project_path / "MEMORY.md"
        memory_path.write_text("# Requirements\n\nTest requirements here")

        prompt = build_planning_prompt(project_path)
        assert "Test requirements here" in prompt


class TestBuildBuildingPrompt:
    """Tests for build_building_prompt."""

    def test_includes_phase_name(self, project_path: Path) -> None:
        """Includes Building phase name."""
        prompt = build_building_prompt(project_path)
        assert "Building Phase" in prompt

    def test_includes_current_task(self, project_path: Path) -> None:
        """Includes current task when provided."""
        task = Task(
            id="test-task",
            description="Implement feature X",
            priority=1,
            verification_criteria=["Tests pass", "Lint passes"],
        )
        prompt = build_building_prompt(project_path, task=task)

        assert "test-task" in prompt
        assert "Implement feature X" in prompt
        assert "Tests pass" in prompt

    def test_includes_backpressure_commands(self, project_path: Path) -> None:
        """Includes backpressure commands."""
        prompt = build_building_prompt(project_path)
        assert "backpressure" in prompt.lower() or "pytest" in prompt

    def test_includes_uv_rule(self, project_path: Path) -> None:
        """Includes uv-only rule."""
        prompt = build_building_prompt(project_path)
        assert "uv run" in prompt


class TestBuildValidationPrompt:
    """Tests for build_validation_prompt."""

    def test_includes_phase_name(self, project_path: Path) -> None:
        """Includes Validation phase name."""
        prompt = build_validation_prompt(project_path)
        assert "Validation Phase" in prompt

    def test_includes_validation_checklist(self, project_path: Path) -> None:
        """Includes validation checklist."""
        prompt = build_validation_prompt(project_path)
        assert "test" in prompt.lower()
        assert "lint" in prompt.lower()
        assert "type" in prompt.lower()

    def test_includes_output_format(self, project_path: Path) -> None:
        """Includes validation report format."""
        prompt = build_validation_prompt(project_path)
        assert "PASS" in prompt
        assert "FAIL" in prompt


class TestGetPhasePrompt:
    """Tests for get_phase_prompt."""

    def test_returns_discovery_prompt(self, project_path: Path) -> None:
        """Returns discovery prompt for discovery phase."""
        prompt = get_phase_prompt(Phase.DISCOVERY, project_path)
        assert "Discovery Phase" in prompt

    def test_returns_planning_prompt(self, project_path: Path) -> None:
        """Returns planning prompt for planning phase."""
        prompt = get_phase_prompt(Phase.PLANNING, project_path)
        assert "Planning Phase" in prompt

    def test_returns_building_prompt(self, project_path: Path) -> None:
        """Returns building prompt for building phase."""
        prompt = get_phase_prompt(Phase.BUILDING, project_path)
        assert "Building Phase" in prompt

    def test_returns_validation_prompt(self, project_path: Path) -> None:
        """Returns validation prompt for validation phase."""
        prompt = get_phase_prompt(Phase.VALIDATION, project_path)
        assert "Validation Phase" in prompt

    def test_passes_task_to_building(self, project_path: Path) -> None:
        """Passes task to building prompt."""
        task = Task(id="my-task", description="My task", priority=1)
        prompt = get_phase_prompt(Phase.BUILDING, project_path, task=task)
        assert "my-task" in prompt

    def test_passes_goal_to_discovery(self, project_path: Path) -> None:
        """Passes goal to discovery prompt."""
        prompt = get_phase_prompt(
            Phase.DISCOVERY, project_path, goal="Build a thing"
        )
        assert "Build a thing" in prompt
