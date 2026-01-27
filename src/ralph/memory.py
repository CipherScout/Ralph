"""Deterministic memory management for Ralph orchestrator (SPEC-004).

Provides automated memory capture at well-defined boundaries:
- Phase transitions (discovery -> planning -> building -> validation)
- Iteration boundaries (end of each iteration within a phase)
- Session handoffs (when context budget is exceeded)

Memory is harness-controlled (Python code), not LLM-dependent,
ensuring deterministic and predictable behavior.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ralph.models import ImplementationPlan, Phase, RalphState, TaskStatus

if TYPE_CHECKING:
    from ralph.sdk_client import IterationResult


# Phase order for determining previous phase
PHASE_ORDER = [Phase.DISCOVERY, Phase.PLANNING, Phase.BUILDING, Phase.VALIDATION]


@dataclass
class MemoryConfig:
    """Configuration for memory management."""

    max_active_memory_chars: int = 8000
    max_iteration_files: int = 20
    max_session_files: int = 10
    max_phase_memory_chars: int = 5000
    archive_after_days: int = 30


@dataclass
class IterationMemory:
    """Memory captured at end of iteration."""

    iteration: int
    phase: Phase
    timestamp: datetime
    tasks_completed: list[str]
    tasks_blocked: list[str]
    progress_made: bool
    tokens_used: int
    cost_usd: float
    error: str | None = None


@dataclass
class PhaseMemory:
    """Memory captured at phase transition."""

    phase: Phase
    completed_at: datetime
    iterations_in_phase: int
    artifacts: dict[str, Any]
    summary: str
    key_decisions: list[str] = field(default_factory=list)


@dataclass
class SessionMemory:
    """Memory captured at session handoff."""

    session_id: str
    phase: Phase
    iteration: int
    handoff_reason: str
    task_in_progress: str | None
    tokens_used: int
    cost_usd: float
    notes_for_next: list[str] = field(default_factory=list)


class MemoryManager:
    """Manages deterministic memory capture and retrieval.

    The MemoryManager is responsible for:
    1. Capturing memory at phase transitions, iteration boundaries, and session handoffs
    2. Building active memory content for injection into agent prompts
    3. Loading historical memory for context
    4. Rotating and cleaning up old memory files
    """

    def __init__(self, project_root: Path, config: MemoryConfig | None = None) -> None:
        """Initialize memory manager.

        Args:
            project_root: Path to the project root
            config: Optional memory configuration (uses defaults if not provided)
        """
        self.project_root = project_root
        self.config = config or MemoryConfig()
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Ensure memory directories exist."""
        memory_dir = self.project_root / ".ralph" / "memory"
        (memory_dir / "phases").mkdir(parents=True, exist_ok=True)
        (memory_dir / "iterations").mkdir(parents=True, exist_ok=True)
        (memory_dir / "sessions").mkdir(parents=True, exist_ok=True)
        (memory_dir / "archive").mkdir(parents=True, exist_ok=True)

    # --- Capture Methods ---

    def capture_iteration_memory(
        self,
        state: RalphState,
        plan: ImplementationPlan,
        result: IterationResult,
    ) -> Path:
        """Capture memory at end of iteration.

        Called automatically by the executor at the end of each iteration.

        Args:
            state: Current Ralph state
            plan: Current implementation plan
            result: Result from the iteration

        Returns:
            Path to the created iteration memory file
        """
        # Gather task information
        tasks_completed = [t.id for t in plan.tasks if t.status == TaskStatus.COMPLETE]
        tasks_blocked = [t.id for t in plan.tasks if t.status == TaskStatus.BLOCKED]

        # Determine if progress was made
        progress_made = result.success and (len(tasks_completed) > 0 or result.tokens_used > 0)

        mem = IterationMemory(
            iteration=state.iteration_count,
            phase=state.current_phase,
            timestamp=datetime.now(),
            tasks_completed=tasks_completed,
            tasks_blocked=tasks_blocked,
            progress_made=progress_made,
            tokens_used=result.tokens_used,
            cost_usd=result.cost_usd,
            error=(
                None if result.success
                else result.final_text[:500] if result.final_text else None
            ),
        )

        # Write to file
        filename = f"iter-{state.iteration_count:03d}.md"
        path = self.project_root / ".ralph" / "memory" / "iterations" / filename
        path.write_text(self._format_iteration_memory(mem))

        return path

    def capture_phase_transition_memory(
        self,
        state: RalphState,
        plan: ImplementationPlan,
        old_phase: Phase,
        new_phase: Phase,
        artifacts: dict[str, Any],
    ) -> Path:
        """Capture memory at phase transition.

        Called when transitioning from one phase to another.

        Args:
            state: Current Ralph state
            plan: Current implementation plan
            old_phase: Phase being completed
            new_phase: Phase being entered
            artifacts: Phase-specific artifacts (specs, tasks, etc.)

        Returns:
            Path to the created phase memory file
        """
        # Build summary from artifacts
        summary_parts = []
        for key, value in artifacts.items():
            if isinstance(value, list):
                summary_parts.append(f"- {key}: {', '.join(str(v) for v in value)}")
            else:
                summary_parts.append(f"- {key}: {value}")
        summary = "\n".join(summary_parts) if summary_parts else "No artifacts recorded"

        mem = PhaseMemory(
            phase=old_phase,
            completed_at=datetime.now(),
            iterations_in_phase=state.iteration_count,
            artifacts=artifacts,
            summary=summary,
            key_decisions=[],
        )

        # Write to file (overwrites existing)
        filename = f"{old_phase.value}.md"
        path = self.project_root / ".ralph" / "memory" / "phases" / filename
        path.write_text(self._format_phase_memory(mem))

        return path

    def capture_session_handoff_memory(
        self,
        state: RalphState,
        plan: ImplementationPlan,
        handoff_reason: str,
    ) -> Path:
        """Capture memory at session handoff.

        Called when the session is ending due to context budget or other reasons.

        Args:
            state: Current Ralph state
            plan: Current implementation plan
            handoff_reason: Reason for the handoff

        Returns:
            Path to the created session memory file
        """
        # Find task in progress
        task_in_progress = None
        for task in plan.tasks:
            if task.status == TaskStatus.IN_PROGRESS:
                task_in_progress = task.id
                break

        mem = SessionMemory(
            session_id=state.session_id or "unknown",
            phase=state.current_phase,
            iteration=state.iteration_count,
            handoff_reason=handoff_reason,
            task_in_progress=task_in_progress,
            tokens_used=state.session_tokens_used,
            cost_usd=state.session_cost_usd,
            notes_for_next=[],
        )

        # Determine next session number
        session_dir = self.project_root / ".ralph" / "memory" / "sessions"
        existing = list(session_dir.glob("session-*.md"))
        next_num = len(existing) + 1

        filename = f"session-{next_num:03d}.md"
        path = session_dir / filename
        path.write_text(self._format_session_memory(mem))

        return path

    # --- Retrieval Methods ---

    def build_active_memory(
        self,
        state: RalphState,
        plan: ImplementationPlan,
    ) -> str:
        """Build the active memory content for prompt injection.

        Combines memory from multiple sources into a single string
        suitable for injection into the agent's system prompt.

        Args:
            state: Current Ralph state
            plan: Current implementation plan

        Returns:
            Combined memory content (truncated to max chars)
        """
        sections: list[str] = []

        # 1. Previous phase context (critical for transitions)
        prev_phase = self._get_previous_phase(state.current_phase)
        if prev_phase:
            prev_mem = self.load_phase_memory(prev_phase)
            if prev_mem:
                truncated = prev_mem[:1500] if len(prev_mem) > 1500 else prev_mem
                sections.append(f"## From {prev_phase.value.title()} Phase\n{truncated}")

        # 2. Current phase context
        current_mem = self.load_phase_memory(state.current_phase)
        if current_mem:
            truncated = current_mem[:1000] if len(current_mem) > 1000 else current_mem
            sections.append(f"## Current Phase ({state.current_phase.value})\n{truncated}")

        # 3. Recent iterations (last 3)
        recent = self.load_recent_iterations(limit=3)
        if recent:
            iter_texts = [self._format_iteration_summary(r) for r in recent]
            sections.append("## Recent Progress\n" + "\n\n".join(iter_texts))

        # 4. Task state summary
        task_summary = self._format_task_state(plan)
        if task_summary:
            sections.append(f"## Task State\n{task_summary}")

        # 5. Session metrics
        metrics = self._format_session_metrics(state)
        sections.append(f"## Session Metrics\n{metrics}")

        # Combine and truncate
        combined = "\n\n".join(sections)
        if len(combined) > self.config.max_active_memory_chars:
            combined = combined[: self.config.max_active_memory_chars - 50] + "\n\n...(truncated)"

        return combined

    def load_phase_memory(self, phase: Phase) -> str | None:
        """Load memory for a specific phase.

        Args:
            phase: The phase to load memory for

        Returns:
            Memory content or None if not found
        """
        path = self.project_root / ".ralph" / "memory" / "phases" / f"{phase.value}.md"
        if path.exists():
            return path.read_text()
        return None

    def load_recent_iterations(self, limit: int = 5) -> list[IterationMemory]:
        """Load recent iteration memories.

        Args:
            limit: Maximum number of iterations to load

        Returns:
            List of IterationMemory objects (most recent first)
        """
        iter_dir = self.project_root / ".ralph" / "memory" / "iterations"
        if not iter_dir.exists():
            return []

        # Get files sorted by modification time (most recent last)
        files = sorted(iter_dir.glob("iter-*.md"), key=lambda p: p.stat().st_mtime)

        # Take the most recent ones
        recent_files = files[-limit:] if len(files) > limit else files

        # Parse into IterationMemory objects
        memories = []
        for f in reversed(recent_files):  # Most recent first
            try:
                mem = self._parse_iteration_file(f)
                if mem:
                    memories.append(mem)
            except Exception:
                # Skip files that can't be parsed
                continue

        return memories

    # --- Cleanup Methods ---

    def rotate_files(self) -> int:
        """Rotate old memory files to archive.

        Keeps only the most recent files according to config limits.

        Returns:
            Number of files rotated to archive
        """
        rotated = 0

        # Rotate iteration files
        iter_dir = self.project_root / ".ralph" / "memory" / "iterations"
        if iter_dir.exists():
            iter_files = sorted(iter_dir.glob("iter-*.md"), key=lambda p: p.stat().st_mtime)
            if len(iter_files) > self.config.max_iteration_files:
                archive_dir = self.project_root / ".ralph" / "memory" / "archive"
                for f in iter_files[: -self.config.max_iteration_files]:
                    archive_path = archive_dir / f.name
                    f.rename(archive_path)
                    rotated += 1

        # Rotate session files
        session_dir = self.project_root / ".ralph" / "memory" / "sessions"
        if session_dir.exists():
            session_files = sorted(
                session_dir.glob("session-*.md"), key=lambda p: p.stat().st_mtime
            )
            if len(session_files) > self.config.max_session_files:
                archive_dir = self.project_root / ".ralph" / "memory" / "archive"
                for f in session_files[: -self.config.max_session_files]:
                    archive_path = archive_dir / f.name
                    f.rename(archive_path)
                    rotated += 1

        return rotated

    def cleanup_archive(self) -> int:
        """Delete old archived files.

        Removes files older than the configured threshold.

        Returns:
            Number of files deleted
        """
        archive_dir = self.project_root / ".ralph" / "memory" / "archive"
        if not archive_dir.exists():
            return 0

        cutoff = datetime.now() - timedelta(days=self.config.archive_after_days)
        deleted = 0

        for f in archive_dir.glob("*"):
            if f.is_file():
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime < cutoff:
                    f.unlink()
                    deleted += 1

        return deleted

    def get_memory_stats(self) -> dict[str, Any]:
        """Get statistics about memory usage.

        Returns:
            Dictionary with memory statistics
        """
        memory_dir = self.project_root / ".ralph" / "memory"

        # Count files in each directory
        iter_dir = memory_dir / "iterations"
        session_dir = memory_dir / "sessions"
        phase_dir = memory_dir / "phases"
        archive_dir = memory_dir / "archive"

        iter_files = list(iter_dir.glob("iter-*.md")) if iter_dir.exists() else []
        session_files = list(session_dir.glob("session-*.md")) if session_dir.exists() else []
        phase_files = list(phase_dir.glob("*.md")) if phase_dir.exists() else []
        archive_files = list(archive_dir.glob("*")) if archive_dir.exists() else []

        # Calculate total size
        total_size = 0
        for d in [iter_dir, session_dir, phase_dir, archive_dir]:
            if d.exists():
                for f in d.glob("*"):
                    if f.is_file():
                        total_size += f.stat().st_size

        return {
            "iteration_files": len(iter_files),
            "session_files": len(session_files),
            "phase_files": len(phase_files),
            "archive_files": len(archive_files),
            "total_size_bytes": total_size,
        }

    # --- Private Formatting Methods ---

    def _format_iteration_memory(self, mem: IterationMemory) -> str:
        """Format iteration memory as markdown."""
        if mem.tasks_completed:
            completed_list = "\n".join(f"- {t}" for t in mem.tasks_completed)
        else:
            completed_list = "- None"
        if mem.tasks_blocked:
            blocked_list = "\n".join(f"- {t}" for t in mem.tasks_blocked)
        else:
            blocked_list = "- None"

        error_section = f"\n### Error\n{mem.error}" if mem.error else ""
        progress = "Yes" if mem.progress_made else "No"

        return f"""## Iteration {mem.iteration} ({mem.phase.value})

**Time**: {mem.timestamp.strftime('%Y-%m-%d %H:%M')}
**Progress**: {progress} | Tokens: {mem.tokens_used:,} | Cost: ${mem.cost_usd:.4f}

### Tasks Completed
{completed_list}

### Tasks Blocked
{blocked_list}
{error_section}
"""

    def _format_phase_memory(self, mem: PhaseMemory) -> str:
        """Format phase memory as markdown."""
        if mem.key_decisions:
            decisions = "\n".join(f"- {d}" for d in mem.key_decisions)
        else:
            decisions = "- None recorded"
        artifacts_str = self._format_artifacts(mem.artifacts)

        return f"""# {mem.phase.value.title()} Phase Memory

**Completed**: {mem.completed_at.strftime('%Y-%m-%d %H:%M')}
**Iterations**: {mem.iterations_in_phase}

## Summary
{mem.summary}

## Key Decisions
{decisions}

## Artifacts
{artifacts_str}
"""

    def _format_session_memory(self, mem: SessionMemory) -> str:
        """Format session memory as markdown."""
        notes = "\n".join(f"- {n}" for n in mem.notes_for_next) if mem.notes_for_next else "- None"

        return f"""# Session Handoff Memory

**Session ID**: {mem.session_id}
**Phase**: {mem.phase.value}
**Iteration**: {mem.iteration}
**Handoff Reason**: {mem.handoff_reason}

## Task In Progress
{mem.task_in_progress or 'None'}

## Session Metrics
- Tokens used: {mem.tokens_used:,}
- Cost: ${mem.cost_usd:.4f}

## Notes for Next Session
{notes}
"""

    def _format_iteration_summary(self, mem: IterationMemory) -> str:
        """Format a brief iteration summary for active memory."""
        completed = len(mem.tasks_completed)
        blocked = len(mem.tasks_blocked)
        progress = "progress" if mem.progress_made else "no progress"
        return (
            f"- **Iter {mem.iteration}** ({mem.phase.value}): "
            f"{completed} completed, {blocked} blocked, {progress}"
        )

    def _format_task_state(self, plan: ImplementationPlan) -> str:
        """Format current task state."""
        if not plan.tasks:
            return "No tasks defined"

        by_status: dict[TaskStatus, list[str]] = {
            TaskStatus.COMPLETE: [],
            TaskStatus.IN_PROGRESS: [],
            TaskStatus.PENDING: [],
            TaskStatus.BLOCKED: [],
        }

        for task in plan.tasks:
            by_status[task.status].append(task.id)

        lines = []
        total = len(plan.tasks)
        complete = len(by_status[TaskStatus.COMPLETE])
        lines.append(f"- Total: {total} tasks")
        lines.append(f"- Complete: {complete} ({complete * 100 // total if total > 0 else 0}%)")

        if by_status[TaskStatus.IN_PROGRESS]:
            lines.append(f"- In Progress: {', '.join(by_status[TaskStatus.IN_PROGRESS])}")
        if by_status[TaskStatus.BLOCKED]:
            lines.append(f"- Blocked: {', '.join(by_status[TaskStatus.BLOCKED])}")

        return "\n".join(lines)

    def _format_session_metrics(self, state: RalphState) -> str:
        """Format session metrics."""
        return f"""- Iteration: {state.iteration_count}
- Session iterations: {state.session_iteration_count}
- Session cost: ${state.session_cost_usd:.4f}
- Tasks this session: {state.tasks_completed_this_session}"""

    def _format_artifacts(self, artifacts: dict[str, Any]) -> str:
        """Format artifacts dict as markdown."""
        if not artifacts:
            return "- None"

        lines = []
        for key, value in artifacts.items():
            if isinstance(value, list):
                lines.append(f"- **{key}**: {', '.join(str(v) for v in value)}")
            elif isinstance(value, dict):
                lines.append(f"- **{key}**: {json.dumps(value)}")
            else:
                lines.append(f"- **{key}**: {value}")
        return "\n".join(lines)

    def _get_previous_phase(self, current: Phase) -> Phase | None:
        """Get the previous phase in the workflow."""
        try:
            idx = PHASE_ORDER.index(current)
            if idx > 0:
                return PHASE_ORDER[idx - 1]
        except ValueError:
            pass
        return None

    def _parse_iteration_file(self, path: Path) -> IterationMemory | None:
        """Parse an iteration memory file back into an IterationMemory object."""
        content = path.read_text()

        # Extract iteration number from filename
        try:
            iter_num = int(path.stem.split("-")[1])
        except (IndexError, ValueError):
            return None

        # Extract phase from content
        phase = Phase.BUILDING  # Default
        for p in Phase:
            if p.value in content.lower():
                phase = p
                break

        # Extract tasks (simplified parsing)
        tasks_completed = []
        tasks_blocked = []
        in_completed = False
        in_blocked = False

        for line in content.split("\n"):
            line = line.strip()
            if "Tasks Completed" in line:
                in_completed = True
                in_blocked = False
            elif "Tasks Blocked" in line:
                in_completed = False
                in_blocked = True
            elif line.startswith("- ") and line != "- None":
                task_id = line[2:].strip()
                if in_completed:
                    tasks_completed.append(task_id)
                elif in_blocked:
                    tasks_blocked.append(task_id)
            elif line.startswith("###") or line.startswith("**"):
                in_completed = False
                in_blocked = False

        return IterationMemory(
            iteration=iter_num,
            phase=phase,
            timestamp=datetime.fromtimestamp(path.stat().st_mtime),
            tasks_completed=tasks_completed,
            tasks_blocked=tasks_blocked,
            progress_made=True,  # Assume progress was made
            tokens_used=0,
            cost_usd=0.0,
        )
