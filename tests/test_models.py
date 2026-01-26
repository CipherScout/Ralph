"""Tests for Ralph core data models."""

from pathlib import Path

from ralph.models import (
    CircuitBreakerState,
    ContextBudget,
    ImplementationPlan,
    Phase,
    RalphState,
    Task,
    TaskStatus,
)


class TestTask:
    """Tests for Task model."""

    def test_task_defaults(self) -> None:
        """Test task has sensible defaults."""
        task = Task(id="task-001", description="Test task", priority=1)
        assert task.status == TaskStatus.PENDING
        assert task.dependencies == []
        assert task.verification_criteria == []
        assert task.estimated_tokens == 30_000
        assert task.retry_count == 0

    def test_task_is_available_no_dependencies(self) -> None:
        """Task without dependencies is available when pending."""
        task = Task(id="task-001", description="Test", priority=1)
        assert task.is_available(set()) is True

    def test_task_is_available_with_met_dependencies(self) -> None:
        """Task is available when all dependencies are completed."""
        task = Task(
            id="task-002",
            description="Dependent task",
            priority=1,
            dependencies=["task-001"],
        )
        assert task.is_available({"task-001"}) is True

    def test_task_is_not_available_with_unmet_dependencies(self) -> None:
        """Task is unavailable when dependencies are not met."""
        task = Task(
            id="task-002",
            description="Dependent task",
            priority=1,
            dependencies=["task-001"],
        )
        assert task.is_available(set()) is False

    def test_task_is_not_available_when_not_pending(self) -> None:
        """Task is unavailable when already in progress or complete."""
        task = Task(
            id="task-001",
            description="Test",
            priority=1,
            status=TaskStatus.IN_PROGRESS,
        )
        assert task.is_available(set()) is False


class TestImplementationPlan:
    """Tests for ImplementationPlan model."""

    def test_empty_plan_returns_none(self) -> None:
        """Empty plan has no next task."""
        plan = ImplementationPlan()
        assert plan.get_next_task() is None

    def test_selects_highest_priority(self) -> None:
        """Plan selects task with lowest priority number (highest priority)."""
        plan = ImplementationPlan(
            tasks=[
                Task(id="a", description="Low priority", priority=3),
                Task(id="b", description="High priority", priority=1),
                Task(id="c", description="Medium priority", priority=2),
            ]
        )
        next_task = plan.get_next_task()
        assert next_task is not None
        assert next_task.id == "b"

    def test_respects_dependencies(self) -> None:
        """Plan respects task dependencies even with higher priority."""
        plan = ImplementationPlan(
            tasks=[
                Task(id="a", description="Depends on b", priority=1, dependencies=["b"]),
                Task(id="b", description="No deps", priority=2),
            ]
        )
        next_task = plan.get_next_task()
        assert next_task is not None
        assert next_task.id == "b"

    def test_skips_completed_tasks(self) -> None:
        """Plan skips tasks that are already complete."""
        plan = ImplementationPlan(
            tasks=[
                Task(id="a", description="Done", priority=1, status=TaskStatus.COMPLETE),
                Task(id="b", description="Pending", priority=2),
            ]
        )
        next_task = plan.get_next_task()
        assert next_task is not None
        assert next_task.id == "b"

    def test_skips_blocked_tasks(self) -> None:
        """Plan skips tasks that are blocked."""
        plan = ImplementationPlan(
            tasks=[
                Task(id="a", description="Blocked", priority=1, status=TaskStatus.BLOCKED),
                Task(id="b", description="Pending", priority=2),
            ]
        )
        next_task = plan.get_next_task()
        assert next_task is not None
        assert next_task.id == "b"

    def test_mark_task_complete(self) -> None:
        """Marking task complete updates status and metadata."""
        plan = ImplementationPlan(
            tasks=[Task(id="a", description="Test", priority=1)]
        )
        result = plan.mark_task_complete("a", notes="All tests pass", tokens_used=25000)
        assert result is True
        task = plan.get_task_by_id("a")
        assert task is not None
        assert task.status == TaskStatus.COMPLETE
        assert task.completion_notes == "All tests pass"
        assert task.actual_tokens_used == 25000
        assert task.completed_at is not None

    def test_mark_task_complete_nonexistent(self) -> None:
        """Marking nonexistent task returns False."""
        plan = ImplementationPlan()
        result = plan.mark_task_complete("nonexistent")
        assert result is False

    def test_mark_task_blocked(self) -> None:
        """Marking task blocked updates status with reason."""
        plan = ImplementationPlan(
            tasks=[Task(id="a", description="Test", priority=1)]
        )
        result = plan.mark_task_blocked("a", "Missing API key")
        assert result is True
        task = plan.get_task_by_id("a")
        assert task is not None
        assert task.status == TaskStatus.BLOCKED
        assert "Missing API key" in str(task.completion_notes)

    def test_completion_percentage(self) -> None:
        """Completion percentage calculated correctly."""
        plan = ImplementationPlan(
            tasks=[
                Task(id="a", description="Done", priority=1, status=TaskStatus.COMPLETE),
                Task(id="b", description="Pending", priority=2),
                Task(id="c", description="Pending", priority=3),
                Task(id="d", description="Done", priority=4, status=TaskStatus.COMPLETE),
            ]
        )
        assert plan.completion_percentage == 0.5

    def test_completion_percentage_empty(self) -> None:
        """Empty plan has 0% completion."""
        plan = ImplementationPlan()
        assert plan.completion_percentage == 0.0

    def test_pending_and_complete_counts(self) -> None:
        """Count properties work correctly."""
        plan = ImplementationPlan(
            tasks=[
                Task(id="a", description="Done", priority=1, status=TaskStatus.COMPLETE),
                Task(id="b", description="Pending", priority=2),
                Task(id="c", description="Blocked", priority=3, status=TaskStatus.BLOCKED),
            ]
        )
        assert plan.pending_count == 1
        assert plan.complete_count == 1

    def test_dependency_chain(self) -> None:
        """Tasks with dependency chains are selected in correct order."""
        plan = ImplementationPlan(
            tasks=[
                Task(id="c", description="Last", priority=1, dependencies=["b"]),
                Task(id="b", description="Middle", priority=1, dependencies=["a"]),
                Task(id="a", description="First", priority=1),
            ]
        )
        # First, only 'a' is available
        assert plan.get_next_task().id == "a"

        # After completing 'a', 'b' becomes available
        plan.mark_task_complete("a")
        assert plan.get_next_task().id == "b"

        # After completing 'b', 'c' becomes available
        plan.mark_task_complete("b")
        assert plan.get_next_task().id == "c"


class TestCircuitBreakerState:
    """Tests for CircuitBreakerState model."""

    def test_initial_state(self) -> None:
        """Circuit breaker starts closed with no failures."""
        cb = CircuitBreakerState()
        assert cb.state == "closed"
        assert cb.failure_count == 0
        assert cb.stagnation_count == 0
        halt, reason = cb.should_halt()
        assert halt is False

    def test_success_resets_failure_count(self) -> None:
        """Successful iteration resets failure count."""
        cb = CircuitBreakerState()
        cb.failure_count = 2
        cb.record_success(tasks_completed=1)
        assert cb.failure_count == 0
        assert cb.stagnation_count == 0

    def test_success_without_task_completion_increments_stagnation(self) -> None:
        """Success without completing tasks increments stagnation."""
        cb = CircuitBreakerState()
        cb.record_success(tasks_completed=0)
        assert cb.stagnation_count == 1
        assert cb.failure_count == 0

    def test_failure_increments_counts(self) -> None:
        """Failure increments both failure and stagnation counts."""
        cb = CircuitBreakerState()
        cb.record_failure("Test error")
        assert cb.failure_count == 1
        assert cb.stagnation_count == 1
        assert cb.last_failure_reason == "Test error"

    def test_halt_on_consecutive_failures(self) -> None:
        """Circuit breaker halts after max consecutive failures."""
        cb = CircuitBreakerState(max_consecutive_failures=3)
        cb.record_failure("Error 1")
        cb.record_failure("Error 2")
        cb.record_failure("Error 3")
        halt, reason = cb.should_halt()
        assert halt is True
        assert "consecutive_failures:3" in reason
        assert cb.state == "open"

    def test_halt_on_stagnation(self) -> None:
        """Circuit breaker halts after max stagnation iterations."""
        cb = CircuitBreakerState(max_stagnation_iterations=3)
        cb.record_success(tasks_completed=0)
        cb.record_success(tasks_completed=0)
        cb.record_success(tasks_completed=0)
        halt, reason = cb.should_halt()
        assert halt is True
        assert "stagnation:3" in reason

    def test_halt_on_cost_limit(self) -> None:
        """Circuit breaker halts when cost limit exceeded (cost passed in)."""
        cb = CircuitBreakerState(max_cost_usd=10.0)
        # Cost is now tracked externally in RalphState, passed to should_halt
        halt, reason = cb.should_halt(current_cost_usd=11.0)
        assert halt is True
        assert "cost_limit" in reason

    def test_reset_clears_failure_state(self) -> None:
        """Reset clears failure state."""
        cb = CircuitBreakerState()
        cb.record_failure("Error")
        cb.reset()
        assert cb.failure_count == 0
        assert cb.stagnation_count == 0
        assert cb.state == "closed"

    def test_half_open_closes_on_success(self) -> None:
        """Half-open circuit closes on successful iteration."""
        cb = CircuitBreakerState()
        cb.state = "half_open"
        cb.record_success(tasks_completed=1)
        assert cb.state == "closed"


class TestContextBudget:
    """Tests for ContextBudget model."""

    def test_effective_capacity(self) -> None:
        """Effective capacity accounts for safety margin."""
        budget = ContextBudget(total_capacity=200_000, safety_margin=0.20)
        assert budget.effective_capacity == 160_000

    def test_smart_zone_max(self) -> None:
        """Smart zone max is 60% of total capacity."""
        budget = ContextBudget(total_capacity=200_000)
        assert budget.smart_zone_max == 120_000

    def test_should_handoff(self) -> None:
        """Handoff triggers when usage exceeds smart zone."""
        budget = ContextBudget(total_capacity=200_000)
        assert budget.should_handoff() is False
        budget.current_usage = 120_001
        assert budget.should_handoff() is True

    def test_available_tokens(self) -> None:
        """Available tokens calculated correctly."""
        budget = ContextBudget(total_capacity=200_000)
        assert budget.available_tokens == 160_000
        budget.add_usage(50_000)
        assert budget.available_tokens == 110_000

    def test_reset(self) -> None:
        """Reset clears usage tracking."""
        budget = ContextBudget()
        budget.add_usage(100_000)
        budget.tool_results_tokens = 5_000
        budget.reset()
        assert budget.current_usage == 0
        assert budget.tool_results_tokens == 0


class TestRalphState:
    """Tests for RalphState model."""

    def test_initial_state(self) -> None:
        """RalphState initializes with sensible defaults."""
        state = RalphState(project_root=Path("/test"))
        assert state.current_phase == Phase.BUILDING
        assert state.iteration_count == 0
        assert state.total_cost_usd == 0.0

    def test_start_iteration(self) -> None:
        """Starting iteration increments count."""
        state = RalphState(project_root=Path("/test"))
        state.start_iteration()
        assert state.iteration_count == 1
        state.start_iteration()
        assert state.iteration_count == 2

    def test_end_iteration_accumulates_costs(self) -> None:
        """Ending iteration accumulates costs and tokens."""
        state = RalphState(project_root=Path("/test"))
        state.end_iteration(cost_usd=1.5, tokens_used=30_000, task_completed=True)
        assert state.total_cost_usd == 1.5
        assert state.total_tokens_used == 30_000
        assert state.tasks_completed_this_session == 1

    def test_start_new_session(self) -> None:
        """New session resets session-specific tracking."""
        state = RalphState(project_root=Path("/test"))
        state.end_iteration(cost_usd=1.0, tokens_used=10_000, task_completed=True)
        state.start_new_session("session-002")
        assert state.session_id == "session-002"
        assert state.session_cost_usd == 0.0
        assert state.session_tokens_used == 0
        assert state.tasks_completed_this_session == 0
        # Total costs preserved
        assert state.total_cost_usd == 1.0
        assert state.total_tokens_used == 10_000

    def test_advance_phase(self) -> None:
        """Advancing phase updates phase and resets context."""
        state = RalphState(project_root=Path("/test"))
        state.context_budget.add_usage(50_000)
        state.advance_phase(Phase.VALIDATION)
        assert state.current_phase == Phase.VALIDATION
        assert state.context_budget.current_usage == 0

    def test_needs_handoff(self) -> None:
        """Needs handoff delegates to context budget."""
        state = RalphState(project_root=Path("/test"))
        assert state.needs_handoff() is False
        state.context_budget.current_usage = 200_000
        assert state.needs_handoff() is True

    def test_should_halt(self) -> None:
        """Should halt delegates to circuit breaker."""
        state = RalphState(project_root=Path("/test"))
        halt, reason = state.should_halt()
        assert halt is False
        # Trigger circuit breaker
        for _ in range(3):
            state.circuit_breaker.record_failure("Error")
        halt, reason = state.should_halt()
        assert halt is True


class TestPhaseEnum:
    """Tests for Phase enum."""

    def test_phase_values(self) -> None:
        """Phase enum has expected values."""
        assert Phase.DISCOVERY.value == "discovery"
        assert Phase.PLANNING.value == "planning"
        assert Phase.BUILDING.value == "building"
        assert Phase.VALIDATION.value == "validation"


class TestTaskStatusEnum:
    """Tests for TaskStatus enum."""

    def test_status_values(self) -> None:
        """TaskStatus enum has expected values."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.IN_PROGRESS.value == "in_progress"
        assert TaskStatus.COMPLETE.value == "complete"
        assert TaskStatus.BLOCKED.value == "blocked"
