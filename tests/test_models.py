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

    def test_task_spec_files_default(self) -> None:
        """Task spec_files defaults to empty list."""
        task = Task(id="task-001", description="Test", priority=1)
        assert task.spec_files == []

    def test_task_spec_files_set(self) -> None:
        """Task spec_files can be set."""
        task = Task(
            id="task-001",
            description="Test",
            priority=1,
            spec_files=["specs/SPEC-001-auth.md", "specs/PRD.md"],
        )
        assert task.spec_files == ["specs/SPEC-001-auth.md", "specs/PRD.md"]


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


class TestCircuitBreakerProgressMade:
    """Tests for progress_made parameter in circuit breaker."""

    def test_progress_made_resets_stagnation(self) -> None:
        """progress_made=True resets stagnation count."""
        cb = CircuitBreakerState()
        cb.stagnation_count = 3
        cb.record_success(tasks_completed=0, progress_made=True)
        assert cb.stagnation_count == 0

    def test_no_progress_increments_stagnation(self) -> None:
        """No progress increments stagnation count."""
        cb = CircuitBreakerState()
        cb.record_success(tasks_completed=0, progress_made=False)
        assert cb.stagnation_count == 1

    def test_tasks_completed_takes_precedence(self) -> None:
        """tasks_completed > 0 resets stagnation regardless of progress_made."""
        cb = CircuitBreakerState()
        cb.stagnation_count = 3
        cb.record_success(tasks_completed=1, progress_made=False)
        assert cb.stagnation_count == 0

    def test_progress_made_without_tasks_resets_stagnation(self) -> None:
        """progress_made resets stagnation even without completing tasks."""
        cb = CircuitBreakerState()
        # Simulate 4 iterations without progress
        for _ in range(4):
            cb.record_success(tasks_completed=0, progress_made=False)
        assert cb.stagnation_count == 4
        # Now make progress (e.g., tasks created in planning phase)
        cb.record_success(tasks_completed=0, progress_made=True)
        assert cb.stagnation_count == 0


class TestContextBudget:
    """Tests for ContextBudget model."""

    def test_effective_capacity(self) -> None:
        """Effective capacity accounts for safety margin (85% with 15% margin)."""
        budget = ContextBudget(total_capacity=200_000, safety_margin=0.15)
        assert budget.effective_capacity == 170_000  # 85% of 200k

    def test_effective_capacity_with_custom_margin(self) -> None:
        """Effective capacity works with custom safety margin."""
        budget = ContextBudget(total_capacity=200_000, safety_margin=0.20)
        assert budget.effective_capacity == 160_000  # 80% of 200k

    def test_smart_zone_max_at_80_percent(self) -> None:
        """Smart zone max (handoff threshold) is 80% of total capacity (SPEC-005)."""
        budget = ContextBudget(total_capacity=200_000)
        assert budget.smart_zone_max == 160_000  # 80% of 200k

    def test_warning_zone_at_70_percent(self) -> None:
        """Warning zone is 70% of total capacity (SPEC-005)."""
        budget = ContextBudget(total_capacity=200_000)
        assert budget.warning_zone == 140_000  # 70% of 200k

    def test_emergency_zone_at_90_percent(self) -> None:
        """Emergency zone is 90% of total capacity (SPEC-005)."""
        budget = ContextBudget(total_capacity=200_000)
        assert budget.emergency_zone == 180_000  # 90% of 200k

    def test_should_handoff_at_80_percent(self) -> None:
        """Handoff triggers at 80%, not 60% (SPEC-005)."""
        budget = ContextBudget(total_capacity=200_000)
        # At 60% - should NOT handoff (old behavior would handoff here)
        budget.current_usage = 120_000
        assert budget.should_handoff() is False
        # At 79% - still not handoff
        budget.current_usage = 158_000
        assert budget.should_handoff() is False
        # At 80% - should handoff
        budget.current_usage = 160_000
        assert budget.should_handoff() is True

    def test_should_warn_at_70_percent(self) -> None:
        """Warning should trigger at 70% but not above 80% (SPEC-005)."""
        budget = ContextBudget(total_capacity=200_000)
        # Below 70% - no warning
        budget.current_usage = 130_000
        assert budget.should_warn() is False
        # At 70% - warning
        budget.current_usage = 140_000
        assert budget.should_warn() is True
        # Between 70-80% - warning
        budget.current_usage = 155_000
        assert budget.should_warn() is True
        # At 80%+ - no warning (handoff takes over)
        budget.current_usage = 160_000
        assert budget.should_warn() is False

    def test_should_emergency_exit_at_90_percent(self) -> None:
        """Emergency exit triggers at 90% (SPEC-005)."""
        budget = ContextBudget(total_capacity=200_000)
        # Below 90% - no emergency
        budget.current_usage = 175_000
        assert budget.should_emergency_exit() is False
        # At 90% - emergency
        budget.current_usage = 180_000
        assert budget.should_emergency_exit() is True

    def test_configurable_thresholds(self) -> None:
        """Thresholds can be configured (SPEC-005)."""
        budget = ContextBudget(
            total_capacity=200_000,
            handoff_threshold=0.85,
            warning_threshold=0.75,
            emergency_threshold=0.95,
        )
        assert budget.smart_zone_max == 170_000  # 85%
        assert budget.warning_zone == 150_000  # 75%
        assert budget.emergency_zone == 190_000  # 95%

    def test_default_thresholds(self) -> None:
        """Default thresholds match SPEC-005 requirements."""
        budget = ContextBudget()
        assert budget.handoff_threshold == 0.80
        assert budget.warning_threshold == 0.70
        assert budget.emergency_threshold == 0.90
        assert budget.safety_margin == 0.15

    def test_available_tokens(self) -> None:
        """Available tokens calculated correctly."""
        budget = ContextBudget(total_capacity=200_000)
        assert budget.available_tokens == 170_000  # 85% effective capacity
        budget.add_usage(50_000)
        assert budget.available_tokens == 120_000

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
        """Needs handoff delegates to context budget (80% threshold per SPEC-005)."""
        state = RalphState(project_root=Path("/test"))
        assert state.needs_handoff() is False
        # At 80% (160k of 200k) - should handoff
        state.context_budget.current_usage = 160_000
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


class TestRalphStateEndIterationProgress:
    """Tests for end_iteration with progress_made."""

    def test_end_iteration_with_progress(self) -> None:
        """end_iteration passes progress_made to circuit breaker."""
        state = RalphState(project_root=Path("/test"))
        state.end_iteration(cost_usd=0.01, tokens_used=100, task_completed=False, progress_made=True)
        assert state.circuit_breaker.stagnation_count == 0

    def test_end_iteration_without_progress(self) -> None:
        """end_iteration without progress increments stagnation."""
        state = RalphState(project_root=Path("/test"))
        state.end_iteration(cost_usd=0.01, tokens_used=100, task_completed=False, progress_made=False)
        assert state.circuit_breaker.stagnation_count == 1

    def test_end_iteration_task_completed_resets_stagnation(self) -> None:
        """end_iteration with task_completed=True resets stagnation."""
        state = RalphState(project_root=Path("/test"))
        # Create stagnation first
        state.circuit_breaker.stagnation_count = 3
        state.end_iteration(cost_usd=0.01, tokens_used=100, task_completed=True, progress_made=False)
        assert state.circuit_breaker.stagnation_count == 0

    def test_end_iteration_progress_prevents_halt(self) -> None:
        """progress_made prevents stagnation halt."""
        state = RalphState(project_root=Path("/test"))
        state.circuit_breaker.max_stagnation_iterations = 3
        # Do iterations with progress - should not halt
        state.end_iteration(cost_usd=0.01, tokens_used=100, task_completed=False, progress_made=True)
        state.end_iteration(cost_usd=0.01, tokens_used=100, task_completed=False, progress_made=True)
        state.end_iteration(cost_usd=0.01, tokens_used=100, task_completed=False, progress_made=True)
        halt, reason = state.should_halt()
        assert halt is False


class TestSessionIterationTracking:
    """Tests for session iteration tracking."""

    def test_start_iteration_increments_both(self) -> None:
        """start_iteration increments both global and session counters."""
        state = RalphState(project_root=Path("/test"))
        assert state.iteration_count == 0
        assert state.session_iteration_count == 0

        state.start_iteration()
        assert state.iteration_count == 1
        assert state.session_iteration_count == 1

        state.start_iteration()
        assert state.iteration_count == 2
        assert state.session_iteration_count == 2

    def test_start_new_session_resets_session_counter(self) -> None:
        """start_new_session resets session counter but preserves global."""
        state = RalphState(project_root=Path("/test"))
        state.start_iteration()
        state.start_iteration()
        assert state.iteration_count == 2
        assert state.session_iteration_count == 2

        state.start_new_session("session-2")
        assert state.iteration_count == 2  # Global preserved
        assert state.session_iteration_count == 0  # Session reset

        state.start_iteration()
        assert state.iteration_count == 3
        assert state.session_iteration_count == 1

    def test_session_iteration_count_initial_value(self) -> None:
        """session_iteration_count starts at 0."""
        state = RalphState(project_root=Path("/test"))
        assert state.session_iteration_count == 0

    def test_multiple_sessions_track_independently(self) -> None:
        """Multiple session transitions maintain correct counts."""
        state = RalphState(project_root=Path("/test"))

        # First session: 3 iterations
        state.start_iteration()
        state.start_iteration()
        state.start_iteration()
        assert state.iteration_count == 3
        assert state.session_iteration_count == 3

        # Second session: 2 iterations
        state.start_new_session("session-2")
        state.start_iteration()
        state.start_iteration()
        assert state.iteration_count == 5
        assert state.session_iteration_count == 2

        # Third session: 1 iteration
        state.start_new_session("session-3")
        state.start_iteration()
        assert state.iteration_count == 6
        assert state.session_iteration_count == 1


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
