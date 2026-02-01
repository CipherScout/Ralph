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

## First Steps

**ALWAYS do these steps first in every iteration:**

1. **Review Session Memory** - Check the memory section above for previous context.
2. **Check specs/ directory** - List what spec files already exist so you don't duplicate work.

## Project Context
- **Project Root**: {project_root}
- **Project Name**: {config.project.name}

"""

    if goal:
        prompt += f"""## Goal
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

## Research Notes
- **Similar solutions found**: {{Links and summaries from web research}}
- **Library/API recommendations**: {{Based on compatibility research}}
- **Known pitfalls**: {{Issues found during research about this feature type}}
- **Reference documentation**: {{Key doc pages discovered}}
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

## Process

### 1. Identify Jobs to Be Done
- What outcomes does the user need?
- What problems are they trying to solve?
- What capabilities do they want to add?

### 2. Research and Validate (MANDATORY)

Before writing any SPEC file, you MUST perform targeted research:

1. **Similar solutions**: Use `WebSearch` to find how similar problems are solved
   - Search: "best practices for [feature type] implementation"
   - Search: "[technology] [feature] patterns"
2. **Technology validation**: Verify library/framework compatibility
   - Search: "[library] production readiness"
   - Use `WebFetch` to read official docs for any external APIs or libraries
3. **Existing patterns**: Search the codebase FIRST (`Grep`, `Glob`), THEN search the web

Each SPEC file MUST include a "## Research Notes" section documenting what you found.

**DO NOT** write a SPEC file without first researching the problem domain.

### 3. For Each JTBD, Create a SPEC File
- One SPEC-NNN-slug.md per job
- Use sequential numbering (001, 002, 003)
- Include all required sections including Research Notes

### 4. Ask Clarifying Questions
Use the `AskUserQuestion` tool to clarify:
- Ambiguous requirements
- Priority decisions
- Technical constraints
- Integration points

### 5. Create the PRD
After gathering requirements and creating SPEC files:
- Write specs/PRD.md with the JTBD table
- Ensure every SPEC file is referenced in the table
- Include business rules and constraints

### 6. Create the Architecture Document
- Write specs/TECHNICAL_ARCHITECTURE.md
- Focus on high-level design decisions
- Leave room for Planning phase to add details

## Tools Available

### Research
- `Read` - Read existing code and documentation
- `Glob` - Find files by pattern
- `Grep` - Search file contents
- `WebSearch` - Search the web for best practices, patterns, and solutions
- `WebFetch` - Fetch and analyze web pages, read API documentation
- `Bash` - Run commands for exploration

### Writing
- `Write` - Create spec files in specs/
- `Edit` - Modify existing files

### Interaction
- `AskUserQuestion` - Ask clarifying questions with structured options
- `Task` - Delegate research subtasks to subagents

### Ralph State Tools
- `mcp__ralph__ralph_get_state_summary` - Get current state
- `mcp__ralph__ralph_validate_discovery_outputs` - Validate required documents exist
- `mcp__ralph__ralph_signal_discovery_complete` - Signal when discovery is done
- `mcp__ralph__ralph_update_memory` - Save context for future sessions

## Critical Rules

### Git is READ-ONLY
```
ALLOWED: git status, git diff, git log, git show
BLOCKED: git commit, git push, git merge, git rebase
```

### No Implementation Code
- Do NOT write implementation code in this phase
- Only gather requirements and create specification documents

## Completion Protocol

**CRITICAL**: Before signaling completion, verify ALL required documents exist:

### Pre-Completion Checklist
- [ ] `specs/PRD.md` exists with populated JTBD table
- [ ] At least one `specs/SPEC-NNN-*.md` file exists
- [ ] `specs/TECHNICAL_ARCHITECTURE.md` exists
- [ ] PRD.md JTBD table references ALL SPEC files created
- [ ] All SPEC files have all required sections filled (including Research Notes)

### Validation
Call `mcp__ralph__ralph_validate_discovery_outputs` to verify documents exist.

### Signal Completion
Only after validation passes, call `mcp__ralph__ralph_signal_discovery_complete` with:
- `summary`: Brief summary of requirements gathered
- `specs_created`: List of SPEC files created (e.g., ["SPEC-001-auth.md", "SPEC-002-sync.md"])
- `prd_created`: true
- `architecture_created`: true

**DO NOT signal completion until ALL THREE document types exist.**

## Avoiding Repetition

- Do NOT re-ask questions that were already answered (check Session Memory)
- Do NOT re-create specs that already exist (check specs/ directory)
- Do NOT re-read the same files multiple times
- If requirements are already captured, signal completion
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

## First Steps

**ALWAYS do these steps first in every iteration:**

1. **Review Session Memory** - Check the memory section above for previous context.
2. **Read specs/PRD.md FIRST** - Get overview of all jobs-to-be-done and business context.
3. **Read specs/TECHNICAL_ARCHITECTURE.md** - Understand the high-level system design.
4. **Read each SPEC file** - Study specs/SPEC-NNN-*.md files referenced in PRD.md.
5. **Check current plan** - Use `mcp__ralph__ralph_get_plan_summary` to see existing tasks.

## Project Context
- **Project Root**: {project_root}
- **Project Name**: {config.project.name}
- **Specs Directory**: {project_root / 'specs'}

## Your Mission

Perform gap analysis between specifications and existing code, producing a prioritized
implementation plan with properly-sized tasks.

## CRITICAL CONSTRAINT

**NO IMPLEMENTATION ALLOWED** - This is a planning-only phase. Do not write any implementation code.

## Expected Discovery Outputs

The Discovery phase produced these standardized documents:

1. **specs/PRD.md** - Master Product Requirements Document
   - Contains business context, JTBD table, business rules, constraints
   - Read this FIRST for an overview of all jobs-to-be-done
   - The JTBD table references all SPEC files

2. **specs/SPEC-NNN-slug.md** - Individual specifications
   - One file per job-to-be-done (e.g., SPEC-001-auth.md)
   - Contains detailed requirements, acceptance criteria, dependencies
   - Includes Research Notes with findings from discovery research

3. **specs/TECHNICAL_ARCHITECTURE.md** - High-level architecture
   - Contains system overview, tech stack, integration points
   - **Your task**: Enhance this document with detailed architecture

## Process

### 1. Orient - Study Specifications
Use subagents to study each spec in `specs/`:
- Understand requirements and success criteria
- Identify acceptance criteria
- Note constraints and non-goals
- Review Research Notes for library/pattern recommendations

### 2. Analyze - Study Existing Code
Use subagents to study the existing codebase:
- Understand current architecture
- Identify existing patterns and conventions
- Find reusable components
- Use Bash to explore structure if needed

### 3. Research-Informed Gap Analysis (MANDATORY)

For each gap between specs and current code, you MUST research before creating tasks:

1. **Implementation approach**: Use `WebSearch` to find recommended patterns
   - "How to implement [feature] in [framework]"
   - "[pattern] best practices [language]"
2. **Library selection**: Validate library choices via `WebFetch` on official docs
   - Check version compatibility with current dependencies
   - Read getting-started guides for unfamiliar libraries
3. **Architecture patterns**: Research applicable patterns
   - "[architecture pattern] for [use case]"
   - "[database/API/auth] design patterns [framework]"

**Embed findings in task descriptions** so the building agent doesn't need to re-research.

### 4. Enhance Technical Architecture

Update specs/TECHNICAL_ARCHITECTURE.md with detailed specifications:
- API endpoint definitions
- Database schema design
- Component interaction diagrams
- Sequence diagrams for key flows

Add your detailed architecture BELOW the existing high-level content, marked with:

```markdown
---
## Detailed Architecture (Added in Planning Phase)
```

### 5. Create Implementation Plan

Write tasks using the `mcp__ralph__ralph_add_task` tool.

#### Task Sizing Rules

**GOOD** - Single context window (~30 min work):
- "Add database column and migration for user.email_verified"
- "Create UserProfile React component with props interface"
- "Implement password reset endpoint with validation"

**TOO BIG** - Split into 5-10 tasks:
- "Build entire authentication system"
- "Implement full API layer"
- "Create complete admin dashboard"

#### Task Description Best Practices

Each task description MUST answer:
1. **What** to implement (feature/component/endpoint)
2. **Where** in the codebase (specific files to create/modify)
3. **How** to approach (pattern to follow, library to use, existing code to reference)
4. **Why** this approach (relevant architecture decisions from TECHNICAL_ARCHITECTURE.md)

**BAD**: "Implement user authentication"
**GOOD**: "Create JWT auth middleware in src/middleware/auth.py following the existing
RequestValidator pattern. Use python-jose for token handling (see SPEC-001 Research Notes).
Modify src/routes/auth.py to add /login and /refresh endpoints. Tests in tests/test_auth.py."

#### Task Format
```json
{{{{
  "id": "unique-task-id",
  "description": "Clear, actionable description with WHERE and HOW",
  "priority": 1,
  "dependencies": ["other-task-id"],
  "verification_criteria": [
    "{config.build.test_command} tests/test_feature.py",
    "endpoint returns 200 on valid input"
  ],
  "spec_files": ["specs/SPEC-001-auth.md"],
  "estimated_tokens": 30000
}}}}
```

### 6. Prioritize Tasks

Order tasks by:
1. Critical path dependencies
2. Risk (harder tasks earlier)
3. Value delivery (user-facing features)

## Tools Available

### Research
- `Read` - Read specs and existing code
- `Glob` - Find files by pattern
- `Grep` - Search file contents
- `WebSearch` - Research implementation patterns and solutions
- `WebFetch` - Read library documentation and API references
- `Bash` - Run exploration commands

### Planning
- `Write` - Create planning documents
- `Edit` - Modify existing files (e.g., enhance TECHNICAL_ARCHITECTURE.md)
- `Task` - Parallel analysis via subagents

### Ralph State Tools
- `mcp__ralph__ralph_add_task` - Add a task to the implementation plan
- `mcp__ralph__ralph_get_plan_summary` - Get current plan status
- `mcp__ralph__ralph_get_state_summary` - Get current state
- `mcp__ralph__ralph_signal_planning_complete` - Signal when planning is done
- `mcp__ralph__ralph_update_memory` - Save context for future sessions

## Critical Rules

### No Implementation
- Do NOT write implementation code
- Do NOT create new source files
- Do NOT modify existing code
- Planning documents and task definitions ONLY

### Git is READ-ONLY
```
ALLOWED: git status, git diff, git log, git show
BLOCKED: git commit, git push, git merge, git rebase
```

## Completion Protocol

**IMPORTANT**: When planning is complete, you MUST:

1. All specs have been analyzed
2. All tasks have been created with:
   - Clear descriptions (answering what/where/how/why)
   - Proper dependencies
   - Verification criteria using project commands
   - References to relevant spec files
3. Tasks are prioritized
4. Use `ralph_update_memory` to save planning summary
5. **Call `mcp__ralph__ralph_signal_planning_complete`** with:
   - `summary`: Brief summary of the plan
   - `task_count`: Number of tasks created

DO NOT just say "planning complete" in text - USE THE TOOL to signal completion.

## Avoiding Repetition

- Do NOT create duplicate tasks (check existing plan first)
- Do NOT re-read the same files multiple times
- If plan already covers all specs, signal completion

## Notes

- Plan regeneration is cheap - don't patch a bad plan, regenerate it
- One task = one testable unit of work
- Include verification criteria for every task
- Dependencies should form a DAG (no cycles)
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
    Includes spec previews, dependency context, research guidance,
    and config-driven command references.
    """
    config = config or load_config(project_root)

    prompt = f"""# Building Phase - Implementation

You are in the BUILDING phase of the Ralph development loop.

## CRITICAL: Ralph Memory System

**Session Memory is provided above.** To save learnings for future sessions:
- Use `mcp__ralph__ralph_update_memory` to save important context
- Mode "replace" overwrites all memory
- Mode "append" adds to existing memory

**DO NOT use**: Read/Write/Edit for `.ralph/MEMORY.md`, or external memory tools.

## First Steps

**ALWAYS do these steps first in every iteration:**

1. **Review Session Memory** - Check the memory section above for previous context.
2. **Check current task** - Use `mcp__ralph__ralph_get_next_task` to confirm your assignment.
3. **Read specs** - Review `specs/PRD.md` and `specs/TECHNICAL_ARCHITECTURE.md` for context.
4. **Understand existing code** - Read relevant files before making any changes.

## Project Context
- **Project Root**: {project_root}
- **Project Name**: {config.project.name}
- **Build Tool**: `{config.build.tool}`
- **Test Command**: `{config.build.test_command}`
- **Lint Command**: `{config.build.lint_command}`
- **Typecheck Command**: `{config.build.typecheck_command}`

"""

    # --- Current Task Details ---
    if task:
        prompt += f"""## Current Task
- **ID**: {task.id}
- **Description**: {task.description}
- **Priority**: {task.priority}
- **Retry Count**: {task.retry_count}

### Verification Criteria
"""
        for criterion in task.verification_criteria:
            prompt += f"- {criterion}\n"
        prompt += "\n"

        # Change 4b: Show completed dependency context with notes
        if task.dependencies:
            prompt += "### Completed Dependencies\n"
            prompt += "These tasks are done — build on top of their work:\n"
            try:
                plan = load_plan(project_root)
                for dep_id in task.dependencies:
                    dep_task = next(
                        (t for t in plan.tasks if t.id == dep_id), None
                    )
                    if dep_task and dep_task.completion_notes:
                        prompt += (
                            f"- **{dep_id}**: {dep_task.description[:80]}"
                            f" — _{dep_task.completion_notes}_\n"
                        )
                    elif dep_task:
                        prompt += f"- **{dep_id}**: {dep_task.description[:80]}\n"
                    else:
                        prompt += f"- {dep_id}\n"
            except Exception:
                for dep in task.dependencies:
                    prompt += f"- {dep}\n"
            prompt += "\n"

        # Change 4a: Include spec file previews
        if task.spec_files:
            prompt += "### Spec Files (READ THESE FOR REQUIREMENTS)\n"
            prompt += "These specs define what you're implementing:\n"
            for spec in task.spec_files:
                spec_path = project_root / spec
                if spec_path.exists():
                    try:
                        content = spec_path.read_text()[:500]
                        first_section = content.split("\n\n")[0] if "\n\n" in content else content
                        prompt += f"\n**{spec}** (preview):\n```\n{first_section}\n```\n"
                    except Exception:
                        prompt += f"- {spec}\n"
                else:
                    prompt += f"- {spec}\n"
            prompt += "\n"

    # --- Development Process ---
    prompt += f"""## Development Process

### 1. Understand Before Coding
- Read the relevant existing code first
- Understand patterns and conventions in the codebase
- Check for existing similar implementations to follow
- Review related specs in `specs/` directory

### 2. Test-Driven Development
```
1. Write failing test(s) for the feature
2. Run tests to confirm they fail: `{config.build.test_command}`
3. Implement minimal code to pass
4. Refactor while tests stay green
5. Repeat
```

### 3. Run Backpressure Commands
Before marking task complete, ALL must pass:
"""
    for cmd in config.building.backpressure:
        prompt += f"- `{cmd}`\n"

    prompt += f"""
### 4. Quality Checklist
Before marking complete, verify:
- [ ] Tests written and passing (`{config.build.test_command}`)
- [ ] Linting passes (`{config.build.lint_command}`)
- [ ] Type checking passes (`{config.build.typecheck_command}`)
- [ ] Code follows project conventions
- [ ] No debug code or print statements left behind
- [ ] Error handling is appropriate

## Research Guidance

You SHOULD use research to work more effectively:

- **Before implementing unfamiliar APIs**: Use `WebSearch` + `WebFetch` to read documentation
- **When encountering errors**: Search the error message before spending multiple attempts
  - `WebSearch "[library] [error message]"` often finds the solution immediately
- **When choosing patterns**: Search for best practices specific to the framework
- **Before marking blocked**: Search for at least 2-3 potential solutions online first

Research saves time — a quick web search often prevents extended trial-and-error.

## Tools Available

### Research
- `Read` - Read file contents, specs, and existing code
- `Glob` - Find files by pattern
- `Grep` - Search file contents
- `WebSearch` - Search for solutions, docs, and error fixes
- `WebFetch` - Read library documentation and API references

### Write/Edit
- `Write` - Create new files
- `Edit` - Modify existing files

### Execute
- `Bash` - Run shell commands (use `{config.build.tool}` prefix for project commands)
- `Task` - Delegate subtasks to subagents

### Ralph State Tools
- `mcp__ralph__ralph_get_next_task` - Get next available task
- `mcp__ralph__ralph_mark_task_complete` - Mark current task done
- `mcp__ralph__ralph_mark_task_blocked` - Mark task as blocked
- `mcp__ralph__ralph_get_plan_summary` - Get current plan status
- `mcp__ralph__ralph_signal_building_complete` - Signal when all building is done
- `mcp__ralph__ralph_update_memory` - Save context for future sessions

## Critical Rules

### Build Tool
All project commands must use `{config.build.tool}`:
```
Tests: {config.build.test_command}
Linting: {config.build.lint_command}
Type check: {config.build.typecheck_command}
```

### Git is READ-ONLY
```
ALLOWED: git status, git diff, git log, git show
BLOCKED: git commit, git push, git merge, git rebase
```

## Completion Protocol

**IMPORTANT**: When task is complete, you MUST:

1. Run all backpressure commands:
"""
    for cmd in config.building.backpressure:
        prompt += f"   - `{cmd}`\n"

    prompt += """2. Verify ALL pass
3. **Call `mcp__ralph__ralph_mark_task_complete`** with:
   - `task_id`: The current task ID
   - `notes`: Brief completion summary
   - `tokens_used`: Approximate tokens used

### If Task is Blocked

Before marking blocked, you MUST:
1. Search for the error message online (`WebSearch`)
2. Try at least 2-3 alternative approaches
3. Check if a dependency is missing or broken

If still blocked after research, call `mcp__ralph__ralph_mark_task_blocked` with:
- `task_id`: Current task ID
- `reason`: Clear explanation of what's blocking progress and what you tried

### When All Tasks Complete

When the implementation plan is fully complete:
1. Use `ralph_update_memory` to save a summary of what was built
2. **Call `mcp__ralph__ralph_signal_building_complete`** with:
   - `summary`: Brief summary of what was built
   - `tasks_completed`: Number of tasks completed

DO NOT just say "building complete" in text - USE THE TOOL to signal completion.

## Avoiding Repetition

- Do NOT re-implement tasks that are already complete (check plan status)
- Do NOT re-read the same files multiple times in one session
- Do NOT run tests repeatedly without making changes between runs
- If encountering the same error 3+ times, mark task as blocked (after researching)
- Check Session Memory before re-asking questions already answered

## Notes

- One task = one testable unit of work
- TDD is mandatory — write tests first
- Record learnings for future sessions via `mcp__ralph__ralph_update_memory`
- If stuck after 3 attempts, mark task blocked
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

    Verifies the implementation meets all requirements with security
    and quality research guidance.
    """
    config = config or load_config(project_root)

    prompt = f"""# Validation Phase - Verification

You are in the VALIDATION phase of the Ralph development loop.

## CRITICAL: Ralph Memory System

**Session Memory is provided above.** To save validation notes:
- Use `mcp__ralph__ralph_update_memory` to save context for next session
- Mode "replace" overwrites all memory
- Mode "append" adds to existing memory

**DO NOT use**: Read/Write/Edit for `.ralph/MEMORY.md`, or external memory tools.

## First Steps

**ALWAYS do these steps first:**

1. **Review Session Memory** - Check the memory section above for previous context.
2. **Read specs/PRD.md** - Understand requirements and success criteria.
3. **Read specs/TECHNICAL_ARCHITECTURE.md** - Understand architecture decisions.
4. **Check plan status** - Use `mcp__ralph__ralph_get_plan_summary` to see completed tasks.

## Project Context
- **Project Root**: {project_root}
- **Project Name**: {config.project.name}
- **Build Tool**: `{config.build.tool}`
- **Test Command**: `{config.build.test_command}`
- **Lint Command**: `{config.build.lint_command}`
- **Typecheck Command**: `{config.build.typecheck_command}`

## Your Mission

Verify that all implemented tasks meet their requirements and the overall
project goals are achieved. Report findings objectively — do NOT fix issues
in this phase.

## Validation Process

### 1. Automated Quality Checks
Run ALL of these and record results:
- `{config.build.test_command}` — Full test suite
- `{config.build.lint_command}` — Linting
- `{config.build.typecheck_command}` — Type checking

### 2. Task Verification
For each completed task in the implementation plan:
- Read the task's verification criteria
- Confirm each criterion is met
- Check that tests cover the feature
- Verify the implementation matches the spec

### 3. Requirements Traceability
Cross-check against discovery outputs:
- Read `specs/PRD.md` — verify each requirement is addressed
- Read `specs/SPEC-*.md` — verify acceptance criteria are met
- Check that all JTBD (Jobs-to-Be-Done) from the PRD have implementations

### 4. Code Quality Review
- Check for debug code, print statements, or TODO comments left behind
- Verify error handling is appropriate (not swallowing errors)
- Confirm no hardcoded secrets, credentials, or test data in source
- Check that new code follows existing project conventions

## Security & Quality Research

You SHOULD check for known issues:
- Search: "[dependency name] CVE" for major dependencies added during building
- Search: "common [framework] security mistakes" for the project's tech stack
- Search: "OWASP top 10 [language] checklist" for applicable security checks
- Document any findings in the validation report

## Validation Checklist

- [ ] All tests pass: `{config.build.test_command}`
- [ ] Linting passes: `{config.build.lint_command}`
- [ ] Type checking passes: `{config.build.typecheck_command}`
- [ ] All tasks marked complete in plan
- [ ] Each task's verification criteria are met
- [ ] Requirements from specs/PRD.md are satisfied
- [ ] Acceptance criteria from specs/SPEC-*.md are met
- [ ] No security issues found (or documented if found)
- [ ] Code quality is consistent with project conventions

## Output

Provide a validation report in this format:

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
- Requirement 1: MET | NOT MET - notes
- Requirement 2: MET | NOT MET - notes
...

SECURITY CHECK:
- Dependency audit: notes
- OWASP checks: notes
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

## Tools Available

### Research
- `Read` - Read specs, code, and implementation files
- `Glob` - Find files by pattern
- `Grep` - Search file contents
- `WebSearch` - Search for security advisories, best practices
- `WebFetch` - Read security checklists and documentation

### Execute
- `Bash` - Run validation commands (use `{config.build.tool}` prefix)
- `Task` - Delegate verification subtasks to subagents

### Ralph State Tools
- `mcp__ralph__ralph_get_plan_summary` - Get current plan status
- `mcp__ralph__ralph_get_state_summary` - Get current state
- `mcp__ralph__ralph_signal_validation_complete` - Signal validation done
- `mcp__ralph__ralph_update_memory` - Save context for future sessions

## Critical Rules

### No Implementation Changes
- Do NOT write or modify implementation code
- Do NOT fix bugs — only document them
- If issues are found, the loop will return to Building phase
- Validation documents and reports ONLY

### Git is READ-ONLY
```
ALLOWED: git status, git diff, git log, git show
BLOCKED: git commit, git push, git merge, git rebase
```

## Completion Protocol

**IMPORTANT**: When validation is complete, you MUST:

1. Run ALL automated checks:
   - `{config.build.test_command}`
   - `{config.build.lint_command}`
   - `{config.build.typecheck_command}`
2. Complete the validation checklist above
3. Generate the validation report
4. Use `ralph_update_memory` to save validation findings
5. **Call `mcp__ralph__ralph_signal_validation_complete`** with:
   - `status`: "pass", "fail", or "partial"
   - `summary`: Brief summary of validation results
   - `issues`: List of issues found (if any)

DO NOT just say "validation complete" in text - USE THE TOOL to signal completion.

## Avoiding Repetition

- Do NOT re-run the same command without a reason
- Do NOT re-read the same files multiple times
- If all checks pass on first run, proceed to completion
- Check Session Memory before re-doing work from a previous session

## Notes

- Be thorough but objective — report facts, not opinions
- If issues are found, the loop returns to Building phase automatically
- Focus on what matters: correctness, security, quality
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
