"""Tests for the loop runner."""

from pathlib import Path

import pytest

from ralph.config import load_config
from ralph.models import ImplementationPlan, Phase, Task, TaskStatus
from ralph.persistence import initialize_plan, initialize_state, save_plan, save_state
from ralph.runner import (
    LoopResult,
    LoopRunner,
    LoopStatus,
    RecoveryAction,
    RecoveryStrategy,
    RunnerIterationResult,
    apply_recovery_action,
    determine_recovery_action,
)


@pytest.fixture
def project_path(tmp_path: Path) -> Path:
    """Create an initialized project directory."""
    initialize_state(tmp_path)
    initialize_plan(tmp_path)
    return tmp_path


@pytest.fixture
def plan_with_tasks(project_path: Path) -> ImplementationPlan:
    """Create a plan with tasks."""
    plan = ImplementationPlan(
        tasks=[
            Task(
                id="task-1",
                description="First task",
                priority=1,
                status=TaskStatus.PENDING,
            ),
            Task(
                id="task-2",
                description="Second task",
                priority=2,
                status=TaskStatus.PENDING,
                dependencies=["task-1"],
            ),
        ]
    )
    save_plan(plan, project_path)
    return plan


class TestLoopStatus:
    """Tests for LoopStatus enum."""

    def test_all_statuses_defined(self) -> None:
        """All expected statuses are defined."""
        assert LoopStatus.RUNNING == "running"
        assert LoopStatus.PAUSED == "paused"
        assert LoopStatus.COMPLETED == "completed"
        assert LoopStatus.FAILED == "failed"
        assert LoopStatus.HALTED == "halted"


class TestRecoveryAction:
    """Tests for RecoveryAction enum."""

    def test_all_actions_defined(self) -> None:
        """All expected actions are defined."""
        assert RecoveryAction.RETRY == "retry"
        assert RecoveryAction.SKIP_TASK == "skip_task"
        assert RecoveryAction.MANUAL_INTERVENTION == "manual_intervention"
        assert RecoveryAction.RESET_CIRCUIT_BREAKER == "reset_circuit_breaker"
        assert RecoveryAction.HANDOFF == "handoff"


class TestRecoveryStrategy:
    """Tests for RecoveryStrategy."""

    def test_initial_state(self) -> None:
        """Initial state allows retries."""
        strategy = RecoveryStrategy(action=RecoveryAction.RETRY, max_retries=3)
        assert strategy.should_retry() is True
        assert strategy.current_retry == 0

    def test_increment_retry(self) -> None:
        """Retry counter increments."""
        strategy = RecoveryStrategy(action=RecoveryAction.RETRY, max_retries=3)
        strategy.increment_retry()
        assert strategy.current_retry == 1

    def test_should_retry_false_after_max(self) -> None:
        """Should not retry after max retries."""
        strategy = RecoveryStrategy(action=RecoveryAction.RETRY, max_retries=2)
        strategy.increment_retry()
        strategy.increment_retry()
        assert strategy.should_retry() is False


class TestRunnerIterationResult:
    """Tests for RunnerIterationResult."""

    def test_default_values(self) -> None:
        """Has correct default values."""
        result = RunnerIterationResult(
            iteration=1,
            phase=Phase.BUILDING,
            success=True,
            cost_usd=0.05,
            tokens_used=5000,
        )
        assert result.task_completed is False
        assert result.task_id is None
        assert result.error is None


class TestLoopResult:
    """Tests for LoopResult."""

    def test_default_values(self) -> None:
        """Has correct default values."""
        result = LoopResult(
            status=LoopStatus.COMPLETED,
            iterations_completed=10,
            tasks_completed=5,
            total_cost_usd=1.5,
            total_tokens_used=50000,
            final_phase=Phase.VALIDATION,
        )
        assert result.error is None
        assert result.halt_reason is None
        assert result.session_count == 1


class TestLoopRunner:
    """Tests for LoopRunner."""

    def test_creation(self, project_path: Path) -> None:
        """Creates runner successfully."""
        runner = LoopRunner(project_path)
        assert runner.project_root == project_path
        assert runner.status == LoopStatus.RUNNING

    def test_current_phase(self, project_path: Path) -> None:
        """Returns current phase."""
        runner = LoopRunner(project_path)
        assert runner.current_phase == Phase.BUILDING

    def test_get_system_prompt(self, project_path: Path) -> None:
        """Gets system prompt for current phase."""
        runner = LoopRunner(project_path)
        prompt = runner.get_system_prompt()
        assert "Building Phase" in prompt

    def test_start_session(self, project_path: Path) -> None:
        """Starts new session."""
        runner = LoopRunner(project_path)
        session_id = runner.start_session()
        assert session_id is not None
        assert len(session_id) == 8

    def test_should_continue_initially(self, project_path: Path) -> None:
        """Should continue initially."""
        runner = LoopRunner(project_path)
        should_continue, reason = runner.should_continue()
        assert should_continue is True
        assert reason is None

    def test_should_continue_when_paused(self, project_path: Path) -> None:
        """Should not continue when paused."""
        state = initialize_state(project_path)
        state.paused = True
        save_state(state, project_path)

        runner = LoopRunner(project_path)
        should_continue, reason = runner.should_continue()
        assert should_continue is False
        assert reason == "paused"

    def test_should_continue_circuit_breaker(self, project_path: Path) -> None:
        """Should not continue when circuit breaker open."""
        state = initialize_state(project_path)
        for _ in range(3):
            state.circuit_breaker.record_failure("test")
        save_state(state, project_path)

        runner = LoopRunner(project_path)
        should_continue, reason = runner.should_continue()
        assert should_continue is False
        assert "consecutive_failures" in reason

    def test_pre_iteration(self, project_path: Path) -> None:
        """Pre-iteration returns context."""
        runner = LoopRunner(project_path)
        context = runner.pre_iteration()

        assert "iteration" in context
        assert "phase" in context
        assert "system_prompt" in context

    def test_post_iteration_success(
        self, project_path: Path, plan_with_tasks: ImplementationPlan
    ) -> None:
        """Post-iteration processes success."""
        runner = LoopRunner(project_path)
        runner.pre_iteration()

        result = runner.post_iteration(
            cost_usd=0.05,
            tokens_used=5000,
            task_completed=True,
            task_id="task-1",
        )

        assert result.success is True
        assert result.tasks_completed == 1

    def test_post_iteration_failure(self, project_path: Path) -> None:
        """Post-iteration processes failure."""
        runner = LoopRunner(project_path)
        runner.pre_iteration()

        result = runner.post_iteration(
            cost_usd=0.05,
            tokens_used=5000,
            task_completed=False,
            error="test error",
        )

        # Note: success is determined by circuit breaker, not error
        assert result.tasks_completed == 0

    def test_callbacks_fired(self, project_path: Path) -> None:
        """Callbacks are fired appropriately."""
        start_called = []
        end_called = []

        runner = LoopRunner(
            project_path,
            on_iteration_start=lambda ctx: start_called.append(ctx),
            on_iteration_end=lambda res: end_called.append(res),
        )

        runner.pre_iteration()
        runner.post_iteration(cost_usd=0.05, tokens_used=5000, task_completed=False)

        assert len(start_called) == 1
        assert len(end_called) == 1

    def test_run_single_iteration(
        self, project_path: Path, plan_with_tasks: ImplementationPlan
    ) -> None:
        """Runs a single iteration."""
        runner = LoopRunner(project_path)
        runner.start_session()

        def execute_fn(ctx):
            return 0.05, 5000, True, "task-1", None

        result = runner.run_iteration(execute_fn)

        assert result.success is True
        assert result.cost_usd == 0.05
        assert result.task_completed is True

    def test_run_multiple_iterations(
        self, project_path: Path, plan_with_tasks: ImplementationPlan
    ) -> None:
        """Runs multiple iterations."""
        runner = LoopRunner(project_path)
        iteration_count = 0

        def execute_fn(ctx):
            nonlocal iteration_count
            iteration_count += 1
            # Complete all tasks
            return 0.05, 5000, True, f"task-{iteration_count}", None

        result = runner.run(execute_fn, max_iterations=5)

        assert iteration_count > 0
        assert result.iterations_completed > 0

    def test_run_stops_on_pause(self, project_path: Path) -> None:
        """Run stops when paused."""
        runner = LoopRunner(project_path)

        def execute_fn(ctx):
            # Pause after first iteration
            runner.state.paused = True
            save_state(runner.state, project_path)
            return 0.05, 5000, False, None, None

        result = runner.run(execute_fn, max_iterations=10)

        assert result.status == LoopStatus.PAUSED
        assert result.iterations_completed == 1


class TestDetermineRecoveryAction:
    """Tests for determine_recovery_action."""

    def test_retry_on_first_failure(self, project_path: Path) -> None:
        """Suggests retry on first failure."""
        state = initialize_state(project_path)
        config = load_config(project_path)

        action = determine_recovery_action(state, "test error", config)
        assert action == RecoveryAction.RETRY

    def test_skip_after_many_failures(self, project_path: Path) -> None:
        """Suggests skip after many failures."""
        state = initialize_state(project_path)
        config = load_config(project_path)

        for _ in range(3):
            state.circuit_breaker.record_failure("test")

        action = determine_recovery_action(state, "test error", config)
        assert action == RecoveryAction.SKIP_TASK

    def test_handoff_on_stagnation(self, project_path: Path) -> None:
        """Suggests handoff on stagnation."""
        state = initialize_state(project_path)
        config = load_config(project_path)

        for _ in range(5):
            state.circuit_breaker.record_success(tasks_completed=0)

        action = determine_recovery_action(state, "no progress", config)
        assert action == RecoveryAction.HANDOFF

    def test_manual_on_cost_exceeded(self, project_path: Path) -> None:
        """Suggests manual intervention on cost exceeded."""
        state = initialize_state(project_path)
        config = load_config(project_path)

        # Cost is now tracked in RalphState, not CircuitBreaker
        state.total_cost_usd = 200.0  # Exceeds default max

        action = determine_recovery_action(state, "expensive", config)
        assert action == RecoveryAction.MANUAL_INTERVENTION


class TestApplyRecoveryAction:
    """Tests for apply_recovery_action."""

    def test_retry_returns_true(self, project_path: Path) -> None:
        """Retry action always succeeds."""
        state = initialize_state(project_path)
        result = apply_recovery_action(RecoveryAction.RETRY, project_path, state)
        assert result is True

    def test_skip_task_blocks_task(
        self, project_path: Path, plan_with_tasks: ImplementationPlan
    ) -> None:
        """Skip task action blocks the current task."""
        state = initialize_state(project_path)
        result = apply_recovery_action(RecoveryAction.SKIP_TASK, project_path, state)
        assert result is True

        from ralph.persistence import load_plan
        plan = load_plan(project_path)
        blocked_tasks = [t for t in plan.tasks if t.status == TaskStatus.BLOCKED]
        assert len(blocked_tasks) == 1

    def test_reset_circuit_breaker(self, project_path: Path) -> None:
        """Reset circuit breaker action resets state."""
        state = initialize_state(project_path)
        state.circuit_breaker.failure_count = 5
        save_state(state, project_path)

        result = apply_recovery_action(
            RecoveryAction.RESET_CIRCUIT_BREAKER, project_path, state
        )
        assert result is True
        assert state.circuit_breaker.failure_count == 0

    def test_manual_intervention_returns_false(self, project_path: Path) -> None:
        """Manual intervention returns false."""
        state = initialize_state(project_path)
        result = apply_recovery_action(
            RecoveryAction.MANUAL_INTERVENTION, project_path, state
        )
        assert result is False
