"""Phase executors for Ralph orchestrator.

Provides phase-specific execution logic using the Claude Agent SDK.
Each executor handles its phase's unique requirements while sharing
common iteration infrastructure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ralph.config import RalphConfig, load_config
from ralph.models import ImplementationPlan, Phase, RalphState, Task
from ralph.persistence import load_plan, load_state, save_plan, save_state
from ralph.phases import get_phase_prompt
from ralph.sdk_client import IterationResult, RalphSDKClient, create_ralph_client

if TYPE_CHECKING:
    pass


@dataclass
class PhaseExecutionResult:
    """Result from executing a phase."""

    success: bool
    phase: Phase
    iterations_run: int = 0
    tasks_completed: int = 0
    cost_usd: float = 0.0
    tokens_used: int = 0
    error: str | None = None
    completion_notes: str | None = None
    needs_phase_transition: bool = False
    next_phase: Phase | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)


class PhaseExecutor(ABC):
    """Base class for phase execution.

    Each phase has specific goals, tools, and completion criteria.
    Executors manage the SDK client and iteration loop for their phase.
    """

    def __init__(
        self,
        project_root: Path,
        state: RalphState | None = None,
        config: RalphConfig | None = None,
    ) -> None:
        """Initialize executor.

        Args:
            project_root: Path to the project root
            state: Optional pre-loaded state
            config: Optional pre-loaded config
        """
        self.project_root = project_root
        self.config = config or load_config(project_root)
        self._state = state
        self._client: RalphSDKClient | None = None
        self._plan: ImplementationPlan | None = None

    @property
    def state(self) -> RalphState:
        """Get current state, loading if needed."""
        if self._state is None:
            self._state = load_state(self.project_root)
        return self._state

    @property
    def plan(self) -> ImplementationPlan:
        """Get current plan, loading if needed."""
        if self._plan is None:
            self._plan = load_plan(self.project_root)
        return self._plan

    @property
    def client(self) -> RalphSDKClient:
        """Get SDK client, creating if needed."""
        if self._client is None:
            self._client = create_ralph_client(
                state=self.state,
                config=self.config,
            )
        return self._client

    @property
    @abstractmethod
    def phase(self) -> Phase:
        """The phase this executor handles."""
        pass

    def get_system_prompt(self, task: Task | None = None) -> str:
        """Get the system prompt for this phase."""
        return get_phase_prompt(
            phase=self.phase,
            project_root=self.project_root,
            task=task,
            config=self.config,
        )

    def save_state(self) -> None:
        """Save current state."""
        save_state(self.state, self.project_root)

    def save_plan(self) -> None:
        """Save current plan."""
        save_plan(self.plan, self.project_root)

    @abstractmethod
    async def execute(self, **kwargs: Any) -> PhaseExecutionResult:
        """Execute the phase.

        Returns:
            PhaseExecutionResult with outcomes
        """
        pass

    async def run_iteration(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_turns: int | None = None,
    ) -> IterationResult:
        """Run a single iteration using the SDK client.

        Args:
            prompt: User prompt for this iteration
            system_prompt: Optional system prompt override
            max_turns: Optional max turns override

        Returns:
            IterationResult with metrics
        """
        # Start iteration tracking
        self.state.start_iteration()

        # Run iteration
        result = await self.client.run_iteration(
            prompt=prompt,
            phase=self.phase,
            system_prompt=system_prompt,
            max_turns=max_turns,
        )

        # Record iteration metrics
        self.state.end_iteration(
            cost_usd=result.cost_usd,
            tokens_used=result.tokens_used,
            task_completed=result.task_completed,
        )

        # Save state after each iteration
        self.save_state()

        return result


class DiscoveryExecutor(PhaseExecutor):
    """Executor for the Discovery phase.

    Uses JTBD framework to gather requirements through interactive
    questioning with the user.
    """

    @property
    def phase(self) -> Phase:
        return Phase.DISCOVERY

    async def execute(
        self,
        initial_goal: str | None = None,
        max_iterations: int = 10,
        **kwargs: Any,
    ) -> PhaseExecutionResult:
        """Execute the Discovery phase.

        Args:
            initial_goal: Optional initial goal description
            max_iterations: Maximum iterations for discovery

        Returns:
            PhaseExecutionResult with specs created
        """
        iterations_run = 0
        total_cost = 0.0
        total_tokens = 0
        specs_created: list[str] = []

        # Build initial prompt
        if initial_goal:
            prompt = f"""You are in the DISCOVERY phase. The user has provided this initial goal:

{initial_goal}

Use the JTBD framework to clarify requirements:
1. Ask clarifying questions using the AskUserQuestion tool
2. Create spec files in the specs/ directory
3. Continue until requirements are clear

Start by asking about the user's specific needs and context."""
        else:
            prompt = """You are in the DISCOVERY phase.

Use the JTBD framework to understand what the user wants to build:
1. Ask clarifying questions using the AskUserQuestion tool
2. Create spec files in the specs/ directory for each requirement
3. Continue until requirements are fully understood

Start by asking the user what they want to build."""

        try:
            # Set phase in state
            self.state.current_phase = Phase.DISCOVERY
            self.save_state()

            # Run discovery iterations
            for i in range(max_iterations):
                result = await self.run_iteration(
                    prompt=prompt if i == 0 else "Continue discovery process.",
                    system_prompt=self.get_system_prompt(),
                )

                iterations_run += 1
                total_cost += result.cost_usd
                total_tokens += result.tokens_used

                if not result.success:
                    return PhaseExecutionResult(
                        success=False,
                        phase=self.phase,
                        iterations_run=iterations_run,
                        cost_usd=total_cost,
                        tokens_used=total_tokens,
                        error=result.error,
                    )

                # Check for phase completion signal in output
                if "discovery complete" in result.final_text.lower():
                    break

                # Check for handoff need
                if result.needs_handoff:
                    break

            # List created specs
            specs_dir = self.project_root / "specs"
            if specs_dir.exists():
                specs_created = [f.name for f in specs_dir.glob("*.md")]

            return PhaseExecutionResult(
                success=True,
                phase=self.phase,
                iterations_run=iterations_run,
                cost_usd=total_cost,
                tokens_used=total_tokens,
                needs_phase_transition=True,
                next_phase=Phase.PLANNING,
                artifacts={"specs_created": specs_created},
                completion_notes=f"Created {len(specs_created)} spec files",
            )

        except Exception as e:
            return PhaseExecutionResult(
                success=False,
                phase=self.phase,
                iterations_run=iterations_run,
                cost_usd=total_cost,
                tokens_used=total_tokens,
                error=str(e),
            )


class PlanningExecutor(PhaseExecutor):
    """Executor for the Planning phase.

    Analyzes specs and codebase to create implementation plan
    with sized, prioritized tasks.
    """

    @property
    def phase(self) -> Phase:
        return Phase.PLANNING

    async def execute(
        self,
        max_iterations: int = 30,
        **kwargs: Any,
    ) -> PhaseExecutionResult:
        """Execute the Planning phase.

        Args:
            max_iterations: Maximum iterations for planning

        Returns:
            PhaseExecutionResult with tasks created
        """
        iterations_run = 0
        total_cost = 0.0
        total_tokens = 0

        prompt = """You are in the PLANNING phase.

Analyze the specs/ directory and current codebase to create an implementation plan:

1. Read all spec files in specs/ directory
2. Analyze the existing codebase structure
3. Identify gaps between specs and implementation
4. Create tasks using the ralph_add_task tool for each piece of work
5. Size tasks to fit within ~30 minutes of work each
6. Set dependencies between tasks appropriately
7. Set priorities (1 = highest priority)

Each task should have:
- Clear description of what to implement
- Dependencies on other tasks if any
- Verification criteria (how to know it's done)

Start by reading the specs and analyzing the codebase."""

        try:
            # Set phase in state
            self.state.current_phase = Phase.PLANNING
            self.save_state()

            # Run planning iterations
            for i in range(max_iterations):
                result = await self.run_iteration(
                    prompt=prompt if i == 0 else "Continue planning. Create more tasks if needed.",
                    system_prompt=self.get_system_prompt(),
                )

                iterations_run += 1
                total_cost += result.cost_usd
                total_tokens += result.tokens_used

                if not result.success:
                    return PhaseExecutionResult(
                        success=False,
                        phase=self.phase,
                        iterations_run=iterations_run,
                        cost_usd=total_cost,
                        tokens_used=total_tokens,
                        error=result.error,
                    )

                # Check for phase completion signal
                if "planning complete" in result.final_text.lower():
                    break

                # Check for handoff need
                if result.needs_handoff:
                    break

                # Reload plan to check progress
                self._plan = None  # Force reload
                if self.plan.pending_count > 0:
                    # Have tasks, may be ready to proceed
                    break

            # Get final task count
            self._plan = None
            task_count = len(self.plan.tasks)

            return PhaseExecutionResult(
                success=True,
                phase=self.phase,
                iterations_run=iterations_run,
                cost_usd=total_cost,
                tokens_used=total_tokens,
                needs_phase_transition=True,
                next_phase=Phase.BUILDING,
                artifacts={"tasks_created": task_count},
                completion_notes=f"Created {task_count} tasks in plan",
            )

        except Exception as e:
            return PhaseExecutionResult(
                success=False,
                phase=self.phase,
                iterations_run=iterations_run,
                cost_usd=total_cost,
                tokens_used=total_tokens,
                error=str(e),
            )


class BuildingExecutor(PhaseExecutor):
    """Executor for the Building phase.

    Iteratively implements tasks from the plan, one task per iteration.
    Uses TDD approach and enforces code quality.
    """

    @property
    def phase(self) -> Phase:
        return Phase.BUILDING

    def _format_criteria(self, task: Task) -> str:
        """Format verification criteria for display."""
        if task.verification_criteria:
            return ", ".join(task.verification_criteria)
        return "Implement and test"

    async def execute(
        self,
        target_task_id: str | None = None,
        max_iterations: int = 100,
        **kwargs: Any,
    ) -> PhaseExecutionResult:
        """Execute the Building phase.

        Args:
            target_task_id: Optional specific task to work on
            max_iterations: Maximum iterations

        Returns:
            PhaseExecutionResult with tasks completed
        """
        iterations_run = 0
        tasks_completed = 0
        total_cost = 0.0
        total_tokens = 0

        try:
            # Set phase in state
            self.state.current_phase = Phase.BUILDING
            self.save_state()

            # Main building loop
            for _ in range(max_iterations):
                # Get next task
                self._plan = None  # Force reload
                if target_task_id:
                    task = self.plan.get_task_by_id(target_task_id)
                    if task is None:
                        return PhaseExecutionResult(
                            success=False,
                            phase=self.phase,
                            iterations_run=iterations_run,
                            tasks_completed=tasks_completed,
                            cost_usd=total_cost,
                            tokens_used=total_tokens,
                            error=f"Task not found: {target_task_id}",
                        )
                else:
                    task = self.plan.get_next_task()

                if task is None:
                    # No more tasks
                    break

                # Build prompt for this task
                prompt = f"""You are in the BUILDING phase.

Your current task:
- ID: {task.id}
- Description: {task.description}
- Priority: {task.priority}
- Dependencies: {', '.join(task.dependencies) if task.dependencies else 'None'}
- Verification criteria: {self._format_criteria(task)}

Instructions:
1. First call ralph_mark_task_in_progress with task_id="{task.id}"
2. Implement the task using TDD:
   - Write failing tests first
   - Implement the feature
   - Make tests pass
3. Run tests with 'uv run pytest'
4. When complete, call ralph_mark_task_complete with verification notes
5. If blocked, call ralph_mark_task_blocked with reason

Use the available tools to read/write files, run commands, and manage tasks.
Start implementing now."""

                result = await self.run_iteration(
                    prompt=prompt,
                    system_prompt=self.get_system_prompt(task),
                )

                iterations_run += 1
                total_cost += result.cost_usd
                total_tokens += result.tokens_used

                if result.task_completed:
                    tasks_completed += 1

                if not result.success:
                    # Record but continue - circuit breaker will halt if needed
                    self.state.circuit_breaker.record_failure(
                        result.error or "unknown_error"
                    )
                else:
                    self.state.circuit_breaker.record_success(
                        tasks_completed=1 if result.task_completed else 0
                    )

                self.save_state()

                # Check circuit breaker
                should_halt, halt_reason = self.state.should_halt()
                if should_halt:
                    return PhaseExecutionResult(
                        success=False,
                        phase=self.phase,
                        iterations_run=iterations_run,
                        tasks_completed=tasks_completed,
                        cost_usd=total_cost,
                        tokens_used=total_tokens,
                        error=f"Circuit breaker tripped: {halt_reason}",
                    )

                # Check for handoff need
                if result.needs_handoff:
                    # Start new session
                    self.client.reset_session()
                    self.state.context_budget.reset()
                    self.save_state()

                # If targeting specific task and it's done, stop
                if target_task_id and result.task_completed:
                    break

            # Check if all tasks complete
            self._plan = None
            all_complete = self.plan.pending_count == 0

            return PhaseExecutionResult(
                success=True,
                phase=self.phase,
                iterations_run=iterations_run,
                tasks_completed=tasks_completed,
                cost_usd=total_cost,
                tokens_used=total_tokens,
                needs_phase_transition=all_complete,
                next_phase=Phase.VALIDATION if all_complete else None,
                completion_notes=f"Completed {tasks_completed} tasks",
            )

        except Exception as e:
            return PhaseExecutionResult(
                success=False,
                phase=self.phase,
                iterations_run=iterations_run,
                tasks_completed=tasks_completed,
                cost_usd=total_cost,
                tokens_used=total_tokens,
                error=str(e),
            )


class ValidationExecutor(PhaseExecutor):
    """Executor for the Validation phase.

    Runs comprehensive verification including tests, linting,
    type checking, and spec compliance.
    """

    @property
    def phase(self) -> Phase:
        return Phase.VALIDATION

    async def _request_human_approval(
        self,
        validation_summary: str,
        iterations: int,
        cost: float,
    ) -> bool:
        """Request human approval before completing validation.

        Args:
            validation_summary: Summary of validation results
            iterations: Number of iterations completed
            cost: Total cost in USD

        Returns:
            True if approved, False if rejected
        """
        import asyncio

        print("\n" + "=" * 60)
        print("VALIDATION COMPLETE - HUMAN APPROVAL REQUIRED")
        print("=" * 60)
        print(f"\nIterations: {iterations}")
        print(f"Cost: ${cost:.4f}")
        print("\nValidation Summary:")
        print("-" * 40)
        # Show first 500 chars of summary
        summary_preview = validation_summary[:500]
        if len(validation_summary) > 500:
            summary_preview += "..."
        print(summary_preview)
        print("-" * 40)

        # Use asyncio-compatible input
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: input("\nApprove validation? [y/N]: ").strip().lower()
            )
        except EOFError:
            # Non-interactive mode - default to approval if tests pass
            print("Non-interactive mode detected, auto-approving...")
            return True

        return response in ("y", "yes")

    async def execute(
        self,
        max_iterations: int = 20,
        **kwargs: Any,
    ) -> PhaseExecutionResult:
        """Execute the Validation phase.

        Args:
            max_iterations: Maximum iterations for validation

        Returns:
            PhaseExecutionResult with validation status
        """
        iterations_run = 0
        total_cost = 0.0
        total_tokens = 0
        validation_results: dict[str, bool] = {}

        prompt = """You are in the VALIDATION phase.

Perform comprehensive verification:

1. Run all tests: uv run pytest -v
2. Run linting: uv run ruff check .
3. Run type checking: uv run mypy .
4. Review specs/ and verify implementation matches
5. Check for any TODO or FIXME comments that should be addressed

Report the results of each check. If any check fails, note what needs to be fixed.
If everything passes, confirm validation is complete."""

        try:
            # Set phase in state
            self.state.current_phase = Phase.VALIDATION
            self.save_state()

            # Run validation iterations
            for i in range(max_iterations):
                result = await self.run_iteration(
                    prompt=prompt if i == 0 else "Continue validation. Fix any issues found.",
                    system_prompt=self.get_system_prompt(),
                )

                iterations_run += 1
                total_cost += result.cost_usd
                total_tokens += result.tokens_used

                if not result.success:
                    return PhaseExecutionResult(
                        success=False,
                        phase=self.phase,
                        iterations_run=iterations_run,
                        cost_usd=total_cost,
                        tokens_used=total_tokens,
                        error=result.error,
                    )

                # Check for completion signal
                if "validation complete" in result.final_text.lower():
                    validation_results["all_passed"] = True

                    # Human approval checkpoint if configured
                    if self.config.validation.require_human_approval:
                        approved = await self._request_human_approval(
                            validation_summary=result.final_text,
                            iterations=iterations_run,
                            cost=total_cost,
                        )
                        if not approved:
                            return PhaseExecutionResult(
                                success=False,
                                phase=self.phase,
                                iterations_run=iterations_run,
                                cost_usd=total_cost,
                                tokens_used=total_tokens,
                                artifacts={"validation_results": validation_results},
                                completion_notes="Validation passed but human approval denied",
                            )
                    break

                # Check for handoff need
                if result.needs_handoff:
                    break

            return PhaseExecutionResult(
                success=validation_results.get("all_passed", False),
                phase=self.phase,
                iterations_run=iterations_run,
                cost_usd=total_cost,
                tokens_used=total_tokens,
                artifacts={"validation_results": validation_results},
                completion_notes=(
                    "Validation complete with human approval"
                    if validation_results.get("all_passed")
                    and self.config.validation.require_human_approval
                    else "Validation complete"
                    if validation_results.get("all_passed")
                    else "Validation incomplete"
                ),
            )

        except Exception as e:
            return PhaseExecutionResult(
                success=False,
                phase=self.phase,
                iterations_run=iterations_run,
                cost_usd=total_cost,
                tokens_used=total_tokens,
                error=str(e),
            )


def get_executor_for_phase(
    phase: Phase,
    project_root: Path,
    state: RalphState | None = None,
    config: RalphConfig | None = None,
) -> PhaseExecutor:
    """Get the appropriate executor for a phase.

    Args:
        phase: The phase to get executor for
        project_root: Path to project root
        state: Optional pre-loaded state
        config: Optional pre-loaded config

    Returns:
        PhaseExecutor for the specified phase
    """
    executors: dict[
        Phase,
        type[DiscoveryExecutor]
        | type[PlanningExecutor]
        | type[BuildingExecutor]
        | type[ValidationExecutor],
    ] = {
        Phase.DISCOVERY: DiscoveryExecutor,
        Phase.PLANNING: PlanningExecutor,
        Phase.BUILDING: BuildingExecutor,
        Phase.VALIDATION: ValidationExecutor,
    }

    executor_class = executors.get(phase, BuildingExecutor)
    return executor_class(project_root, state=state, config=config)


async def run_full_workflow(
    project_root: Path,
    initial_goal: str | None = None,
    config: RalphConfig | None = None,
    start_phase: Phase = Phase.DISCOVERY,
) -> list[PhaseExecutionResult]:
    """Run the full Ralph workflow from start to finish.

    Args:
        project_root: Path to project root
        initial_goal: Optional initial goal for discovery
        config: Optional configuration
        start_phase: Phase to start from

    Returns:
        List of PhaseExecutionResult for each phase run
    """
    results: list[PhaseExecutionResult] = []
    current_phase = start_phase

    phase_order = [Phase.DISCOVERY, Phase.PLANNING, Phase.BUILDING, Phase.VALIDATION]
    start_index = phase_order.index(current_phase)

    for phase in phase_order[start_index:]:
        executor = get_executor_for_phase(
            phase=phase,
            project_root=project_root,
            config=config,
        )

        kwargs: dict[str, Any] = {}
        if phase == Phase.DISCOVERY and initial_goal:
            kwargs["initial_goal"] = initial_goal

        result = await executor.execute(**kwargs)
        results.append(result)

        if not result.success:
            # Stop on failure
            break

        if not result.needs_phase_transition:
            # Phase not ready to transition
            break

    return results
