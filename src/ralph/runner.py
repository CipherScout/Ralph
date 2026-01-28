"""Loop runner for Ralph's deterministic agentic workflow.

This module provides the main orchestration loop that:
- Controls phase transitions
- Enforces circuit breaker limits
- Handles recovery from failures
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ralph.config import RalphConfig, load_config
from ralph.context import generate_llm_session_summary
from ralph.models import Phase, RalphState, TaskStatus
from ralph.persistence import load_plan, save_plan, save_state
from ralph.phases import PhaseOrchestrator, PhaseResult, get_phase_prompt

logger = logging.getLogger(__name__)


class LoopStatus(str, Enum):
    """Status of the Ralph loop."""

    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    HALTED = "halted"


class RecoveryAction(str, Enum):
    """Recovery actions for failure scenarios."""

    RETRY = "retry"
    SKIP_TASK = "skip_task"
    MANUAL_INTERVENTION = "manual_intervention"
    RESET_CIRCUIT_BREAKER = "reset_circuit_breaker"
    HANDOFF = "handoff"


@dataclass
class RunnerIterationResult:
    """Result of a single iteration from the loop runner.

    Note: This is distinct from sdk_client.IterationResult which contains
    SDK-specific fields like metrics.
    """

    iteration: int
    phase: Phase
    success: bool
    cost_usd: float
    tokens_used: int
    task_completed: bool = False
    task_id: str | None = None
    error: str | None = None
    messages: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass
class LoopResult:
    """Result of running the Ralph loop."""

    status: LoopStatus
    iterations_completed: int
    tasks_completed: int
    total_cost_usd: float
    total_tokens_used: int
    final_phase: Phase
    error: str | None = None
    halt_reason: str | None = None
    session_count: int = 1
    iteration_results: list[RunnerIterationResult] = field(default_factory=list)


@dataclass
class RecoveryStrategy:
    """Strategy for recovering from failures."""

    action: RecoveryAction
    max_retries: int = 3
    backoff_multiplier: float = 1.5
    current_retry: int = 0

    def should_retry(self) -> bool:
        """Check if retry is appropriate."""
        return self.current_retry < self.max_retries

    def increment_retry(self) -> None:
        """Increment retry counter."""
        self.current_retry += 1


class LoopRunner:
    """Main orchestrator for the Ralph loop.

    The runner is responsible for:
    1. Starting and managing iterations
    2. Handling phase transitions
    3. Managing context handoffs
    4. Enforcing circuit breaker limits
    5. Recovery from failures

    The runner does NOT execute LLM calls - that is done by the
    caller who provides an iteration callback.
    """

    def __init__(
        self,
        project_root: Path,
        config: RalphConfig | None = None,
        on_iteration_start: Callable[[dict[str, Any]], None] | None = None,
        on_iteration_end: Callable[[RunnerIterationResult], None] | None = None,
        on_phase_change: Callable[[Phase, Phase], None] | None = None,
        on_handoff: Callable[[str], None] | None = None,
        on_halt: Callable[[str], None] | None = None,
    ):
        """Initialize the loop runner.

        Args:
            project_root: Path to the project root
            config: Optional configuration override
            on_iteration_start: Callback when iteration starts
            on_iteration_end: Callback when iteration ends
            on_phase_change: Callback when phase changes
            on_handoff: Callback when context handoff occurs
            on_halt: Callback when loop halts
        """
        self.project_root = project_root
        self.config = config or load_config(project_root)
        self.orchestrator = PhaseOrchestrator(project_root, self.config)

        # Callbacks
        self.on_iteration_start = on_iteration_start
        self.on_iteration_end = on_iteration_end
        self.on_phase_change = on_phase_change
        self.on_handoff = on_handoff
        self.on_halt = on_halt

        # State
        self.status = LoopStatus.RUNNING
        self._iteration_results: list[RunnerIterationResult] = []
        self._session_count = 1
        self._recovery_strategy: RecoveryStrategy | None = None

    @property
    def state(self) -> RalphState:
        """Get current state."""
        return self.orchestrator.state

    @property
    def current_phase(self) -> Phase:
        """Get current phase."""
        return self.orchestrator.get_current_phase()

    def get_system_prompt(self) -> str:
        """Get the system prompt for the current phase."""
        plan = load_plan(self.project_root)
        task = plan.get_next_task()
        return get_phase_prompt(
            phase=self.current_phase,
            project_root=self.project_root,
            task=task,
            config=self.config,
        )

    def start_session(self) -> str:
        """Start a new session and return session ID.

        Also resets any stale IN_PROGRESS tasks to PENDING to prevent
        tasks from being stuck forever after crashes.
        """
        session_id = str(uuid.uuid4())[:8]
        self.state.start_new_session(session_id)

        # Reset any stale IN_PROGRESS tasks from previous sessions
        plan = load_plan(self.project_root)
        stale_count = plan.reset_stale_in_progress_tasks()
        if stale_count > 0:
            save_plan(plan, self.project_root)

        save_state(self.state, self.project_root)
        return session_id

    def should_continue(self) -> tuple[bool, str | None]:
        """Check if loop should continue.

        Returns:
            Tuple of (should_continue, reason_if_not)
        """
        # Check paused
        if self.orchestrator.should_pause():
            return False, "paused"

        # Check circuit breaker
        should_halt, halt_reason = self.orchestrator.check_circuit_breaker()
        if should_halt:
            return False, halt_reason

        # Check max iterations
        if self.state.iteration_count >= self.config.max_iterations:
            return False, f"max_iterations:{self.config.max_iterations}"

        # Check completion (all tasks done in validation)
        if self.current_phase == Phase.VALIDATION:
            plan = load_plan(self.project_root)
            if plan.pending_count == 0 and all(
                t.status != TaskStatus.IN_PROGRESS for t in plan.tasks
            ):
                # Check if validation passed (would need external signal)
                pass

        return True, None

    def pre_iteration(self) -> dict[str, Any]:
        """Prepare for an iteration and return context.

        Returns:
            Context dict for the iteration
        """
        context = self.orchestrator.start_iteration()

        # Add system prompt
        context["system_prompt"] = self.get_system_prompt()

        # Fire callback
        if self.on_iteration_start:
            self.on_iteration_start(context)

        return context

    def post_iteration(
        self,
        cost_usd: float,
        tokens_used: int,
        task_completed: bool,
        task_id: str | None = None,
        error: str | None = None,
    ) -> PhaseResult:
        """Process iteration completion.

        Args:
            cost_usd: Cost of the iteration
            tokens_used: Tokens used in the iteration
            task_completed: Whether a task was completed
            task_id: ID of completed task if any
            error: Error message if failed

        Returns:
            PhaseResult indicating next steps
        """
        # Record iteration result
        result = RunnerIterationResult(
            iteration=self.state.iteration_count,
            phase=self.current_phase,
            success=error is None,
            cost_usd=cost_usd,
            tokens_used=tokens_used,
            task_completed=task_completed,
            task_id=task_id,
            error=error,
        )
        self._iteration_results.append(result)

        # Fire callback
        if self.on_iteration_end:
            self.on_iteration_end(result)

        # End iteration in orchestrator
        phase_result = self.orchestrator.end_iteration(
            cost_usd=cost_usd,
            tokens_used=tokens_used,
            task_completed=task_completed,
        )

        # Handle phase transition
        if phase_result.should_transition and phase_result.next_phase:
            old_phase = self.current_phase
            self.orchestrator.transition_to(phase_result.next_phase)
            if self.on_phase_change:
                self.on_phase_change(old_phase, phase_result.next_phase)

        # Handle handoff
        if phase_result.needs_handoff:
            self._handle_handoff(phase_result.handoff_reason or "context_budget")

        # Handle failure
        if not phase_result.success:
            self._handle_failure(phase_result.error or "unknown_error")

        return phase_result

    def _handle_handoff(self, reason: str) -> None:
        """Handle context handoff."""
        # Generate basic summary from iteration results
        summary_parts = []
        for result in self._iteration_results[-5:]:  # Last 5 iterations
            if result.task_id:
                summary_parts.append(
                    f"- Completed task {result.task_id}"
                    if result.task_completed
                    else f"- Worked on task {result.task_id}"
                )

        basic_summary = "\n".join(summary_parts) if summary_parts else None

        # Attempt LLM-generated summary
        llm_summary = None
        try:
            plan = load_plan(self.project_root)
            llm_summary = asyncio.run(
                generate_llm_session_summary(
                    state=self.state,
                    plan=plan,
                    project_root=self.project_root,
                    recent_work=basic_summary,
                )
            )
        except RuntimeError:
            # Already in async context - try with existing loop
            try:
                asyncio.get_running_loop()  # Verify we're in async context
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        generate_llm_session_summary(
                            state=self.state,
                            plan=load_plan(self.project_root),
                            project_root=self.project_root,
                            recent_work=basic_summary,
                        ),
                    )
                    llm_summary = future.result(timeout=30)
            except Exception as e:
                logger.warning("Failed to generate LLM summary in async context: %s", e)
        except Exception as e:
            logger.warning("Failed to generate LLM session summary: %s", e)

        # Use LLM summary if available, otherwise fall back to basic summary
        summary = llm_summary or basic_summary

        # Execute handoff
        new_session_id = self.orchestrator.execute_handoff(reason, summary)
        self._session_count += 1

        # Clear iteration results for new session
        self._iteration_results = []

        # Fire callback
        if self.on_handoff:
            self.on_handoff(new_session_id)

    def _handle_failure(self, error: str) -> RecoveryAction:
        """Handle iteration failure and determine recovery action.

        Args:
            error: Error description

        Returns:
            Recovery action to take
        """
        # Initialize recovery strategy if needed
        if self._recovery_strategy is None:
            self._recovery_strategy = RecoveryStrategy(
                action=RecoveryAction.RETRY,
                max_retries=self.config.safety.max_retries,
            )

        # Record failure in circuit breaker
        self.state.circuit_breaker.record_failure(error)

        # Determine action
        if self._recovery_strategy.should_retry():
            self._recovery_strategy.increment_retry()
            return RecoveryAction.RETRY

        # Check if we should skip task
        plan = load_plan(self.project_root)
        next_task = plan.get_next_task()
        if next_task and next_task.retry_count >= 2:
            # Skip after multiple failures
            next_task.status = TaskStatus.BLOCKED
            next_task.completion_notes = f"BLOCKED: {error}"
            save_plan(plan, self.project_root)
            self._recovery_strategy = None  # Reset for next task
            return RecoveryAction.SKIP_TASK

        # Need manual intervention
        return RecoveryAction.MANUAL_INTERVENTION

    def run_iteration(
        self,
        execute_fn: Callable[
            [dict[str, Any]], tuple[float, int, bool, str | None, str | None]
        ],
    ) -> RunnerIterationResult:
        """Run a single iteration.

        Args:
            execute_fn: Function that executes the iteration
                       Returns (cost_usd, tokens_used, task_completed, task_id, error)

        Returns:
            IterationResult for this iteration
        """
        # Pre-iteration setup
        context = self.pre_iteration()

        # Execute (done by caller)
        cost_usd, tokens_used, task_completed, task_id, error = execute_fn(context)

        # Post-iteration processing
        self.post_iteration(
            cost_usd=cost_usd,
            tokens_used=tokens_used,
            task_completed=task_completed,
            task_id=task_id,
            error=error,
        )

        return self._iteration_results[-1]

    def run(
        self,
        execute_fn: Callable[
            [dict[str, Any]], tuple[float, int, bool, str | None, str | None]
        ],
        max_iterations: int | None = None,
    ) -> LoopResult:
        """Run the Ralph loop.

        Args:
            execute_fn: Function that executes each iteration
            max_iterations: Optional override for max iterations

        Returns:
            LoopResult summarizing the run
        """
        max_iter = max_iterations or self.config.max_iterations
        iterations_completed = 0
        tasks_completed = 0
        total_cost = 0.0
        total_tokens = 0

        # Start session if needed
        if not self.state.session_id:
            self.start_session()

        # Main loop
        while iterations_completed < max_iter:
            # Check if we should continue
            should_continue, reason = self.should_continue()
            if not should_continue:
                if reason == "paused":
                    self.status = LoopStatus.PAUSED
                else:
                    self.status = LoopStatus.HALTED
                    if self.on_halt:
                        self.on_halt(reason or "unknown")
                break

            # Run iteration
            try:
                result = self.run_iteration(execute_fn)
                iterations_completed += 1
                total_cost += result.cost_usd
                total_tokens += result.tokens_used

                if result.task_completed:
                    tasks_completed += 1

                # Reset recovery on success
                if result.success:
                    self._recovery_strategy = None

            except Exception as e:
                # Unexpected error
                self.status = LoopStatus.FAILED
                return LoopResult(
                    status=self.status,
                    iterations_completed=iterations_completed,
                    tasks_completed=tasks_completed,
                    total_cost_usd=total_cost,
                    total_tokens_used=total_tokens,
                    final_phase=self.current_phase,
                    error=str(e),
                    session_count=self._session_count,
                    iteration_results=self._iteration_results,
                )

        # Check final status
        if self.status == LoopStatus.RUNNING:
            # Check if completed
            plan = load_plan(self.project_root)
            if plan.pending_count == 0:
                self.status = LoopStatus.COMPLETED
            else:
                self.status = LoopStatus.HALTED
                if iterations_completed >= max_iter:
                    return LoopResult(
                        status=self.status,
                        iterations_completed=iterations_completed,
                        tasks_completed=tasks_completed,
                        total_cost_usd=total_cost,
                        total_tokens_used=total_tokens,
                        final_phase=self.current_phase,
                        halt_reason=f"max_iterations:{max_iter}",
                        session_count=self._session_count,
                        iteration_results=self._iteration_results,
                    )

        return LoopResult(
            status=self.status,
            iterations_completed=iterations_completed,
            tasks_completed=tasks_completed,
            total_cost_usd=total_cost,
            total_tokens_used=total_tokens,
            final_phase=self.current_phase,
            session_count=self._session_count,
            iteration_results=self._iteration_results,
        )


# ============================================================================
# Recovery Management
# ============================================================================


def determine_recovery_action(
    state: RalphState,
    error: str,
    config: RalphConfig,
) -> RecoveryAction:
    """Determine appropriate recovery action for a failure.

    Args:
        state: Current Ralph state
        error: Error description
        config: Ralph configuration

    Returns:
        Appropriate recovery action
    """
    cb = state.circuit_breaker

    # Cost limit exceeded - need manual intervention
    # Cost is tracked in RalphState, not CircuitBreaker
    if state.total_cost_usd >= cb.max_cost_usd:
        return RecoveryAction.MANUAL_INTERVENTION

    # Stagnation - try handoff to fresh context
    if cb.stagnation_count >= cb.max_stagnation_iterations:
        return RecoveryAction.HANDOFF

    # Consecutive failures - try retry first
    if cb.failure_count < cb.max_consecutive_failures:
        return RecoveryAction.RETRY

    # Too many failures - skip task
    return RecoveryAction.SKIP_TASK


def reset_recovery_state(state: RalphState) -> None:
    """Reset recovery-related state after successful recovery.

    Args:
        state: Ralph state to reset
    """
    state.circuit_breaker.reset()


def apply_recovery_action(
    action: RecoveryAction,
    project_root: Path,
    state: RalphState,
) -> bool:
    """Apply a recovery action.

    Args:
        action: Recovery action to apply
        project_root: Project root path
        state: Ralph state

    Returns:
        True if action was applied successfully
    """
    if action == RecoveryAction.RETRY:
        # Just continue - retry happens automatically
        return True

    elif action == RecoveryAction.SKIP_TASK:
        plan = load_plan(project_root)
        next_task = plan.get_next_task()
        if next_task:
            next_task.status = TaskStatus.BLOCKED
            next_task.completion_notes = "BLOCKED: Max retries exceeded"
            save_plan(plan, project_root)
        return True

    elif action == RecoveryAction.RESET_CIRCUIT_BREAKER:
        state.circuit_breaker.reset()
        save_state(state, project_root)
        return True

    elif action == RecoveryAction.HANDOFF:
        # Handoff is handled by the runner
        return True

    elif action == RecoveryAction.MANUAL_INTERVENTION:
        # Requires human action
        return False

    return False
