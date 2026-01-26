"""Core iteration logic for Ralph orchestrator.

Provides the execute function that integrates with LoopRunner,
connecting the SDK client to Ralph's iteration management.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ralph.config import RalphConfig, load_config
from ralph.models import Phase, Task
from ralph.persistence import load_plan, load_state, save_state
from ralph.phases import get_phase_prompt
from ralph.sdk_client import IterationResult, create_ralph_client

if TYPE_CHECKING:
    pass


@dataclass
class IterationContext:
    """Context for a single iteration.

    Contains all the information needed to execute one iteration
    of the Ralph loop.
    """

    iteration: int
    phase: Phase
    system_prompt: str
    task: Task | None
    usage_percentage: float
    session_id: str | None

    def get_user_prompt(self) -> str:
        """Generate the user prompt for this iteration."""
        if self.task is None:
            # No specific task - general phase work
            return f"""Continue with the {self.phase.value} phase.
Check the plan summary and state summary to understand current progress."""

        # Task-specific prompt
        task = self.task
        deps = ", ".join(task.dependencies) if task.dependencies else "None"
        if task.verification_criteria:
            criteria = "\n".join(f"  - {c}" for c in task.verification_criteria)
        else:
            criteria = "  - Implementation complete and tested"

        return f"""Your current task:

**Task ID:** {task.id}
**Description:** {task.description}
**Priority:** {task.priority}
**Dependencies:** {deps}
**Verification Criteria:**
{criteria}

Instructions:
1. Call ralph_mark_task_in_progress with task_id="{task.id}"
2. Implement the task following TDD principles
3. Run tests to verify: uv run pytest
4. When complete, call ralph_mark_task_complete with verification notes
5. If blocked, call ralph_mark_task_blocked with a clear reason

Start implementing now."""


def create_execute_function(
    project_root: Path,
    config: RalphConfig | None = None,
) -> Callable[..., Any]:
    """Create an execute function for use with LoopRunner.

    The returned function matches the signature expected by LoopRunner.run():
    execute_fn(context: dict) -> tuple[float, int, bool, str | None, str | None]

    Args:
        project_root: Path to the project root
        config: Optional configuration

    Returns:
        Execute function for LoopRunner
    """
    cfg = config or load_config(project_root)

    def execute(context: dict[str, Any]) -> tuple[float, int, bool, str | None, str | None]:
        """Execute a single iteration.

        Args:
            context: Iteration context from LoopRunner.pre_iteration()

        Returns:
            Tuple of (cost_usd, tokens_used, task_completed, task_id, error)
        """
        # Run async iteration in sync context
        return asyncio.run(_execute_async(context, project_root, cfg))

    return execute


async def _execute_async(
    context: dict[str, Any],
    project_root: Path,
    config: RalphConfig,
) -> tuple[float, int, bool, str | None, str | None]:
    """Async implementation of iteration execution.

    Args:
        context: Iteration context from LoopRunner
        project_root: Path to project root
        config: Ralph configuration

    Returns:
        Tuple of (cost_usd, tokens_used, task_completed, task_id, error)
    """
    # Load current state
    state = load_state(project_root)
    plan = load_plan(project_root)

    # Create SDK client
    client = create_ralph_client(state=state, config=config)

    # Get next task
    task = plan.get_next_task()

    # Build iteration context
    iter_ctx = IterationContext(
        iteration=context.get("iteration", state.iteration_count),
        phase=Phase(context.get("phase", state.current_phase.value)),
        system_prompt=context.get("system_prompt", ""),
        task=task,
        usage_percentage=context.get("usage_percentage", 0.0),
        session_id=context.get("session_id"),
    )

    # Run iteration
    try:
        result = await client.run_iteration(
            prompt=iter_ctx.get_user_prompt(),
            phase=iter_ctx.phase,
            system_prompt=iter_ctx.system_prompt,
        )

        return (
            result.cost_usd,
            result.tokens_used,
            result.task_completed,
            result.task_id,
            result.error,
        )

    except Exception as e:
        return (0.0, 0, False, None, str(e))


async def execute_single_iteration(
    project_root: Path,
    prompt: str | None = None,
    config: RalphConfig | None = None,
) -> IterationResult:
    """Execute a single iteration with the SDK client.

    This is a convenience function for running one iteration
    without the full LoopRunner infrastructure.

    Args:
        project_root: Path to project root
        prompt: Optional custom prompt (defaults to task-based prompt)
        config: Optional configuration

    Returns:
        IterationResult with metrics and outcomes
    """
    cfg = config or load_config(project_root)
    state = load_state(project_root)
    plan = load_plan(project_root)

    # Create client
    client = create_ralph_client(state=state, config=cfg)

    # Get task
    task = plan.get_next_task()

    # Build prompt
    if prompt is None:
        ctx = IterationContext(
            iteration=state.iteration_count + 1,
            phase=state.current_phase,
            system_prompt=get_phase_prompt(
                phase=state.current_phase,
                project_root=project_root,
                task=task,
                config=cfg,
            ),
            task=task,
            usage_percentage=(
                state.context_budget.current_usage / state.context_budget.total_capacity * 100
                if state.context_budget.total_capacity > 0
                else 0
            ),
            session_id=state.session_id,
        )
        prompt = ctx.get_user_prompt()
        system_prompt = ctx.system_prompt
    else:
        system_prompt = get_phase_prompt(
            phase=state.current_phase,
            project_root=project_root,
            task=task,
            config=cfg,
        )

    # Track iteration start
    state.start_iteration()

    # Run iteration
    result = await client.run_iteration(
        prompt=prompt,
        system_prompt=system_prompt,
    )

    # Track iteration end
    state.end_iteration(
        cost_usd=result.cost_usd,
        tokens_used=result.tokens_used,
        task_completed=result.task_completed,
    )

    # Save state
    save_state(state, project_root)

    return result


def run_iteration_sync(
    project_root: Path,
    prompt: str | None = None,
    config: RalphConfig | None = None,
) -> IterationResult:
    """Synchronous wrapper for execute_single_iteration.

    Args:
        project_root: Path to project root
        prompt: Optional custom prompt
        config: Optional configuration

    Returns:
        IterationResult with metrics
    """
    return asyncio.run(execute_single_iteration(project_root, prompt, config))


async def execute_until_complete(
    project_root: Path,
    config: RalphConfig | None = None,
    max_iterations: int = 100,
    on_iteration: Callable[..., Any] | None = None,
) -> list[IterationResult]:
    """Execute iterations until all tasks are complete or limits reached.

    Args:
        project_root: Path to project root
        config: Optional configuration
        max_iterations: Maximum iterations to run
        on_iteration: Optional callback for each iteration

    Returns:
        List of IterationResult from all iterations
    """
    results: list[IterationResult] = []
    cfg = config or load_config(project_root)

    for i in range(max_iterations):
        # Load fresh state each iteration
        state = load_state(project_root)
        plan = load_plan(project_root)

        # Check completion
        if plan.pending_count == 0:
            break

        # Check circuit breaker
        should_halt, _ = state.should_halt()
        if should_halt:
            break

        # Run iteration
        result = await execute_single_iteration(project_root, config=cfg)
        results.append(result)

        # Callback
        if on_iteration:
            on_iteration(result, i + 1)

        # Check for failures
        if not result.success:
            # Continue - circuit breaker will halt if needed
            continue

    return results


# Convenience exports
__all__ = [
    "IterationContext",
    "create_execute_function",
    "execute_single_iteration",
    "execute_until_complete",
    "run_iteration_sync",
]
