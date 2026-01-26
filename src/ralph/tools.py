"""Custom MCP tools for Ralph orchestrator.

Provides structured state management tools that the LLM can use
during execution to interact with Ralph's state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ralph.models import ImplementationPlan, RalphState, Task, TaskStatus
from ralph.persistence import load_plan, load_state, save_plan, save_state


@dataclass
class ToolResult:
    """Result from a custom tool execution."""

    success: bool
    content: str
    data: dict[str, Any] | None = None
    error: str | None = None


class RalphTools:
    """Custom tools for Ralph state management.

    These tools are exposed via MCP for the LLM to interact
    with Ralph's state in a structured way.
    """

    def __init__(self, project_root: Path) -> None:
        """Initialize tools with project root.

        Args:
            project_root: Path to the project root directory
        """
        self.project_root = project_root

    def _load_state(self) -> RalphState:
        """Load current Ralph state."""
        return load_state(self.project_root)

    def _save_state(self, state: RalphState) -> None:
        """Save Ralph state."""
        save_state(state, self.project_root)

    def _load_plan(self) -> ImplementationPlan:
        """Load current implementation plan."""
        return load_plan(self.project_root)

    def _save_plan(self, plan: ImplementationPlan) -> None:
        """Save implementation plan."""
        save_plan(plan, self.project_root)

    def get_next_task(self) -> ToolResult:
        """Get the highest-priority incomplete task.

        Returns the next task that should be worked on based on
        priority and dependency constraints.

        Returns:
            ToolResult with task information or message if no tasks available
        """
        try:
            plan = self._load_plan()
            task = plan.get_next_task()

            if task is None:
                return ToolResult(
                    success=True,
                    content="No tasks available. All tasks may be complete or blocked.",
                    data={"task": None, "remaining_count": plan.pending_count},
                )

            task_data = {
                "id": task.id,
                "description": task.description,
                "priority": task.priority,
                "status": task.status.value,
                "dependencies": task.dependencies,
                "verification_criteria": task.verification_criteria,
                "estimated_tokens": task.estimated_tokens,
                "retry_count": task.retry_count,
            }

            return ToolResult(
                success=True,
                content=f"Next task: {task.description}",
                data={"task": task_data, "remaining_count": plan.pending_count},
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="Failed to get next task",
                error=str(e),
            )

    def mark_task_complete(
        self,
        task_id: str,
        verification_notes: str | None = None,
        tokens_used: int | None = None,
    ) -> ToolResult:
        """Mark a task as completed.

        Args:
            task_id: ID of the task to mark complete
            verification_notes: Optional notes about verification
            tokens_used: Optional token count used for this task

        Returns:
            ToolResult indicating success or failure
        """
        try:
            plan = self._load_plan()
            state = self._load_state()

            # Verify task exists and is in progress or pending
            task = plan.get_task_by_id(task_id)
            if task is None:
                return ToolResult(
                    success=False,
                    content=f"Task not found: {task_id}",
                    error="Task ID does not exist in the plan",
                )

            if task.status == TaskStatus.COMPLETE:
                return ToolResult(
                    success=True,
                    content=f"Task already complete: {task_id}",
                    data={"task_id": task_id, "was_already_complete": True},
                )

            # Mark complete
            success = plan.mark_task_complete(task_id, verification_notes, tokens_used)
            if not success:
                return ToolResult(
                    success=False,
                    content=f"Failed to mark task complete: {task_id}",
                    error="Unknown error marking task complete",
                )

            # Update state
            state.tasks_completed_this_session += 1
            if tokens_used:
                state.context_budget.add_usage(tokens_used)

            # Save both
            self._save_plan(plan)
            self._save_state(state)

            return ToolResult(
                success=True,
                content=f"Task completed: {task_id}",
                data={
                    "task_id": task_id,
                    "completion_percentage": plan.completion_percentage,
                    "remaining_tasks": plan.pending_count,
                },
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="Failed to mark task complete",
                error=str(e),
            )

    def mark_task_blocked(self, task_id: str, reason: str) -> ToolResult:
        """Mark a task as blocked.

        Args:
            task_id: ID of the task to mark blocked
            reason: Reason why the task is blocked

        Returns:
            ToolResult indicating success or failure
        """
        try:
            plan = self._load_plan()

            # Verify task exists
            task = plan.get_task_by_id(task_id)
            if task is None:
                return ToolResult(
                    success=False,
                    content=f"Task not found: {task_id}",
                    error="Task ID does not exist in the plan",
                )

            if task.status == TaskStatus.BLOCKED:
                return ToolResult(
                    success=True,
                    content=f"Task already blocked: {task_id}",
                    data={"task_id": task_id, "was_already_blocked": True},
                )

            # Mark blocked
            success = plan.mark_task_blocked(task_id, reason)
            if not success:
                return ToolResult(
                    success=False,
                    content=f"Failed to mark task blocked: {task_id}",
                    error="Unknown error marking task blocked",
                )

            self._save_plan(plan)

            return ToolResult(
                success=True,
                content=f"Task blocked: {task_id} - {reason}",
                data={
                    "task_id": task_id,
                    "reason": reason,
                    "remaining_tasks": plan.pending_count,
                },
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="Failed to mark task blocked",
                error=str(e),
            )

    def mark_task_in_progress(self, task_id: str) -> ToolResult:
        """Mark a task as in progress.

        Args:
            task_id: ID of the task to start

        Returns:
            ToolResult indicating success or failure
        """
        try:
            plan = self._load_plan()

            task = plan.get_task_by_id(task_id)
            if task is None:
                return ToolResult(
                    success=False,
                    content=f"Task not found: {task_id}",
                    error="Task ID does not exist in the plan",
                )

            if task.status != TaskStatus.PENDING:
                return ToolResult(
                    success=False,
                    content=f"Task cannot be started: {task_id} (status: {task.status.value})",
                    error="Task must be in PENDING status to start",
                )

            task.status = TaskStatus.IN_PROGRESS
            plan.last_modified = datetime.now()
            self._save_plan(plan)

            return ToolResult(
                success=True,
                content=f"Task started: {task_id}",
                data={"task_id": task_id, "status": "in_progress"},
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="Failed to mark task in progress",
                error=str(e),
            )

    def increment_retry(self, task_id: str) -> ToolResult:
        """Increment retry count for a task.

        Args:
            task_id: ID of the task

        Returns:
            ToolResult with updated retry count
        """
        try:
            plan = self._load_plan()

            task = plan.get_task_by_id(task_id)
            if task is None:
                return ToolResult(
                    success=False,
                    content=f"Task not found: {task_id}",
                    error="Task ID does not exist in the plan",
                )

            task.retry_count += 1
            task.status = TaskStatus.PENDING  # Reset to pending for retry
            plan.last_modified = datetime.now()
            self._save_plan(plan)

            return ToolResult(
                success=True,
                content=f"Retry count incremented for: {task_id}",
                data={"task_id": task_id, "retry_count": task.retry_count},
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="Failed to increment retry count",
                error=str(e),
            )

    def append_learning(
        self,
        learning: str,
        category: str = "pattern",
    ) -> ToolResult:
        """Record a learning for future iterations.

        Appends to progress.txt for operational learnings.

        Args:
            learning: The learning to record
            category: Category (pattern, antipattern, architecture, debugging, build)

        Returns:
            ToolResult indicating success or failure
        """
        valid_categories = {"pattern", "antipattern", "architecture", "debugging", "build"}
        if category not in valid_categories:
            return ToolResult(
                success=False,
                content=f"Invalid category: {category}",
                error=f"Category must be one of: {', '.join(valid_categories)}",
            )

        try:
            progress_file = self.project_root / "progress.txt"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            entry = f"[{timestamp}] {category.upper()}: {learning}\n"

            # Append to file (create if doesn't exist)
            with open(progress_file, "a") as f:
                f.write(entry)

            return ToolResult(
                success=True,
                content=f"Learning recorded: {learning[:50]}...",
                data={"category": category, "timestamp": timestamp},
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="Failed to record learning",
                error=str(e),
            )

    def get_plan_summary(self) -> ToolResult:
        """Get a summary of the current implementation plan.

        Returns:
            ToolResult with plan summary
        """
        try:
            plan = self._load_plan()

            summary = {
                "total_tasks": len(plan.tasks),
                "complete": plan.complete_count,
                "pending": plan.pending_count,
                "blocked": sum(1 for t in plan.tasks if t.status == TaskStatus.BLOCKED),
                "in_progress": sum(1 for t in plan.tasks if t.status == TaskStatus.IN_PROGRESS),
                "completion_percentage": plan.completion_percentage,
                "created_at": plan.created_at.isoformat(),
                "last_modified": plan.last_modified.isoformat(),
            }

            next_task = plan.get_next_task()
            if next_task:
                summary["next_task"] = {
                    "id": next_task.id,
                    "description": next_task.description,
                    "priority": next_task.priority,
                }

            content_lines = [
                f"Tasks: {summary['complete']}/{summary['total_tasks']} complete "
                f"({summary['completion_percentage']:.0%})",
                f"Pending: {summary['pending']}, Blocked: {summary['blocked']}, "
                f"In Progress: {summary['in_progress']}",
            ]
            if next_task:
                content_lines.append(f"Next: {next_task.description}")

            return ToolResult(
                success=True,
                content="\n".join(content_lines),
                data=summary,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="Failed to get plan summary",
                error=str(e),
            )

    def get_state_summary(self) -> ToolResult:
        """Get a summary of the current Ralph state.

        Returns:
            ToolResult with state summary
        """
        try:
            state = self._load_state()

            summary = {
                "phase": state.current_phase.value,
                "iteration": state.iteration_count,
                "session_id": state.session_id,
                "total_cost_usd": state.total_cost_usd,
                "session_cost_usd": state.session_cost_usd,
                "total_tokens": state.total_tokens_used,
                "session_tokens": state.session_tokens_used,
                "tasks_completed_this_session": state.tasks_completed_this_session,
                "context_usage_pct": (
                    state.context_budget.current_usage / state.context_budget.total_capacity * 100
                    if state.context_budget.total_capacity > 0
                    else 0
                ),
                "needs_handoff": state.needs_handoff(),
                "circuit_breaker": {
                    "state": state.circuit_breaker.state,
                    "failure_count": state.circuit_breaker.failure_count,
                    "stagnation_count": state.circuit_breaker.stagnation_count,
                },
            }

            should_halt, halt_reason = state.should_halt()
            summary["should_halt"] = should_halt
            summary["halt_reason"] = halt_reason

            circuit_breaker_info = summary["circuit_breaker"]
            assert isinstance(circuit_breaker_info, dict)
            content_lines = [
                f"Phase: {summary['phase']}, Iteration: {summary['iteration']}",
                f"Session tasks: {summary['tasks_completed_this_session']}, "
                f"Cost: ${summary['session_cost_usd']:.4f}",
                f"Context: {summary['context_usage_pct']:.1f}% used",
                f"Circuit breaker: {circuit_breaker_info['state']}",
            ]
            if should_halt:
                content_lines.append(f"HALTING: {halt_reason}")

            return ToolResult(
                success=True,
                content="\n".join(content_lines),
                data=summary,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="Failed to get state summary",
                error=str(e),
            )

    def add_task(
        self,
        task_id: str,
        description: str,
        priority: int,
        dependencies: list[str] | None = None,
        verification_criteria: list[str] | None = None,
        estimated_tokens: int = 30_000,
    ) -> ToolResult:
        """Add a new task to the implementation plan.

        Args:
            task_id: Unique ID for the task
            description: Task description
            priority: Priority (1 = highest)
            dependencies: List of task IDs this depends on
            verification_criteria: List of criteria to verify completion
            estimated_tokens: Estimated tokens needed

        Returns:
            ToolResult indicating success or failure
        """
        try:
            plan = self._load_plan()

            # Check for duplicate ID
            if plan.get_task_by_id(task_id) is not None:
                return ToolResult(
                    success=False,
                    content=f"Task ID already exists: {task_id}",
                    error="Duplicate task ID",
                )

            # Validate dependencies exist
            if dependencies:
                for dep in dependencies:
                    if plan.get_task_by_id(dep) is None:
                        return ToolResult(
                            success=False,
                            content=f"Dependency not found: {dep}",
                            error=f"Task {dep} does not exist in the plan",
                        )

            task = Task(
                id=task_id,
                description=description,
                priority=priority,
                dependencies=dependencies or [],
                verification_criteria=verification_criteria or [],
                estimated_tokens=estimated_tokens,
            )

            plan.tasks.append(task)
            plan.last_modified = datetime.now()
            self._save_plan(plan)

            return ToolResult(
                success=True,
                content=f"Task added: {task_id}",
                data={
                    "task_id": task_id,
                    "priority": priority,
                    "total_tasks": len(plan.tasks),
                },
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="Failed to add task",
                error=str(e),
            )


def create_tools(project_root: Path) -> RalphTools:
    """Create a RalphTools instance for the given project.

    Args:
        project_root: Path to the project root

    Returns:
        Configured RalphTools instance
    """
    return RalphTools(project_root)


# Tool definitions for MCP exposure
TOOL_DEFINITIONS = [
    {
        "name": "ralph_get_next_task",
        "description": "Get the highest-priority incomplete task from the implementation plan",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "ralph_mark_task_complete",
        "description": "Mark a task as completed with optional verification notes",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "ID of the task to complete"},
                "verification_notes": {
                    "type": "string",
                    "description": "Notes about how the task was verified",
                },
                "tokens_used": {
                    "type": "integer",
                    "description": "Number of tokens used to complete this task",
                },
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "ralph_mark_task_blocked",
        "description": "Mark a task as blocked with a reason",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "ID of the task to block"},
                "reason": {"type": "string", "description": "Reason why the task is blocked"},
            },
            "required": ["task_id", "reason"],
        },
    },
    {
        "name": "ralph_append_learning",
        "description": "Record a learning for future iterations",
        "input_schema": {
            "type": "object",
            "properties": {
                "learning": {"type": "string", "description": "The learning to record"},
                "category": {
                    "type": "string",
                    "enum": ["pattern", "antipattern", "architecture", "debugging", "build"],
                    "description": "Category of the learning",
                },
            },
            "required": ["learning"],
        },
    },
    {
        "name": "ralph_get_plan_summary",
        "description": "Get a summary of the current implementation plan",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "ralph_get_state_summary",
        "description": "Get a summary of the current Ralph state",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "ralph_add_task",
        "description": "Add a new task to the implementation plan",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Unique ID for the task"},
                "description": {"type": "string", "description": "Task description"},
                "priority": {
                    "type": "integer",
                    "description": "Priority (1 = highest)",
                },
                "dependencies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of task IDs this depends on",
                },
                "verification_criteria": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Criteria to verify completion",
                },
            },
            "required": ["task_id", "description", "priority"],
        },
    },
]
