"""Context window management and hand-off protocol for Ralph.

Handles context budget tracking, session hand-offs, and
MEMORY.md generation for session continuity.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ralph.models import ImplementationPlan, Phase, RalphState, TaskStatus

# Default limits (can be overridden via config)
DEFAULT_MAX_FILES_IN_MEMORY = 10
DEFAULT_MAX_SESSION_HISTORY = 50

# Configure logger for context module
logger = logging.getLogger(__name__)


@dataclass
class SessionArchive:
    """Archive of a completed session."""

    session_id: str
    iteration: int
    started_at: datetime
    ended_at: datetime
    tokens_used: int
    cost_usd: float
    tasks_completed: int
    phase: Phase
    handoff_reason: str
    summary_path: str | None = None


@dataclass
class ContextInjection:
    """Injection of context into the next iteration."""

    timestamp: datetime
    content: str
    source: str  # user, system, test_failure, etc.
    priority: int = 0  # Higher priority = included first


@dataclass
class IterationContext:
    """Context assembled for a single iteration.

    Contains all the information needed for the LLM to
    continue work in a fresh context window.
    """

    # Current state
    iteration: int
    phase: Phase
    session_id: str | None

    # Task information
    current_task: dict[str, Any] | None
    completed_tasks_this_session: int
    total_completed_tasks: int
    total_pending_tasks: int

    # Memory from previous sessions
    memory_content: str | None

    # Injections (user guidance, test failures, etc.)
    injections: list[ContextInjection]

    # Token budget
    remaining_tokens: int
    usage_percentage: float


def load_memory_file(project_root: Path) -> str | None:
    """Load .ralph/MEMORY.md content if it exists.

    Args:
        project_root: Path to project root

    Returns:
        Memory content or None if file doesn't exist
    """
    memory_path = project_root / ".ralph" / "MEMORY.md"
    if memory_path.exists():
        return memory_path.read_text()
    return None


def load_injections(project_root: Path) -> list[ContextInjection]:
    """Load pending context injections.

    Args:
        project_root: Path to project root

    Returns:
        List of context injections
    """
    injection_path = project_root / ".ralph" / "injections.json"
    if not injection_path.exists():
        return []

    injections = []
    try:
        with open(injection_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                injections.append(
                    ContextInjection(
                        timestamp=datetime.fromisoformat(data["timestamp"]),
                        content=data["content"],
                        source=data.get("source", "user"),
                        priority=data.get("priority", 0),
                    )
                )
    except json.JSONDecodeError as e:
        logger.warning(f"Corrupted injections file at {injection_path}: {e}")
    except KeyError as e:
        logger.warning(f"Missing required field in injections file: {e}")

    # Sort by priority (descending) then timestamp
    injections.sort(key=lambda x: (-x.priority, x.timestamp))
    return injections


def clear_injections(project_root: Path) -> None:
    """Clear pending injections after they've been processed.

    Args:
        project_root: Path to project root
    """
    injection_path = project_root / ".ralph" / "injections.json"
    if injection_path.exists():
        injection_path.unlink()


def add_injection(
    project_root: Path,
    content: str,
    source: str = "user",
    priority: int = 0,
) -> None:
    """Add an injection for the next iteration.

    Args:
        project_root: Path to project root
        content: Content to inject
        source: Source of the injection
        priority: Priority (higher = included first)
    """
    injection_path = project_root / ".ralph" / "injections.json"
    injection_path.parent.mkdir(parents=True, exist_ok=True)

    injection = {
        "timestamp": datetime.now().isoformat(),
        "content": content,
        "source": source,
        "priority": priority,
    }

    with open(injection_path, "a") as f:
        f.write(json.dumps(injection) + "\n")


def build_iteration_context(
    state: RalphState,
    plan: ImplementationPlan,
    project_root: Path,
) -> IterationContext:
    """Build the context for a new iteration.

    Args:
        state: Current Ralph state
        plan: Current implementation plan
        project_root: Path to project root

    Returns:
        Assembled iteration context
    """
    # Get current task
    current_task = None
    next_task = plan.get_next_task()
    if next_task:
        current_task = {
            "id": next_task.id,
            "description": next_task.description,
            "priority": next_task.priority,
            "verification_criteria": next_task.verification_criteria,
            "dependencies": next_task.dependencies,
            "retry_count": next_task.retry_count,
        }

    # Calculate usage percentage
    if state.context_budget.total_capacity > 0:
        usage_pct = (
            state.context_budget.current_usage / state.context_budget.total_capacity * 100
        )
    else:
        usage_pct = 0.0

    return IterationContext(
        iteration=state.iteration_count,
        phase=state.current_phase,
        session_id=state.session_id,
        current_task=current_task,
        completed_tasks_this_session=state.tasks_completed_this_session,
        total_completed_tasks=plan.complete_count,
        total_pending_tasks=plan.pending_count,
        memory_content=load_memory_file(project_root),
        injections=load_injections(project_root),
        remaining_tokens=state.context_budget.available_tokens,
        usage_percentage=usage_pct,
    )


def generate_memory_content(
    state: RalphState,
    plan: ImplementationPlan,
    project_root: Path,
    session_summary: str | None = None,
    files_modified: list[str] | None = None,
    architectural_decisions: list[str] | None = None,
    blockers: list[str] | None = None,
    notes_for_next: list[str] | None = None,
    max_files: int = DEFAULT_MAX_FILES_IN_MEMORY,
) -> str:
    """Generate MEMORY.md content for session hand-off.

    Args:
        state: Current Ralph state
        plan: Current implementation plan
        project_root: Path to project root
        session_summary: Optional LLM-provided summary
        files_modified: List of modified files
        architectural_decisions: Decisions made this session
        blockers: Current blockers
        notes_for_next: Notes for next session
        max_files: Maximum number of files to include in memory.
            Defaults to DEFAULT_MAX_FILES_IN_MEMORY (10).

    Returns:
        Markdown content for MEMORY.md
    """
    lines = [f"# Session Memory - Iteration {state.iteration_count}", ""]

    # Completed this session
    completed = [t for t in plan.tasks if t.status == TaskStatus.COMPLETE and t.completed_at]
    # Sort by completion time to get recent ones
    completed.sort(key=lambda t: t.completed_at or datetime.min, reverse=True)
    recent_completed = completed[: state.tasks_completed_this_session]

    lines.append("## Completed This Session")
    if recent_completed:
        for task in recent_completed:
            lines.append(f"- [x] {task.description}")
    else:
        lines.append("- No tasks completed this session")
    lines.append("")

    # Current task in progress
    in_progress = [t for t in plan.tasks if t.status == TaskStatus.IN_PROGRESS]
    lines.append("## Current Task In Progress")
    if in_progress:
        task = in_progress[0]
        lines.append(f"Task ID: {task.id}")
        lines.append(f"Description: {task.description}")
        if task.completion_notes:
            lines.append(f"Progress: {task.completion_notes}")
    else:
        next_task = plan.get_next_task()
        if next_task:
            lines.append(f"Next up: {next_task.description} (ID: {next_task.id})")
        else:
            lines.append("No task in progress")
    lines.append("")

    # Architectural decisions
    lines.append("## Architectural Decisions")
    if architectural_decisions:
        for decision in architectural_decisions:
            lines.append(f"- {decision}")
    else:
        lines.append("- No new decisions this session")
    lines.append("")

    # Files modified
    lines.append("## Files Modified")
    if files_modified:
        for i, file in enumerate(files_modified[:max_files], 1):
            lines.append(f"{i}. {file}")
    else:
        lines.append("- No files tracked this session")
    lines.append("")

    # Blockers
    lines.append("## Blockers/Issues")
    if blockers:
        for blocker in blockers:
            lines.append(f"- {blocker}")
    else:
        blocked_tasks = [t for t in plan.tasks if t.status == TaskStatus.BLOCKED]
        if blocked_tasks:
            for task in blocked_tasks:
                lines.append(f"- {task.description}: {task.completion_notes or 'Unknown reason'}")
        else:
            lines.append("- No blockers identified")
    lines.append("")

    # Notes for next session
    lines.append("## Notes for Next Session")
    if notes_for_next:
        for note in notes_for_next:
            lines.append(f"- {note}")
    else:
        lines.append("- Continue from current task")
    lines.append("")

    # Session metadata
    lines.append("## Session Metadata")
    lines.append(f"- Phase: {state.current_phase.value}")
    lines.append(f"- Iteration: {state.iteration_count}")
    lines.append(f"- Session Cost: ${state.session_cost_usd:.4f}")
    lines.append(f"- Session Tokens: {state.session_tokens_used:,}")
    lines.append(f"- Total Progress: {plan.completion_percentage:.0%}")
    lines.append(f"- Timestamp: {datetime.now().isoformat()}")
    lines.append("")

    # Optional LLM summary
    if session_summary:
        lines.append("## LLM Session Summary")
        lines.append(session_summary)
        lines.append("")

    return "\n".join(lines)


def write_memory_file(content: str, project_root: Path) -> Path:
    """Write .ralph/MEMORY.md file.

    Args:
        content: Memory content to write
        project_root: Path to project root

    Returns:
        Path to written file
    """
    ralph_dir = project_root / ".ralph"
    ralph_dir.mkdir(parents=True, exist_ok=True)
    memory_path = ralph_dir / "MEMORY.md"
    memory_path.write_text(content)
    return memory_path


def archive_session(
    state: RalphState,
    handoff_reason: str,
    project_root: Path,
) -> Path:
    """Archive the current session to history.

    Args:
        state: Current Ralph state
        handoff_reason: Reason for session handoff
        project_root: Path to project root

    Returns:
        Path to archive file
    """
    history_dir = project_root / ".ralph" / "session_history"
    history_dir.mkdir(parents=True, exist_ok=True)

    archive = SessionArchive(
        session_id=state.session_id or f"session-{state.iteration_count}",
        iteration=state.iteration_count,
        started_at=state.started_at,
        ended_at=datetime.now(),
        tokens_used=state.session_tokens_used,
        cost_usd=state.session_cost_usd,
        tasks_completed=state.tasks_completed_this_session,
        phase=state.current_phase,
        handoff_reason=handoff_reason,
        summary_path=str(project_root / "MEMORY.md"),
    )

    # Save to history file (JSON Lines format)
    history_file = history_dir / "sessions.jsonl"
    with open(history_file, "a") as f:
        archive_data = {
            "session_id": archive.session_id,
            "iteration": archive.iteration,
            "started_at": archive.started_at.isoformat(),
            "ended_at": archive.ended_at.isoformat(),
            "tokens_used": archive.tokens_used,
            "cost_usd": archive.cost_usd,
            "tasks_completed": archive.tasks_completed,
            "phase": archive.phase.value,
            "handoff_reason": archive.handoff_reason,
            "summary_path": archive.summary_path,
        }
        f.write(json.dumps(archive_data) + "\n")

    return history_file


def load_session_history(
    project_root: Path,
    limit: int = DEFAULT_MAX_SESSION_HISTORY,
) -> list[SessionArchive]:
    """Load session history.

    Args:
        project_root: Path to project root
        limit: Maximum number of sessions to load.
            Defaults to DEFAULT_MAX_SESSION_HISTORY (50).

    Returns:
        List of session archives (most recent first)
    """
    history_file = project_root / ".ralph" / "session_history" / "sessions.jsonl"
    if not history_file.exists():
        return []

    sessions = []
    try:
        with open(history_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                sessions.append(
                    SessionArchive(
                        session_id=data["session_id"],
                        iteration=data["iteration"],
                        started_at=datetime.fromisoformat(data["started_at"]),
                        ended_at=datetime.fromisoformat(data["ended_at"]),
                        tokens_used=data["tokens_used"],
                        cost_usd=data["cost_usd"],
                        tasks_completed=data["tasks_completed"],
                        phase=Phase(data["phase"]),
                        handoff_reason=data["handoff_reason"],
                        summary_path=data.get("summary_path"),
                    )
                )
    except (json.JSONDecodeError, KeyError):
        pass

    # Return most recent first
    sessions.reverse()
    return sessions[:limit]


@dataclass
class HandoffResult:
    """Result from executing a context hand-off."""

    success: bool
    reason: str
    memory_path: Path | None = None
    archive_path: Path | None = None
    next_session_id: str | None = None


def execute_context_handoff(
    state: RalphState,
    plan: ImplementationPlan,
    project_root: Path,
    reason: str,
    session_summary: str | None = None,
    files_modified: list[str] | None = None,
    architectural_decisions: list[str] | None = None,
) -> HandoffResult:
    """Execute a full context hand-off.

    This should be called when:
    - Context budget threshold is reached
    - Phase transition occurs
    - Explicit user request

    Args:
        state: Current Ralph state
        plan: Current implementation plan
        project_root: Path to project root
        reason: Reason for handoff
        session_summary: Optional LLM-provided summary
        files_modified: List of modified files
        architectural_decisions: Decisions made this session

    Returns:
        HandoffResult with paths and next session ID
    """
    try:
        # Capture session handoff memory using MemoryManager (harness-controlled)
        # This provides deterministic memory capture at session boundaries
        try:
            from ralph.memory import MemoryManager

            memory_manager = MemoryManager(project_root)
            memory_manager.capture_session_handoff_memory(
                state=state,
                plan=plan,
                handoff_reason=reason,
            )

            # Also rotate old memory files if needed
            memory_manager.rotate_files()
        except Exception as mem_error:
            # Don't fail handoff if memory capture fails
            logger.warning(f"Memory capture failed during handoff: {mem_error}")

        # Generate and write MEMORY.md (legacy, for backwards compatibility)
        memory_content = generate_memory_content(
            state=state,
            plan=plan,
            project_root=project_root,
            session_summary=session_summary,
            files_modified=files_modified,
            architectural_decisions=architectural_decisions,
        )
        memory_path = write_memory_file(memory_content, project_root)

        # Archive session
        archive_path = archive_session(state, reason, project_root)

        # Generate next session ID
        next_session_id = f"session-{state.iteration_count + 1}-{datetime.now().strftime('%H%M%S')}"

        # Clear processed injections
        clear_injections(project_root)

        return HandoffResult(
            success=True,
            reason=reason,
            memory_path=memory_path,
            archive_path=archive_path,
            next_session_id=next_session_id,
        )
    except Exception as e:
        return HandoffResult(
            success=False,
            reason=f"Handoff failed: {e}",
        )


def should_trigger_handoff(state: RalphState) -> tuple[bool, str | None]:
    """Check if a context hand-off should be triggered.

    Args:
        state: Current Ralph state

    Returns:
        Tuple of (should_handoff, reason)
    """
    # Check context budget
    if state.needs_handoff():
        return True, "context_budget_threshold"

    # Check if approaching effective capacity (more urgent)
    budget = state.context_budget
    if budget.total_capacity > 0:
        usage_ratio = budget.current_usage / budget.total_capacity
        if usage_ratio >= 0.75:
            return True, "context_budget_warning"

    return False, None


async def generate_llm_session_summary(
    state: RalphState,
    plan: ImplementationPlan,
    project_root: Path,
    recent_work: str | None = None,
) -> str | None:
    """Generate an LLM summary of the session for MEMORY.md.

    Uses Claude to create a concise summary of what was accomplished,
    key decisions made, and context for the next session.

    Args:
        state: Current Ralph state
        plan: Current implementation plan
        project_root: Path to project root
        recent_work: Optional description of recent work for context

    Returns:
        Summary text or None if generation fails
    """
    try:
        from claude_agent_sdk import query

        # Build context for the summary
        completed_this_session = [
            t for t in plan.tasks
            if t.status == TaskStatus.COMPLETE
            and t.completed_at is not None
        ]
        completed_this_session.sort(
            key=lambda t: t.completed_at or datetime.min, reverse=True
        )
        recent_completed = completed_this_session[:state.tasks_completed_this_session]

        tasks_summary = "\n".join(
            f"- {t.description}" for t in recent_completed
        ) if recent_completed else "No tasks completed this session"

        blocked_tasks = [t for t in plan.tasks if t.status == TaskStatus.BLOCKED]
        blockers_summary = "\n".join(
            f"- {t.description}: {t.completion_notes or 'Unknown'}"
            for t in blocked_tasks
        ) if blocked_tasks else "No blockers"

        prompt = f"""Summarize this development session for handoff to a fresh context window.

Session Info:
- Phase: {state.current_phase.value}
- Iteration: {state.iteration_count}
- Tasks completed: {state.tasks_completed_this_session}
- Cost: ${state.session_cost_usd:.4f}

Completed Tasks:
{tasks_summary}

Blockers:
{blockers_summary}

{f"Recent work context: {recent_work}" if recent_work else ""}

Write a concise 2-3 sentence summary that helps the next session continue effectively.
Focus on: what was done, key decisions, and what to do next."""

        # Use SDK query to get the summary
        from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock

        options = ClaudeAgentOptions(
            allowed_tools=[],  # No tools needed for summary
            permission_mode="bypassPermissions",
            max_turns=1,
        )

        result_parts: list[str] = []
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        result_parts.append(block.text)

        if result_parts:
            return " ".join(result_parts).strip()

        return None

    except ImportError:
        logger.warning("Claude SDK not available for summary generation")
        return None
    except Exception as e:
        logger.warning("Failed to generate LLM session summary: %s", e)
        return None
