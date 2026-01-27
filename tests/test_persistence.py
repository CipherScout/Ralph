"""Tests for the persistence layer."""

from datetime import datetime
from pathlib import Path

import pytest

from ralph.models import (
    CircuitBreakerState,
    ContextBudget,
    ImplementationPlan,
    Phase,
    RalphState,
    Task,
    TaskStatus,
)
from ralph.persistence import (
    CorruptedStateError,
    StateNotFoundError,
    initialize_plan,
    initialize_state,
    load_plan,
    load_state,
    plan_exists,
    save_plan,
    save_state,
    state_exists,
)


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    return tmp_path / "test_project"


@pytest.fixture
def sample_state(temp_project: Path) -> RalphState:
    """Create a sample RalphState for testing."""
    return RalphState(
        project_root=temp_project,
        current_phase=Phase.BUILDING,
        iteration_count=5,
        session_id="test-session-123",
        total_cost_usd=1.50,
        total_tokens_used=50000,
        started_at=datetime(2025, 1, 15, 10, 0, 0),
        last_activity_at=datetime(2025, 1, 15, 11, 30, 0),
        circuit_breaker=CircuitBreakerState(
            max_consecutive_failures=5,
            max_stagnation_iterations=10,
            max_cost_usd=50.0,
            state="closed",
            failure_count=1,
            stagnation_count=2,
            last_failure_reason=None,
        ),
        context_budget=ContextBudget(
            total_capacity=200000,
            system_prompt_allocation=5000,
            safety_margin=0.20,
            current_usage=80000,
            tool_results_tokens=30000,
        ),
        session_cost_usd=0.75,
        session_tokens_used=25000,
        tasks_completed_this_session=2,
    )


@pytest.fixture
def sample_plan() -> ImplementationPlan:
    """Create a sample ImplementationPlan for testing."""
    return ImplementationPlan(
        tasks=[
            Task(
                id="task-1",
                description="First task",
                priority=1,
                status=TaskStatus.COMPLETE,
                dependencies=[],
                verification_criteria=["Test passes"],
                estimated_tokens=20000,
                actual_tokens_used=18000,
                completion_notes="Done successfully",
                completed_at=datetime(2025, 1, 15, 10, 30, 0),
                retry_count=0,
                spec_files=["specs/SPEC-001-auth.md", "specs/PRD.md"],
            ),
            Task(
                id="task-2",
                description="Second task",
                priority=2,
                status=TaskStatus.PENDING,
                dependencies=["task-1"],
                verification_criteria=["Integration works"],
                estimated_tokens=30000,
                actual_tokens_used=None,
                completion_notes=None,
                completed_at=None,
                retry_count=0,
                spec_files=[],
            ),
            Task(
                id="task-3",
                description="Third task",
                priority=3,
                status=TaskStatus.BLOCKED,
                dependencies=["task-2"],
                verification_criteria=["All green"],
                estimated_tokens=25000,
                actual_tokens_used=None,
                completion_notes="BLOCKED: Waiting for API",
                completed_at=None,
                retry_count=1,
            ),
        ],
        created_at=datetime(2025, 1, 15, 9, 0, 0),
        last_modified=datetime(2025, 1, 15, 11, 0, 0),
    )


class TestStateExistsAndPlanExists:
    """Tests for existence check functions."""

    def test_state_exists_false_when_missing(self, temp_project: Path) -> None:
        """State exists returns false when no state file."""
        temp_project.mkdir(parents=True)
        assert state_exists(temp_project) is False

    def test_plan_exists_false_when_missing(self, temp_project: Path) -> None:
        """Plan exists returns false when no plan file."""
        temp_project.mkdir(parents=True)
        assert plan_exists(temp_project) is False

    def test_state_exists_true_after_save(
        self, temp_project: Path, sample_state: RalphState
    ) -> None:
        """State exists returns true after saving."""
        temp_project.mkdir(parents=True)
        save_state(sample_state, temp_project)
        assert state_exists(temp_project) is True

    def test_plan_exists_true_after_save(
        self, temp_project: Path, sample_plan: ImplementationPlan
    ) -> None:
        """Plan exists returns true after saving."""
        temp_project.mkdir(parents=True)
        save_plan(sample_plan, temp_project)
        assert plan_exists(temp_project) is True


class TestSaveAndLoadState:
    """Tests for state save/load operations."""

    def test_save_creates_ralph_dir(
        self, temp_project: Path, sample_state: RalphState
    ) -> None:
        """Save creates .ralph directory if missing."""
        temp_project.mkdir(parents=True)
        save_state(sample_state, temp_project)
        assert (temp_project / ".ralph").is_dir()

    def test_save_creates_state_file(
        self, temp_project: Path, sample_state: RalphState
    ) -> None:
        """Save creates state.json file."""
        temp_project.mkdir(parents=True)
        path = save_state(sample_state, temp_project)
        assert path.exists()
        assert path.name == "state.json"

    def test_round_trip_preserves_data(
        self, temp_project: Path, sample_state: RalphState
    ) -> None:
        """Save then load preserves all state data."""
        temp_project.mkdir(parents=True)
        save_state(sample_state, temp_project)
        loaded = load_state(temp_project)

        assert loaded.project_root == sample_state.project_root
        assert loaded.current_phase == sample_state.current_phase
        assert loaded.iteration_count == sample_state.iteration_count
        assert loaded.session_id == sample_state.session_id
        assert loaded.total_cost_usd == sample_state.total_cost_usd
        assert loaded.total_tokens_used == sample_state.total_tokens_used
        assert loaded.started_at == sample_state.started_at
        assert loaded.last_activity_at == sample_state.last_activity_at
        assert loaded.session_cost_usd == sample_state.session_cost_usd
        assert loaded.session_tokens_used == sample_state.session_tokens_used
        assert loaded.tasks_completed_this_session == sample_state.tasks_completed_this_session

    def test_round_trip_preserves_circuit_breaker(
        self, temp_project: Path, sample_state: RalphState
    ) -> None:
        """Save then load preserves circuit breaker state."""
        temp_project.mkdir(parents=True)
        save_state(sample_state, temp_project)
        loaded = load_state(temp_project)

        cb = loaded.circuit_breaker
        orig = sample_state.circuit_breaker
        assert cb.max_consecutive_failures == orig.max_consecutive_failures
        assert cb.max_stagnation_iterations == orig.max_stagnation_iterations
        assert cb.max_cost_usd == orig.max_cost_usd
        assert cb.state == orig.state
        assert cb.failure_count == orig.failure_count
        assert cb.stagnation_count == orig.stagnation_count
        assert cb.last_failure_reason == orig.last_failure_reason

    def test_round_trip_preserves_context_budget(
        self, temp_project: Path, sample_state: RalphState
    ) -> None:
        """Save then load preserves context budget."""
        temp_project.mkdir(parents=True)
        save_state(sample_state, temp_project)
        loaded = load_state(temp_project)

        budget = loaded.context_budget
        orig = sample_state.context_budget
        assert budget.total_capacity == orig.total_capacity
        assert budget.system_prompt_allocation == orig.system_prompt_allocation
        assert budget.safety_margin == orig.safety_margin
        assert budget.current_usage == orig.current_usage
        assert budget.tool_results_tokens == orig.tool_results_tokens

    def test_load_missing_state_raises_error(self, temp_project: Path) -> None:
        """Load raises StateNotFoundError when file missing."""
        temp_project.mkdir(parents=True)
        with pytest.raises(StateNotFoundError):
            load_state(temp_project)

    def test_load_corrupted_json_raises_error(self, temp_project: Path) -> None:
        """Load raises CorruptedStateError for invalid JSON."""
        temp_project.mkdir(parents=True)
        ralph_dir = temp_project / ".ralph"
        ralph_dir.mkdir()
        (ralph_dir / "state.json").write_text("not valid json{{{")

        with pytest.raises(CorruptedStateError):
            load_state(temp_project)

    def test_load_invalid_data_raises_error(self, temp_project: Path) -> None:
        """Load raises CorruptedStateError for missing required fields."""
        temp_project.mkdir(parents=True)
        ralph_dir = temp_project / ".ralph"
        ralph_dir.mkdir()
        (ralph_dir / "state.json").write_text('{"some": "invalid"}')

        with pytest.raises(CorruptedStateError):
            load_state(temp_project)


class TestSessionIterationPersistence:
    """Tests for session iteration count persistence."""

    def test_session_iteration_count_serialized(self, temp_project: Path) -> None:
        """session_iteration_count is saved and loaded correctly."""
        temp_project.mkdir(parents=True)
        state = RalphState(project_root=temp_project)
        state.session_iteration_count = 5

        save_state(state, temp_project)
        loaded = load_state(temp_project)

        assert loaded.session_iteration_count == 5

    def test_missing_session_iteration_defaults_to_zero(self, temp_project: Path) -> None:
        """Missing session_iteration_count in old state files defaults to 0."""
        temp_project.mkdir(parents=True)
        ralph_dir = temp_project / ".ralph"
        ralph_dir.mkdir()

        # Write state without session_iteration_count (simulating old format)
        state_file = ralph_dir / "state.json"
        state_file.write_text('{"project_root": "' + str(temp_project) + '", "iteration_count": 5}')

        loaded = load_state(temp_project)
        assert loaded.session_iteration_count == 0
        assert loaded.iteration_count == 5

    def test_round_trip_preserves_session_iteration(self, temp_project: Path) -> None:
        """Save then load preserves session_iteration_count through multiple saves."""
        temp_project.mkdir(parents=True)
        state = RalphState(project_root=temp_project)

        # Simulate session with iterations
        state.start_iteration()
        state.start_iteration()
        state.start_iteration()

        save_state(state, temp_project)
        loaded = load_state(temp_project)

        assert loaded.iteration_count == 3
        assert loaded.session_iteration_count == 3


class TestSaveAndLoadPlan:
    """Tests for plan save/load operations."""

    def test_save_creates_plan_file(
        self, temp_project: Path, sample_plan: ImplementationPlan
    ) -> None:
        """Save creates implementation_plan.json file."""
        temp_project.mkdir(parents=True)
        path = save_plan(sample_plan, temp_project)
        assert path.exists()
        assert path.name == "implementation_plan.json"

    def test_round_trip_preserves_tasks(
        self, temp_project: Path, sample_plan: ImplementationPlan
    ) -> None:
        """Save then load preserves all task data."""
        temp_project.mkdir(parents=True)
        save_plan(sample_plan, temp_project)
        loaded = load_plan(temp_project)

        assert len(loaded.tasks) == len(sample_plan.tasks)
        for orig_task, loaded_task in zip(sample_plan.tasks, loaded.tasks, strict=True):
            assert loaded_task.id == orig_task.id
            assert loaded_task.description == orig_task.description
            assert loaded_task.priority == orig_task.priority
            assert loaded_task.status == orig_task.status
            assert loaded_task.dependencies == orig_task.dependencies
            assert loaded_task.verification_criteria == orig_task.verification_criteria
            assert loaded_task.estimated_tokens == orig_task.estimated_tokens
            assert loaded_task.actual_tokens_used == orig_task.actual_tokens_used
            assert loaded_task.completion_notes == orig_task.completion_notes
            assert loaded_task.completed_at == orig_task.completed_at
            assert loaded_task.retry_count == orig_task.retry_count
            assert loaded_task.spec_files == orig_task.spec_files

    def test_round_trip_preserves_timestamps(
        self, temp_project: Path, sample_plan: ImplementationPlan
    ) -> None:
        """Save then load preserves plan timestamps."""
        temp_project.mkdir(parents=True)
        save_plan(sample_plan, temp_project)
        loaded = load_plan(temp_project)

        assert loaded.created_at == sample_plan.created_at
        assert loaded.last_modified == sample_plan.last_modified

    def test_load_missing_plan_raises_error(self, temp_project: Path) -> None:
        """Load raises StateNotFoundError when file missing."""
        temp_project.mkdir(parents=True)
        with pytest.raises(StateNotFoundError):
            load_plan(temp_project)

    def test_load_corrupted_plan_raises_error(self, temp_project: Path) -> None:
        """Load raises CorruptedStateError for invalid JSON."""
        temp_project.mkdir(parents=True)
        ralph_dir = temp_project / ".ralph"
        ralph_dir.mkdir()
        (ralph_dir / "implementation_plan.json").write_text("broken{json")

        with pytest.raises(CorruptedStateError):
            load_plan(temp_project)

    def test_empty_plan_round_trip(self, temp_project: Path) -> None:
        """Empty plan can be saved and loaded."""
        temp_project.mkdir(parents=True)
        empty_plan = ImplementationPlan()
        save_plan(empty_plan, temp_project)
        loaded = load_plan(temp_project)

        assert loaded.tasks == []


class TestInitializeFunctions:
    """Tests for initialize_state and initialize_plan."""

    def test_initialize_state_creates_file(self, temp_project: Path) -> None:
        """Initialize state creates and saves new state."""
        temp_project.mkdir(parents=True)
        state = initialize_state(temp_project)

        assert state.project_root == temp_project
        assert state.iteration_count == 0
        assert state_exists(temp_project)

    def test_initialize_plan_creates_file(self, temp_project: Path) -> None:
        """Initialize plan creates and saves new plan."""
        temp_project.mkdir(parents=True)
        plan = initialize_plan(temp_project)

        assert plan.tasks == []
        assert plan_exists(temp_project)

    def test_initialize_state_defaults(self, temp_project: Path) -> None:
        """Initialize state uses correct defaults."""
        temp_project.mkdir(parents=True)
        state = initialize_state(temp_project)

        assert state.current_phase == Phase.BUILDING
        assert state.total_cost_usd == 0.0
        assert state.circuit_breaker.state == "closed"
        assert state.context_budget.current_usage == 0


class TestPhaseHandling:
    """Tests for Phase enum serialization."""

    def test_all_phases_round_trip(self, temp_project: Path) -> None:
        """All Phase values can be serialized and deserialized."""
        temp_project.mkdir(parents=True)

        for phase in Phase:
            state = RalphState(project_root=temp_project, current_phase=phase)
            save_state(state, temp_project)
            loaded = load_state(temp_project)
            assert loaded.current_phase == phase


class TestTaskStatusHandling:
    """Tests for TaskStatus enum serialization."""

    def test_all_task_statuses_round_trip(self, temp_project: Path) -> None:
        """All TaskStatus values can be serialized and deserialized."""
        temp_project.mkdir(parents=True)

        for status in TaskStatus:
            task = Task(id="test", description="Test", priority=1, status=status)
            plan = ImplementationPlan(tasks=[task])
            save_plan(plan, temp_project)
            loaded = load_plan(temp_project)
            assert loaded.tasks[0].status == status


class TestEdgeCases:
    """Tests for edge cases and special values."""

    def test_none_values_preserved(self, temp_project: Path) -> None:
        """None values are correctly preserved."""
        temp_project.mkdir(parents=True)
        state = RalphState(project_root=temp_project, session_id=None)
        save_state(state, temp_project)
        loaded = load_state(temp_project)
        assert loaded.session_id is None

    def test_empty_lists_preserved(self, temp_project: Path) -> None:
        """Empty lists are correctly preserved."""
        temp_project.mkdir(parents=True)
        task = Task(
            id="test",
            description="Test",
            priority=1,
            dependencies=[],
            verification_criteria=[],
        )
        plan = ImplementationPlan(tasks=[task])
        save_plan(plan, temp_project)
        loaded = load_plan(temp_project)
        assert loaded.tasks[0].dependencies == []
        assert loaded.tasks[0].verification_criteria == []

    def test_save_uses_state_project_root_by_default(
        self, temp_project: Path, sample_state: RalphState
    ) -> None:
        """Save uses state.project_root when no override given."""
        temp_project.mkdir(parents=True)
        save_state(sample_state)  # No project_root override
        assert state_exists(temp_project)


class TestCompletionSignalsPersistence:
    """Tests for completion signals persistence."""

    def test_completion_signals_round_trip(self, temp_project: Path) -> None:
        """completion_signals are preserved through save/load cycle."""
        temp_project.mkdir(parents=True)
        state = RalphState(project_root=temp_project)
        state.completion_signals["discovery"] = {
            "complete": True,
            "summary": "Discovery complete with 3 specs",
            "timestamp": "2026-01-27T12:00:00",
            "artifacts": {"specs_created": ["spec1.md", "spec2.md"]},
        }
        state.completion_signals["planning"] = {
            "complete": True,
            "summary": "Created 10 tasks",
            "timestamp": "2026-01-27T12:30:00",
            "artifacts": {"task_count": 10},
        }

        save_state(state, temp_project)
        loaded = load_state(temp_project)

        assert loaded.is_phase_complete("discovery")
        assert loaded.is_phase_complete("planning")
        assert not loaded.is_phase_complete("building")
        assert loaded.completion_signals["discovery"]["summary"] == "Discovery complete with 3 specs"
        assert loaded.completion_signals["planning"]["artifacts"]["task_count"] == 10

    def test_missing_completion_signals_defaults_to_empty(self, temp_project: Path) -> None:
        """Missing completion_signals in old state files defaults to empty dict."""
        temp_project.mkdir(parents=True)
        ralph_dir = temp_project / ".ralph"
        ralph_dir.mkdir()

        # Write state without completion_signals (simulating old format)
        state_file = ralph_dir / "state.json"
        state_file.write_text('{"project_root": "' + str(temp_project) + '"}')

        loaded = load_state(temp_project)
        assert loaded.completion_signals == {}
        assert not loaded.is_phase_complete("discovery")

    def test_empty_completion_signals_preserved(self, temp_project: Path) -> None:
        """Empty completion_signals dict is preserved correctly."""
        temp_project.mkdir(parents=True)
        state = RalphState(project_root=temp_project)
        # completion_signals starts empty by default

        save_state(state, temp_project)
        loaded = load_state(temp_project)

        assert loaded.completion_signals == {}

    def test_completion_signal_cleared_after_reload(self, temp_project: Path) -> None:
        """Completion signal can be set, saved, reloaded, cleared, and saved again."""
        temp_project.mkdir(parents=True)
        state = RalphState(project_root=temp_project)

        # Set signal
        state.completion_signals["discovery"] = {"complete": True, "summary": "Done"}
        save_state(state, temp_project)

        # Reload and verify
        loaded = load_state(temp_project)
        assert loaded.is_phase_complete("discovery")

        # Clear signal
        loaded.clear_phase_completion("discovery")
        save_state(loaded, temp_project)

        # Reload and verify cleared
        reloaded = load_state(temp_project)
        assert not reloaded.is_phase_complete("discovery")
        assert "discovery" not in reloaded.completion_signals
