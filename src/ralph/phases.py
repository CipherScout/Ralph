"""Phase implementations for Ralph's development lifecycle.

Each phase has specific goals, allowed tools, and transition criteria.
The Python orchestrator controls phase transitions, not the LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ralph.config import RalphConfig, load_config
from ralph.context import (
    build_iteration_context,
    execute_context_handoff,
    should_trigger_handoff,
)
from ralph.models import (
    ImplementationPlan,
    Phase,
    RalphState,
    Task,
    TaskStatus,
)
from ralph.persistence import load_plan, load_state, save_plan, save_state


@dataclass
class PhaseResult:
    """Result of executing a phase iteration."""

    success: bool
    phase: Phase
    tasks_completed: int = 0
    tasks_blocked: int = 0
    error: str | None = None
    should_transition: bool = False
    next_phase: Phase | None = None
    needs_handoff: bool = False
    handoff_reason: str | None = None
    messages: list[str] = field(default_factory=list)


@dataclass
class DiscoveryOutput:
    """Output from Discovery phase."""

    project_goal: str
    functional_requirements: list[str]
    non_functional_requirements: list[str]
    constraints: list[str]
    questions_asked: int = 0
    questions_answered: int = 0


@dataclass
class PlanningOutput:
    """Output from Planning phase."""

    tasks: list[Task]
    architecture_notes: list[str] = field(default_factory=list)
    dependencies_mapped: bool = False
    estimated_total_tokens: int = 0


class PhaseOrchestrator:
    """Orchestrates phase execution with deterministic control.

    The orchestrator manages:
    - Phase transitions based on completion criteria
    - Context budget monitoring
    - Circuit breaker state
    - Task state management
    """

    def __init__(self, project_root: Path, config: RalphConfig | None = None):
        self.project_root = project_root
        self.config = config or load_config(project_root)
        self._state: RalphState | None = None
        self._plan: ImplementationPlan | None = None

    @property
    def state(self) -> RalphState:
        """Load state lazily."""
        if self._state is None:
            self._state = load_state(self.project_root)
        return self._state

    @property
    def plan(self) -> ImplementationPlan:
        """Load plan lazily."""
        if self._plan is None:
            self._plan = load_plan(self.project_root)
        return self._plan

    def refresh_state(self) -> None:
        """Force reload state from disk."""
        self._state = load_state(self.project_root)
        self._plan = load_plan(self.project_root)

    def save_all(self) -> None:
        """Persist current state and plan."""
        if self._state:
            save_state(self._state, self.project_root)
        if self._plan:
            save_plan(self._plan, self.project_root)

    def check_circuit_breaker(self) -> tuple[bool, str | None]:
        """Check if circuit breaker should halt execution."""
        return self.state.should_halt()

    def check_context_budget(self) -> tuple[bool, str | None]:
        """Check if context handoff is needed."""
        return should_trigger_handoff(self.state)

    def should_pause(self) -> bool:
        """Check if loop should pause."""
        return self.state.paused

    def get_current_phase(self) -> Phase:
        """Get current phase."""
        return self.state.current_phase

    def transition_to(self, phase: Phase) -> None:
        """Transition to a new phase."""
        self.state.advance_phase(phase)
        self.save_all()

    def start_iteration(self) -> dict[str, Any]:
        """Start a new iteration and return context."""
        self.state.start_iteration()
        context = build_iteration_context(self.state, self.plan, self.project_root)
        return {
            "iteration": context.iteration,
            "phase": context.phase.value,
            "session_id": context.session_id,
            "current_task": context.current_task,
            "usage_percentage": context.usage_percentage,
            "remaining_tokens": context.remaining_tokens,
        }

    def end_iteration(
        self,
        cost_usd: float,
        tokens_used: int,
        task_completed: bool,
    ) -> PhaseResult:
        """End an iteration and determine next steps."""
        self.state.end_iteration(cost_usd, tokens_used, task_completed)

        # Check for handoff need
        needs_handoff, handoff_reason = self.check_context_budget()

        # Check circuit breaker
        should_halt, halt_reason = self.check_circuit_breaker()

        # Determine phase transition
        should_transition, next_phase = self._check_phase_transition()

        result = PhaseResult(
            success=not should_halt,
            phase=self.state.current_phase,
            tasks_completed=1 if task_completed else 0,
            needs_handoff=needs_handoff,
            handoff_reason=handoff_reason,
            should_transition=should_transition,
            next_phase=next_phase,
        )

        if should_halt:
            result.error = halt_reason
            result.success = False

        self.save_all()
        return result

    def _check_phase_transition(self) -> tuple[bool, Phase | None]:
        """Check if phase should transition based on completion criteria."""
        phase = self.state.current_phase

        if phase == Phase.DISCOVERY:
            # Discovery completes when requirements are captured
            # This is typically triggered manually or by specific criteria
            return False, None

        elif phase == Phase.PLANNING:
            # Planning completes when all tasks are defined
            if self.plan.tasks and all(t.priority > 0 for t in self.plan.tasks):
                return True, Phase.BUILDING
            return False, None

        elif phase == Phase.BUILDING:
            # Building completes when all tasks are done or blocked
            pending = self.plan.pending_count
            in_progress = sum(
                1 for t in self.plan.tasks if t.status == TaskStatus.IN_PROGRESS
            )
            if pending == 0 and in_progress == 0:
                return True, Phase.VALIDATION
            return False, None

        elif phase == Phase.VALIDATION:
            # Validation completes when all verifications pass
            # This is typically triggered by test/lint/typecheck success
            return False, None

        return False, None

    def execute_handoff(self, reason: str, summary: str | None = None) -> str:
        """Execute context handoff and return new session ID."""
        result = execute_context_handoff(
            state=self.state,
            plan=self.plan,
            project_root=self.project_root,
            reason=reason,
            session_summary=summary,
        )
        if result.success:
            self.refresh_state()
            return result.next_session_id or ""
        raise RuntimeError(f"Handoff failed: {result.reason}")


# ============================================================================
# Discovery Phase Implementation
# ============================================================================


def build_discovery_prompt(
    project_root: Path,
    goal: str | None = None,
    config: RalphConfig | None = None,
) -> str:
    """Build the system prompt for Discovery phase.

    Uses Jobs-to-be-Done (JTBD) framework to capture requirements.
    """
    config = config or load_config(project_root)

    prompt = f"""# Discovery Phase - Requirements Gathering

You are in the DISCOVERY phase of the Ralph development loop.

## Your Mission
Understand what the user wants to build by using the Jobs-to-be-Done framework.
Ask clarifying questions to fully understand:
- The functional situation: When [situation], I want to [motivation], so I can [expected outcome]
- Success criteria: How will we know when it's done?
- Constraints: Technical limitations, deadlines, existing code patterns
- Non-functional requirements: Performance, security, maintainability

## Project Context
- Project Root: {project_root}
- Project Name: {config.project.name}

"""

    if goal:
        prompt += f"""## Initial Goal
{goal}

"""

    prompt += """## Your Process
1. Read and understand the existing codebase structure
2. Ask the user clarifying questions (up to 10 questions)
3. Summarize the requirements in structured format
4. Output a clear requirements document

## Output Format
When you have gathered enough information, output a requirements summary:

```requirements
GOAL: <one-line project goal>

FUNCTIONAL REQUIREMENTS:
- FR1: <requirement>
- FR2: <requirement>
...

NON-FUNCTIONAL REQUIREMENTS:
- NFR1: <requirement>
...

CONSTRAINTS:
- C1: <constraint>
...

SUCCESS CRITERIA:
- SC1: <criterion>
...
```

## Important
- Ask ONE question at a time
- Explore edge cases and error handling
- Understand existing code patterns before suggesting new ones
- Do NOT write code in this phase - only gather requirements
"""

    return prompt


# ============================================================================
# Planning Phase Implementation
# ============================================================================


def build_planning_prompt(
    project_root: Path,
    config: RalphConfig | None = None,
) -> str:
    """Build the system prompt for Planning phase.

    Creates a dependency-aware implementation plan with sized tasks.
    """
    config = config or load_config(project_root)

    # Load MEMORY.md if it exists
    memory_path = project_root / "MEMORY.md"
    memory_content = ""
    if memory_path.exists():
        memory_content = memory_path.read_text()

    prompt = f"""# Planning Phase - Implementation Design

You are in the PLANNING phase of the Ralph development loop.

## Your Mission
Create a detailed implementation plan with tasks sized for single context windows.
Each task should be completable in approximately 30 minutes of focused work.

## Project Context
- Project Root: {project_root}
- Project Name: {config.project.name}

"""

    if memory_content:
        prompt += f"""## Requirements from Discovery Phase
{memory_content}

"""

    prompt += """## Planning Process
1. Analyze the codebase architecture
2. Identify gaps between current state and requirements
3. Break down work into discrete, testable tasks
4. Map dependencies between tasks
5. Estimate token usage for each task

## Task Sizing Guidelines
- Each task: ~30,000 tokens (roughly 30 min work)
- Include test writing in task scope
- One logical unit of change per task
- Clear verification criteria

## Output Format
Output tasks using ralph_add_task tool:

For each task, specify:
- id: Unique identifier (e.g., "auth-01", "api-02")
- description: Clear description of what to implement
- priority: 1 = highest priority, larger = lower
- dependencies: List of task IDs this depends on
- verification_criteria: How to verify completion

## Dependency Rules
- Tasks can only depend on previously defined tasks
- Avoid circular dependencies
- Keep dependency chains shallow when possible

## Important
- Focus on implementation order, not just logical grouping
- Consider test infrastructure setup as tasks
- Include documentation tasks if needed
- Do NOT implement - only plan
"""

    return prompt


# ============================================================================
# Building Phase Implementation
# ============================================================================


def build_building_prompt(
    project_root: Path,
    task: Task | None = None,
    config: RalphConfig | None = None,
) -> str:
    """Build the system prompt for Building phase.

    Executes tasks from the implementation plan with backpressure.
    """
    config = config or load_config(project_root)

    prompt = f"""# Building Phase - Implementation

You are in the BUILDING phase of the Ralph development loop.

## Your Mission
Implement the current task from the implementation plan.
Follow test-driven development and maintain code quality.

## Project Context
- Project Root: {project_root}
- Project Name: {config.project.name}
- Build Tool: {config.build.tool}
- Test Command: {config.build.test_command}
- Lint Command: {config.build.lint_command}
- Typecheck Command: {config.build.typecheck_command}

"""

    if task:
        prompt += f"""## Current Task
- ID: {task.id}
- Description: {task.description}
- Priority: {task.priority}
- Retry Count: {task.retry_count}

### Verification Criteria
"""
        for criterion in task.verification_criteria:
            prompt += f"- {criterion}\n"
        prompt += "\n"

        if task.dependencies:
            prompt += "### Dependencies (already completed)\n"
            for dep in task.dependencies:
                prompt += f"- {dep}\n"
            prompt += "\n"

    prompt += f"""## Development Process
1. Read and understand relevant existing code
2. Write tests first (TDD)
3. Implement the feature
4. Run backpressure commands: {', '.join(config.building.backpressure)}
5. Fix any issues
6. Mark task complete when verification criteria met

## Backpressure Commands
These commands MUST pass before marking task complete:
"""
    for cmd in config.building.backpressure:
        prompt += f"- `{cmd}`\n"

    prompt += """
## Important Rules
- Use ONLY `uv run` for Python commands (not pip, not venv)
- Git operations are READ-ONLY (no commit, push, merge)
- Run tests after EVERY change
- Keep changes focused on the current task
- Document any learnings with ralph_append_learning

## Completion
When the task is done:
1. Ensure all backpressure commands pass
2. Use ralph_mark_task_complete with notes
3. The loop will provide the next task
"""

    return prompt


# ============================================================================
# Validation Phase Implementation
# ============================================================================


def build_validation_prompt(
    project_root: Path,
    config: RalphConfig | None = None,
) -> str:
    """Build the system prompt for Validation phase.

    Verifies the implementation meets all requirements.
    """
    config = config or load_config(project_root)

    prompt = f"""# Validation Phase - Verification

You are in the VALIDATION phase of the Ralph development loop.

## Your Mission
Verify that all implemented tasks meet their requirements and the overall
project goals are achieved.

## Project Context
- Project Root: {project_root}
- Project Name: {config.project.name}

## Validation Checklist
1. All tests pass: `{config.build.test_command}`
2. Linting passes: `{config.build.lint_command}`
3. Type checking passes: `{config.build.typecheck_command}`
4. All tasks marked complete
5. Requirements from Discovery phase are met

## Validation Process
1. Run full test suite
2. Run linting
3. Run type checking
4. Review each completed task against its verification criteria
5. Check original requirements are satisfied
6. Document any gaps or issues found

## Output
Provide a validation report:

```validation
STATUS: PASS | FAIL | PARTIAL

TEST RESULTS:
- Total: X
- Passed: Y
- Failed: Z

LINT RESULTS:
- Errors: X
- Warnings: Y

TYPECHECK RESULTS:
- Errors: X

TASK VERIFICATION:
- task-1: PASS | FAIL - notes
- task-2: PASS | FAIL - notes
...

REQUIREMENTS CHECK:
- FR1: MET | NOT MET - notes
- FR2: MET | NOT MET - notes
...

ISSUES FOUND:
- Issue 1
- Issue 2
...

RECOMMENDATIONS:
- Recommendation 1
- Recommendation 2
...
```

## Important
- Be thorough but objective
- Report issues, don't fix them in this phase
- If issues found, loop may return to Building phase
"""

    return prompt


# ============================================================================
# Phase System Prompt Builder
# ============================================================================


def get_phase_prompt(
    phase: Phase,
    project_root: Path,
    task: Task | None = None,
    goal: str | None = None,
    config: RalphConfig | None = None,
) -> str:
    """Get the appropriate system prompt for a phase."""
    if phase == Phase.DISCOVERY:
        return build_discovery_prompt(project_root, goal, config)
    elif phase == Phase.PLANNING:
        return build_planning_prompt(project_root, config)
    elif phase == Phase.BUILDING:
        return build_building_prompt(project_root, task, config)
    elif phase == Phase.VALIDATION:
        return build_validation_prompt(project_root, config)
    else:
        raise ValueError(f"Unknown phase: {phase}")
