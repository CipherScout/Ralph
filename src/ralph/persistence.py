"""JSON state persistence layer for Ralph.

Provides save/load operations for RalphState and ImplementationPlan,
enabling deterministic workflow progression across context window resets.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import fields
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from ralph.models import (
    CircuitBreakerState,
    ContextBudget,
    ImplementationPlan,
    Phase,
    RalphState,
    Task,
    TaskStatus,
)

T = TypeVar("T")

# Default paths relative to project root
STATE_FILE = ".ralph/state.json"
PLAN_FILE = ".ralph/implementation_plan.json"
MEMORY_FILE = ".ralph/MEMORY.md"


class PersistenceError(Exception):
    """Base exception for persistence operations."""

    pass


class StateNotFoundError(PersistenceError):
    """Raised when state file does not exist."""

    pass


class CorruptedStateError(PersistenceError):
    """Raised when state file contains invalid data."""

    pass


def _datetime_to_iso(dt: datetime) -> str:
    """Convert datetime to ISO format string."""
    return dt.isoformat()


def _iso_to_datetime(iso_str: str) -> datetime:
    """Convert ISO format string to datetime."""
    return datetime.fromisoformat(iso_str)


def _serialize_dataclass(obj: Any) -> dict[str, Any]:
    """Recursively serialize a dataclass to a JSON-compatible dict.

    Handles nested dataclasses, enums, datetime, and Path objects.
    """
    if obj is None:
        return None  # type: ignore[return-value]

    result: dict[str, Any] = {}

    for f in fields(obj):
        value = getattr(obj, f.name)

        if value is None:
            result[f.name] = None
        elif isinstance(value, datetime):
            result[f.name] = _datetime_to_iso(value)
        elif isinstance(value, Path):
            result[f.name] = str(value)
        elif isinstance(value, (Phase, TaskStatus)):
            result[f.name] = value.value
        elif isinstance(value, list):
            result[f.name] = [
                _serialize_dataclass(item) if hasattr(item, "__dataclass_fields__") else item
                for item in value
            ]
        elif hasattr(value, "__dataclass_fields__"):
            result[f.name] = _serialize_dataclass(value)
        else:
            result[f.name] = value

    return result


def _deserialize_task(data: dict[str, Any]) -> Task:
    """Deserialize a Task from a dict."""
    return Task(
        id=data["id"],
        description=data["description"],
        priority=data["priority"],
        status=TaskStatus(data["status"]),
        dependencies=data.get("dependencies", []),
        verification_criteria=data.get("verification_criteria", []),
        blockers=data.get("blockers", []),
        estimated_tokens=data.get("estimated_tokens", 30_000),
        actual_tokens_used=data.get("actual_tokens_used"),
        completion_notes=data.get("completion_notes"),
        completed_at=_iso_to_datetime(data["completed_at"]) if data.get("completed_at") else None,
        retry_count=data.get("retry_count", 0),
    )


def _deserialize_circuit_breaker(data: dict[str, Any]) -> CircuitBreakerState:
    """Deserialize CircuitBreakerState from a dict."""
    return CircuitBreakerState(
        max_consecutive_failures=data.get("max_consecutive_failures", 3),
        max_stagnation_iterations=data.get("max_stagnation_iterations", 5),
        max_cost_usd=data.get("max_cost_usd", 100.0),
        state=data.get("state", "closed"),
        failure_count=data.get("failure_count", 0),
        stagnation_count=data.get("stagnation_count", 0),
        last_failure_reason=data.get("last_failure_reason"),
        # Note: total_cost was removed - cost is now tracked only in RalphState
    )


def _deserialize_context_budget(data: dict[str, Any]) -> ContextBudget:
    """Deserialize ContextBudget from a dict."""
    return ContextBudget(
        total_capacity=data.get("total_capacity", 200_000),
        system_prompt_allocation=data.get("system_prompt_allocation", 5_000),
        safety_margin=data.get("safety_margin", 0.20),
        current_usage=data.get("current_usage", 0),
        tool_results_tokens=data.get("tool_results_tokens", 0),
    )


def _deserialize_ralph_state(data: dict[str, Any]) -> RalphState:
    """Deserialize RalphState from a dict."""
    return RalphState(
        project_root=Path(data["project_root"]),
        current_phase=Phase(data.get("current_phase", "building")),
        iteration_count=data.get("iteration_count", 0),
        session_iteration_count=data.get("session_iteration_count", 0),
        session_id=data.get("session_id"),
        total_cost_usd=data.get("total_cost_usd", 0.0),
        total_tokens_used=data.get("total_tokens_used", 0),
        started_at=(
            _iso_to_datetime(data["started_at"]) if data.get("started_at") else datetime.now()
        ),
        last_activity_at=(
            _iso_to_datetime(data["last_activity_at"])
            if data.get("last_activity_at")
            else datetime.now()
        ),
        circuit_breaker=_deserialize_circuit_breaker(data.get("circuit_breaker", {})),
        context_budget=_deserialize_context_budget(data.get("context_budget", {})),
        session_cost_usd=data.get("session_cost_usd", 0.0),
        session_tokens_used=data.get("session_tokens_used", 0),
        tasks_completed_this_session=data.get("tasks_completed_this_session", 0),
        paused=data.get("paused", False),
        completion_signals=data.get("completion_signals", {}),
        pending_memory_update=data.get("pending_memory_update"),
    )


def _deserialize_implementation_plan(data: dict[str, Any]) -> ImplementationPlan:
    """Deserialize ImplementationPlan from a dict."""
    tasks = [_deserialize_task(t) for t in data.get("tasks", [])]
    return ImplementationPlan(
        tasks=tasks,
        created_at=(
            _iso_to_datetime(data["created_at"]) if data.get("created_at") else datetime.now()
        ),
        last_modified=(
            _iso_to_datetime(data["last_modified"])
            if data.get("last_modified")
            else datetime.now()
        ),
    )


def ensure_ralph_dir(project_root: Path) -> Path:
    """Ensure .ralph directory exists and return its path."""
    ralph_dir = project_root / ".ralph"
    ralph_dir.mkdir(parents=True, exist_ok=True)
    return ralph_dir


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Write data to file atomically using temp file + rename.

    This ensures that a crash during write won't corrupt the file.

    Args:
        path: Target file path
        data: Data to write as JSON
    """
    # Write to a temp file in the same directory (same filesystem for atomic rename)
    dir_path = path.parent
    fd, temp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        # Atomic rename (on POSIX systems)
        os.replace(temp_path, path)
    except Exception:
        # Clean up temp file on failure
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def save_state(state: RalphState, project_root: Path | None = None) -> Path:
    """Save RalphState to JSON file atomically.

    Uses atomic write (temp file + rename) to prevent corruption
    if a crash occurs during write.

    Args:
        state: The RalphState to persist
        project_root: Optional project root override (defaults to state.project_root)

    Returns:
        Path to the saved state file

    Raises:
        PersistenceError: If save operation fails
    """
    root = project_root or state.project_root
    ensure_ralph_dir(root)
    state_path = root / STATE_FILE

    try:
        data = _serialize_dataclass(state)
        _atomic_write(state_path, data)
        return state_path
    except (OSError, TypeError) as e:
        raise PersistenceError(f"Failed to save state: {e}") from e


def load_state(project_root: Path) -> RalphState:
    """Load RalphState from JSON file.

    Args:
        project_root: Path to the project root

    Returns:
        Loaded RalphState

    Raises:
        StateNotFoundError: If state file does not exist
        CorruptedStateError: If state file is invalid
    """
    state_path = project_root / STATE_FILE

    if not state_path.exists():
        raise StateNotFoundError(f"State file not found: {state_path}")

    try:
        with open(state_path) as f:
            data = json.load(f)
        return _deserialize_ralph_state(data)
    except json.JSONDecodeError as e:
        raise CorruptedStateError(f"Invalid JSON in state file: {e}") from e
    except (KeyError, ValueError) as e:
        raise CorruptedStateError(f"Invalid state data: {e}") from e


def save_plan(plan: ImplementationPlan, project_root: Path) -> Path:
    """Save ImplementationPlan to JSON file atomically.

    Uses atomic write (temp file + rename) to prevent corruption
    if a crash occurs during write.

    Args:
        plan: The ImplementationPlan to persist
        project_root: Path to the project root

    Returns:
        Path to the saved plan file

    Raises:
        PersistenceError: If save operation fails
    """
    ensure_ralph_dir(project_root)
    plan_path = project_root / PLAN_FILE

    try:
        data = _serialize_dataclass(plan)
        _atomic_write(plan_path, data)
        return plan_path
    except (OSError, TypeError) as e:
        raise PersistenceError(f"Failed to save plan: {e}") from e


def load_plan(project_root: Path) -> ImplementationPlan:
    """Load ImplementationPlan from JSON file.

    Args:
        project_root: Path to the project root

    Returns:
        Loaded ImplementationPlan

    Raises:
        StateNotFoundError: If plan file does not exist
        CorruptedStateError: If plan file is invalid
    """
    plan_path = project_root / PLAN_FILE

    if not plan_path.exists():
        raise StateNotFoundError(f"Plan file not found: {plan_path}")

    try:
        with open(plan_path) as f:
            data = json.load(f)
        return _deserialize_implementation_plan(data)
    except json.JSONDecodeError as e:
        raise CorruptedStateError(f"Invalid JSON in plan file: {e}") from e
    except (KeyError, ValueError) as e:
        raise CorruptedStateError(f"Invalid plan data: {e}") from e


def state_exists(project_root: Path) -> bool:
    """Check if state file exists."""
    return (project_root / STATE_FILE).exists()


def plan_exists(project_root: Path) -> bool:
    """Check if plan file exists."""
    return (project_root / PLAN_FILE).exists()


def initialize_state(project_root: Path) -> RalphState:
    """Create and save a new RalphState.

    Args:
        project_root: Path to the project root

    Returns:
        Newly created RalphState
    """
    state = RalphState(project_root=project_root)
    save_state(state, project_root)
    return state


def initialize_plan(project_root: Path) -> ImplementationPlan:
    """Create and save a new ImplementationPlan.

    Args:
        project_root: Path to the project root

    Returns:
        Newly created ImplementationPlan
    """
    plan = ImplementationPlan()
    save_plan(plan, project_root)
    return plan


def load_memory(project_root: Path) -> str | None:
    """Load memory content from .ralph/MEMORY.md.

    Args:
        project_root: Path to the project root

    Returns:
        Memory content if file exists, None otherwise
    """
    memory_path = project_root / MEMORY_FILE
    if memory_path.exists():
        return memory_path.read_text()
    return None


def save_memory(content: str, project_root: Path) -> Path:
    """Save memory content to .ralph/MEMORY.md.

    Args:
        content: Memory content to save
        project_root: Path to the project root

    Returns:
        Path to the saved memory file
    """
    ensure_ralph_dir(project_root)
    memory_path = project_root / MEMORY_FILE
    memory_path.write_text(content)
    return memory_path


def memory_exists(project_root: Path) -> bool:
    """Check if memory file exists."""
    return (project_root / MEMORY_FILE).exists()
