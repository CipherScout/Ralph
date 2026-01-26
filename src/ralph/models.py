"""Core data models for Ralph orchestrator.

These models define the state structures that persist across iterations,
enabling deterministic workflow progression while LLM context windows reset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class Phase(str, Enum):
    """Development lifecycle phases."""

    DISCOVERY = "discovery"
    PLANNING = "planning"
    BUILDING = "building"
    VALIDATION = "validation"


class TaskStatus(str, Enum):
    """Task completion states."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    BLOCKED = "blocked"


@dataclass
class Task:
    """Individual task within an implementation plan.

    Tasks are sized for single context windows (~30 min work each) with
    clear dependencies and verification criteria.
    """

    id: str
    description: str
    priority: int  # 1 = highest
    status: TaskStatus = TaskStatus.PENDING
    dependencies: list[str] = field(default_factory=list)  # task IDs
    verification_criteria: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)  # blocking reasons
    estimated_tokens: int = 30_000
    actual_tokens_used: int | None = None
    completion_notes: str | None = None
    completed_at: datetime | None = None
    retry_count: int = 0

    def is_available(self, completed_task_ids: set[str]) -> bool:
        """Check if task can be started (dependencies met)."""
        if self.status != TaskStatus.PENDING:
            return False
        return all(dep in completed_task_ids for dep in self.dependencies)


@dataclass
class ImplementationPlan:
    """Persisted to .ralph/implementation_plan.json.

    Contains prioritized tasks with dependency tracking for deterministic
    task selection by Python (not LLM).
    """

    tasks: list[Task] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_modified: datetime = field(default_factory=datetime.now)

    def get_completed_task_ids(self) -> set[str]:
        """Get IDs of all completed tasks."""
        return {t.id for t in self.tasks if t.status == TaskStatus.COMPLETE}

    def get_next_task(self) -> Task | None:
        """Deterministic selection: highest priority available task.

        Returns the highest priority (lowest number) task that:
        - Has status 'pending'
        - Has all dependencies met (completed)
        """
        completed = self.get_completed_task_ids()
        available = [t for t in self.tasks if t.is_available(completed)]
        if not available:
            return None
        return min(available, key=lambda t: t.priority)

    def get_task_by_id(self, task_id: str) -> Task | None:
        """Find task by ID."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def mark_task_complete(
        self, task_id: str, notes: str | None = None, tokens_used: int | None = None
    ) -> bool:
        """Mark a task as complete with optional metadata."""
        task = self.get_task_by_id(task_id)
        if task is None:
            return False
        task.status = TaskStatus.COMPLETE
        task.completion_notes = notes
        task.actual_tokens_used = tokens_used
        task.completed_at = datetime.now()
        self.last_modified = datetime.now()
        return True

    def mark_task_blocked(self, task_id: str, reason: str) -> bool:
        """Mark a task as blocked."""
        task = self.get_task_by_id(task_id)
        if task is None:
            return False
        task.status = TaskStatus.BLOCKED
        task.blockers.append(reason)
        task.completion_notes = f"BLOCKED: {reason}"
        self.last_modified = datetime.now()
        return True

    @property
    def completion_percentage(self) -> float:
        """Calculate completion percentage."""
        if not self.tasks:
            return 0.0
        completed = sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETE)
        return completed / len(self.tasks)

    @property
    def pending_count(self) -> int:
        """Count of pending tasks."""
        return sum(1 for t in self.tasks if t.status == TaskStatus.PENDING)

    @property
    def complete_count(self) -> int:
        """Count of completed tasks."""
        return sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETE)

    def reset_stale_in_progress_tasks(self) -> int:
        """Reset IN_PROGRESS tasks to PENDING.

        This prevents tasks from being stuck forever if the agent crashes
        during task execution. Should be called at session start.

        Returns:
            Number of tasks reset
        """
        count = 0
        for task in self.tasks:
            if task.status == TaskStatus.IN_PROGRESS:
                task.status = TaskStatus.PENDING
                count += 1
        if count > 0:
            self.last_modified = datetime.now()
        return count


@dataclass
class CircuitBreakerState:
    """Circuit breaker state for failure detection and recovery.

    Tracks consecutive failures and stagnation (no progress)
    to determine when to halt or recover.

    Note: Cost tracking is done at the RalphState level to maintain
    a single source of truth. This class references external cost
    via the check_cost_limit method.
    """

    max_consecutive_failures: int = 3
    max_stagnation_iterations: int = 5
    max_cost_usd: float = 100.0

    state: str = "closed"  # closed | open | half_open
    failure_count: int = 0
    stagnation_count: int = 0
    last_failure_reason: str | None = None

    def record_success(self, tasks_completed: int = 0, progress_made: bool = False) -> None:
        """Record a successful iteration.

        Args:
            tasks_completed: Number of tasks completed in this iteration
            progress_made: Whether meaningful progress was made (e.g., tasks created in planning)
        """
        self.failure_count = 0
        if tasks_completed > 0 or progress_made:
            self.stagnation_count = 0
        else:
            self.stagnation_count += 1
        if self.state == "half_open":
            self.state = "closed"

    def record_failure(self, reason: str) -> None:
        """Record a failed iteration.

        Args:
            reason: Description of the failure
        """
        self.failure_count += 1
        self.stagnation_count += 1
        self.last_failure_reason = reason
        if self.failure_count >= self.max_consecutive_failures:
            self.state = "open"

    def should_halt(self, current_cost_usd: float = 0.0) -> tuple[bool, str | None]:
        """Check if execution should halt.

        Args:
            current_cost_usd: Current total cost from RalphState

        Returns:
            Tuple of (should_halt, reason_or_none)
        """
        if self.failure_count >= self.max_consecutive_failures:
            return True, f"consecutive_failures:{self.failure_count}"
        if self.stagnation_count >= self.max_stagnation_iterations:
            return True, f"stagnation:{self.stagnation_count}"
        if current_cost_usd >= self.max_cost_usd:
            return True, f"cost_limit:${current_cost_usd:.2f}"
        return False, None

    def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        self.state = "closed"
        self.failure_count = 0
        self.stagnation_count = 0
        self.last_failure_reason = None


@dataclass
class ContextBudget:
    """Token budget tracking for context window management.

    Targets 40-60% utilization (the "smart zone") and triggers
    hand-off before reaching 80%.
    """

    total_capacity: int = 200_000
    system_prompt_allocation: int = 5_000
    safety_margin: float = 0.20  # Keep 20% buffer

    current_usage: int = 0
    tool_results_tokens: int = 0

    @property
    def effective_capacity(self) -> int:
        """Capacity minus safety margin."""
        return int(self.total_capacity * (1 - self.safety_margin))

    @property
    def smart_zone_max(self) -> int:
        """Upper bound of smart zone (60%)."""
        return int(self.total_capacity * 0.60)

    @property
    def available_tokens(self) -> int:
        """Remaining tokens before effective capacity."""
        return max(0, self.effective_capacity - self.current_usage)

    @property
    def usage_percentage(self) -> float:
        """Current usage as a percentage of total capacity."""
        if self.total_capacity <= 0:
            return 0.0
        return (self.current_usage / self.total_capacity) * 100

    def should_handoff(self) -> bool:
        """Check if context hand-off is needed."""
        return self.current_usage >= self.smart_zone_max

    def add_usage(self, tokens: int) -> None:
        """Track token usage."""
        self.current_usage += tokens

    def reset(self) -> None:
        """Reset for new session."""
        self.current_usage = 0
        self.tool_results_tokens = 0


@dataclass
class RalphState:
    """Master state persisted to .ralph/state.json.

    This is the single source of truth for Ralph's execution state,
    surviving across context window resets and iterations.
    """

    project_root: Path
    current_phase: Phase = Phase.BUILDING
    iteration_count: int = 0
    session_iteration_count: int = 0  # Resets each session
    session_id: str | None = None

    # Cost tracking
    total_cost_usd: float = 0.0
    total_tokens_used: int = 0

    # Timing
    started_at: datetime = field(default_factory=datetime.now)
    last_activity_at: datetime = field(default_factory=datetime.now)

    # Nested state objects
    circuit_breaker: CircuitBreakerState = field(default_factory=CircuitBreakerState)
    context_budget: ContextBudget = field(default_factory=ContextBudget)

    # Session tracking
    session_cost_usd: float = 0.0
    session_tokens_used: int = 0
    tasks_completed_this_session: int = 0

    # Control flags
    paused: bool = False

    # Phase completion signals (set by ralph_signal_*_complete tools)
    # Dict mapping phase name to completion info
    completion_signals: dict[str, dict[str, Any]] = field(default_factory=dict)

    def is_phase_complete(self, phase: str) -> bool:
        """Check if a phase has been signaled as complete."""
        return phase in self.completion_signals and self.completion_signals[phase].get(
            "complete", False
        )

    def clear_phase_completion(self, phase: str) -> None:
        """Clear the completion signal for a phase."""
        if phase in self.completion_signals:
            del self.completion_signals[phase]

    def start_iteration(self) -> None:
        """Mark start of a new iteration."""
        self.iteration_count += 1
        self.session_iteration_count += 1
        self.last_activity_at = datetime.now()

    def end_iteration(
        self, cost_usd: float, tokens_used: int, task_completed: bool, progress_made: bool = False
    ) -> None:
        """Record iteration completion.

        Args:
            cost_usd: Cost of this iteration in USD
            tokens_used: Number of tokens used in this iteration
            task_completed: Whether a task was completed in this iteration
            progress_made: Whether meaningful progress was made (e.g., tasks created in planning)
        """
        self.total_cost_usd += cost_usd
        self.total_tokens_used += tokens_used
        self.session_cost_usd += cost_usd
        self.session_tokens_used += tokens_used
        self.last_activity_at = datetime.now()
        self.context_budget.add_usage(tokens_used)

        if task_completed:
            self.tasks_completed_this_session += 1
            self.circuit_breaker.record_success(tasks_completed=1, progress_made=True)
        else:
            self.circuit_breaker.record_success(tasks_completed=0, progress_made=progress_made)

    def start_new_session(self, session_id: str) -> None:
        """Initialize a new session (fresh context window)."""
        self.session_id = session_id
        self.session_cost_usd = 0.0
        self.session_tokens_used = 0
        self.tasks_completed_this_session = 0
        self.session_iteration_count = 0  # Reset session iteration counter
        self.context_budget.reset()

    def advance_phase(self, new_phase: Phase) -> None:
        """Transition to a new phase."""
        self.current_phase = new_phase
        self.last_activity_at = datetime.now()
        # Phase transitions always start fresh sessions
        self.context_budget.reset()

    def needs_handoff(self) -> bool:
        """Check if context hand-off is needed."""
        return self.context_budget.should_handoff()

    def should_halt(self) -> tuple[bool, str | None]:
        """Check if execution should halt via circuit breaker."""
        return self.circuit_breaker.should_halt(current_cost_usd=self.total_cost_usd)
