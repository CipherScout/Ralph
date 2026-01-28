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

        # Check circuit breaker
        should_halt, halt_reason = self.check_circuit_breaker()

        # Determine phase transition
        should_transition, next_phase = self._check_phase_transition()

        result = PhaseResult(
            success=not should_halt,
            phase=self.state.current_phase,
            tasks_completed=1 if task_completed else 0,
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
    Produces standardized outputs: PRD.md, SPEC-NNN-slug.md files, TECHNICAL_ARCHITECTURE.md.
    """
    config = config or load_config(project_root)

    prompt = f"""# Discovery Phase - Requirements Gathering

You are in the DISCOVERY phase of the Ralph development loop.

## CRITICAL: Ralph Memory System

**Memory from previous sessions is provided in the "Session Memory" section above.**

To save memory for future sessions:
- Use `mcp__ralph__ralph_update_memory` with your content
- Mode "replace" overwrites all memory
- Mode "append" adds to existing memory

**DO NOT use**:
- Read/Write/Edit tools for `.ralph/MEMORY.md` - the harness manages this
- External memory tools (Serena's read_memory/write_memory, etc.)

**RALPH TOOLS**: Use `mcp__ralph__*` tools for state management:
- `mcp__ralph__ralph_get_state_summary` - Get current state
- `mcp__ralph__ralph_validate_discovery_outputs` - Validate required documents exist
- `mcp__ralph__ralph_signal_discovery_complete` - Signal phase completion
- `mcp__ralph__ralph_update_memory` - Save memory for future sessions

## Project Context
- Project Root: {project_root}
- Project Name: {config.project.name}

"""

    if goal:
        prompt += f"""## Initial Goal
{goal}

"""

    prompt += """## REQUIRED OUTPUTS - Non-Negotiable

Discovery phase MUST produce these EXACT files before signaling completion:

### 1. specs/PRD.md - Product Requirements Document

The master document containing business logic, rules, constraints, and objectives.
**MUST** reference all SPEC files in a JTBD table.

```markdown
# Product Requirements Document: {{Project Name}}

## Overview
{{High-level summary of what is being built and why}}

## Business Context
- **Problem Statement**: {{What problem does this solve?}}
- **Target Users**: {{Who will use this?}}
- **Success Metrics**: {{How do we measure success?}}

## Jobs to Be Done

| Job ID | Description | Spec File |
|--------|-------------|-----------|
| JTBD-001 | {{job description}} | [SPEC-001-slug](./SPEC-001-slug.md) |
| JTBD-002 | {{job description}} | [SPEC-002-slug](./SPEC-002-slug.md) |

## Business Rules
1. {{Critical business logic rule}}

## Global Constraints
- **Technical**: {{Technology requirements}}
- **Timeline**: {{Deadline constraints}}

## Non-Goals (Explicit Exclusions)
- {{What we will NOT build}}

## References
- [TECHNICAL_ARCHITECTURE.md](./TECHNICAL_ARCHITECTURE.md)
```

### 2. specs/SPEC-NNN-slug.md - Individual Specifications

One file per Job-to-Be-Done discovered:
- NNN = 3-digit number (001, 002, 003, etc.)
- slug = kebab-case description (auth, user-profile, payment-flow)
- Example: `specs/SPEC-001-user-authentication.md`

```markdown
# SPEC-{{NNN}}: {{Title}}

**JTBD**: When {{situation}}, I want to {{motivation}}, so I can {{expected outcome}}

## Problem Statement
{{Clear description of what problem this specification addresses}}

## Functional Requirements
1. {{Requirement 1}}
2. {{Requirement 2}}

## User Stories
- As a {{role}}, I want {{feature}} so that {{benefit}}

## Success Criteria
- [ ] {{Measurable outcome 1}}
- [ ] {{Measurable outcome 2}}

## Acceptance Criteria
- [ ] {{Testable criterion 1}}
- [ ] {{Testable criterion 2}}

## Constraints
- {{Limitation or boundary}}

## Edge Cases
- {{Edge case}}: {{How to handle it}}

## Dependencies
- **Depends on**: {{Other SPEC files or "None"}}
- **Required by**: {{Dependent SPEC files or "None"}}
```

### 3. specs/TECHNICAL_ARCHITECTURE.md - High-Level Architecture

System design document (Planning phase will add detailed specifications).

```markdown
# Technical Architecture (Discovery Phase)

## System Overview
{{High-level description of the system being built}}

## Technology Stack
- **Language**: {{e.g., Python 3.11+}}
- **Framework**: {{e.g., FastAPI}}
- **Database**: {{e.g., PostgreSQL}}

## Integration Points
- {{External API}}: {{Purpose}}

## Security Considerations
- **Authentication**: {{Approach}}
- **Authorization**: {{Model}}

## Performance Requirements
- **Latency**: {{Targets}}
- **Throughput**: {{Expected load}}

---
*Planning phase will add detailed architecture below this line.*
```

## Your Mission

Transform the user's intent into the three required documents through interactive conversation
using the Jobs-to-be-Done (JTBD) framework.

## Your Process

1. **Review Session Memory** above for previous context
2. **Check specs/ directory** for existing requirement documents
3. **Identify Jobs to Be Done** - Ask clarifying questions to understand:
   - The functional situation: When [situation], I want to [motivation], so I can [expected outcome]
   - Success criteria: How will we know when it's done?
   - Constraints: Technical limitations, deadlines, existing code patterns
4. **Create SPEC files** - One SPEC-NNN-slug.md per JTBD
5. **Create PRD.md** - Master document with JTBD table referencing all SPEC files
6. **Create TECHNICAL_ARCHITECTURE.md** - High-level architecture decisions
7. **Validate outputs** - Call ralph_validate_discovery_outputs
8. **Signal completion** - Call ralph_signal_discovery_complete

## Important

- Ask ONE question at a time using AskUserQuestion tool
- Explore edge cases and error handling
- Understand existing code patterns before suggesting new ones
- Do NOT write code in this phase - only gather requirements
- PRD.md is the master document - it must reference all SPEC files
- DO NOT signal completion until ALL THREE document types exist

## Completion Protocol

Before signaling completion:
1. Verify specs/PRD.md exists with populated JTBD table
2. Verify at least one specs/SPEC-NNN-*.md file exists
3. Verify specs/TECHNICAL_ARCHITECTURE.md exists
4. Call ralph_validate_discovery_outputs to confirm
5. Call ralph_signal_discovery_complete with:
   - summary: Brief summary of requirements gathered
   - specs_created: List of SPEC files (e.g., ["SPEC-001-auth.md"])
   - prd_created: true
   - architecture_created: true
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

    prompt = f"""# Planning Phase - Implementation Design

You are in the PLANNING phase of the Ralph development loop.

## CRITICAL: Ralph Memory System

**Memory from previous sessions is provided in the "Session Memory" section above.**

To save memory for future sessions:
- Use `mcp__ralph__ralph_update_memory` with your content
- Mode "replace" overwrites all memory
- Mode "append" adds to existing memory

**DO NOT use**:
- Read/Write/Edit tools for `.ralph/MEMORY.md` - the harness manages this
- External memory tools (Serena's read_memory/write_memory, etc.)

## Your Mission
Create a detailed implementation plan with tasks sized for single context windows.
Each task should be completable in approximately 30 minutes of focused work.

## Project Context
- Project Root: {project_root}
- Project Name: {config.project.name}

"""

    prompt += """## Expected Discovery Outputs

The Discovery phase produced these standardized documents:

1. **specs/PRD.md** - Master Product Requirements Document
   - Contains business context, JTBD table, business rules, constraints
   - Read this FIRST for an overview of all jobs-to-be-done

2. **specs/SPEC-NNN-slug.md** - Individual specifications
   - One file per job-to-be-done (e.g., SPEC-001-auth.md)
   - Contains detailed requirements, acceptance criteria, dependencies

3. **specs/TECHNICAL_ARCHITECTURE.md** - High-level architecture
   - Contains system overview, tech stack, integration points
   - **Your task**: Enhance this with detailed architecture

## Planning Process

1. **Read specs/PRD.md FIRST** - Get overview of all jobs and business context
2. **Read specs/TECHNICAL_ARCHITECTURE.md** - Understand high-level design
3. **Read each SPEC file** - Study all specs/SPEC-NNN-*.md files
4. **Enhance architecture** - Add detailed specs to TECHNICAL_ARCHITECTURE.md
5. **Break down work** into discrete, testable tasks
6. **Use ralph_add_task** to add each task to the plan

## Architecture Enhancement

Update specs/TECHNICAL_ARCHITECTURE.md with detailed specifications.
Add your detailed content BELOW the existing high-level architecture:

```markdown
---
## Detailed Architecture (Added in Planning Phase)

### API Specifications
[Endpoint definitions]

### Database Schema
[Schema design]

### Component Interactions
[Diagrams and descriptions]
```

## Task Sizing Guidelines

- Each task: ~30,000 tokens (roughly 30 min work)
- Include test writing in task scope
- One logical unit of change per task
- Clear verification criteria

## Output Format

Use the ralph_add_task MCP tool for each task:

For each task, specify:
- id: Unique identifier (e.g., "auth-01", "api-02")
- description: Clear description of what to implement
- priority: 1 = highest priority, larger = lower
- dependencies: List of task IDs this depends on
- verification_criteria: How to verify completion
- spec_files: List of relevant spec files (e.g., ["specs/SPEC-001-auth.md", "specs/PRD.md"])

## Spec File References

**Every task should reference at least one spec file.** This helps the building phase agent
understand the requirements:
- Use relative paths from project root (e.g., "specs/SPEC-001-auth.md")
- Reference the SPEC file(s) most relevant to each task
- Include PRD.md if the task relates to overall product requirements

## Dependency Rules

- Tasks can only depend on previously defined tasks
- Avoid circular dependencies
- Keep dependency chains shallow when possible

## Important

- Focus on implementation order, not just logical grouping
- Consider test infrastructure setup as tasks
- Include documentation tasks if needed
- Do NOT implement - only plan
- When done, call ralph_signal_planning_complete
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

## CRITICAL: Ralph Memory System

**Session Memory is provided above.** To save learnings for future sessions:
- Use `mcp__ralph__ralph_update_memory` to save important context

**DO NOT use**: Read/Write/Edit for `.ralph/MEMORY.md`, or external memory tools.

## Your Mission
Implement the current task from the implementation plan.
Follow test-driven development and maintain code quality.

## Foundational Documents (REVIEW FIRST)
Before starting any task, review these key documents for context:
- `specs/PRD.md` - Product requirements and overall goals
- `specs/TECHNICAL_ARCHITECTURE.md` - Architecture decisions and patterns

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

        if task.spec_files:
            prompt += "### Spec Files (READ THESE FIRST)\n"
            prompt += "Before implementing, read these specification files for requirements:\n"
            for spec in task.spec_files:
                prompt += f"- {spec}\n"
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

## CRITICAL: Ralph Memory System

**Session Memory is provided above.** To save validation notes:
- Use `mcp__ralph__ralph_update_memory` to save context for next session

**DO NOT use**: Read/Write/Edit for `.ralph/MEMORY.md`, or external memory tools.

## Your Mission
Verify that all implemented tasks meet their requirements and the overall
project goals are achieved.

## Foundational Documents (REVIEW FIRST)
Before validating, review these key documents to understand what was planned:
- `specs/PRD.md` - Product requirements and success criteria
- `specs/TECHNICAL_ARCHITECTURE.md` - Architecture decisions and constraints
- `specs/SPEC-*.md` - Individual feature specifications

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
