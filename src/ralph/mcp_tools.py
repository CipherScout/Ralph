"""MCP tools for Ralph orchestrator using Claude Agent SDK format.

Exposes Ralph's state management tools via MCP using the @tool decorator
format expected by the Claude Agent SDK.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from ralph.tools import RalphTools, ToolResult

# Validation constants
TASK_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
MAX_TASK_ID_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 5000
MAX_LEARNING_LENGTH = 2000
MAX_MEMORY_CONTENT_LENGTH = 10_000
VALID_CATEGORIES = {"pattern", "antipattern", "architecture", "debugging", "build"}
VALID_MEMORY_MODES = {"replace", "append"}


class ValidationError(Exception):
    """Raised when input validation fails."""

    pass


def _validate_task_id(task_id: Any) -> str:
    """Validate and return task ID."""
    if not isinstance(task_id, str):
        raise ValidationError(f"task_id must be a string, got {type(task_id).__name__}")
    if not task_id or not task_id.strip():
        raise ValidationError("task_id cannot be empty")
    validated_id: str = task_id.strip()
    if len(validated_id) > MAX_TASK_ID_LENGTH:
        raise ValidationError(f"task_id too long (max {MAX_TASK_ID_LENGTH} chars)")
    if not TASK_ID_PATTERN.match(validated_id):
        raise ValidationError(
            "task_id must contain only alphanumeric chars, hyphens, and underscores"
        )
    return validated_id


def _validate_tokens_used(tokens_used: Any) -> int | None:
    """Validate and return tokens_used."""
    if tokens_used is None:
        return None
    validated_tokens: int
    if not isinstance(tokens_used, int):
        try:
            validated_tokens = int(tokens_used)
        except (ValueError, TypeError) as e:
            raise ValidationError(f"tokens_used must be an integer: {e}") from e
    else:
        validated_tokens = tokens_used
    if validated_tokens < 0:
        raise ValidationError("tokens_used cannot be negative")
    if validated_tokens > 10_000_000:
        raise ValidationError("tokens_used value unreasonably large")
    return validated_tokens


def _validate_priority(priority: Any) -> int:
    """Validate and return priority."""
    validated_priority: int
    if not isinstance(priority, int):
        try:
            validated_priority = int(priority)
        except (ValueError, TypeError) as e:
            raise ValidationError(f"priority must be an integer: {e}") from e
    else:
        validated_priority = priority
    if validated_priority < 1:
        raise ValidationError("priority must be at least 1")
    if validated_priority > 1000:
        raise ValidationError("priority too high (max 1000)")
    return validated_priority


def _validate_category(category: Any) -> str:
    """Validate and return learning category."""
    if not isinstance(category, str):
        raise ValidationError(f"category must be a string, got {type(category).__name__}")
    validated_category: str = category.lower().strip()
    if validated_category not in VALID_CATEGORIES:
        valid_list = ", ".join(sorted(VALID_CATEGORIES))
        raise ValidationError(f"category must be one of: {valid_list}")
    return validated_category


def _validate_dependencies(dependencies: Any) -> list[str] | None:
    """Validate and normalize dependencies to a list of task IDs."""
    if dependencies is None:
        return None

    # Handle comma-separated string
    if isinstance(dependencies, str):
        if not dependencies.strip():
            return None
        # Split by comma and validate each
        dep_list = [d.strip() for d in dependencies.split(",") if d.strip()]
        if not dep_list:
            return None
        dependencies = dep_list

    if not isinstance(dependencies, list):
        raise ValidationError(
            f"dependencies must be a list or comma-separated string, "
            f"got {type(dependencies).__name__}"
        )

    validated: list[str] = []
    for dep in dependencies:
        validated.append(_validate_task_id(dep))

    return validated if validated else None


def _validate_verification_criteria(criteria: Any) -> list[str] | None:
    """Validate and normalize verification criteria to a list of strings."""
    if criteria is None:
        return None

    if isinstance(criteria, str):
        if not criteria.strip():
            return None
        return [criteria.strip()]

    if not isinstance(criteria, list):
        raise ValidationError(
            f"verification_criteria must be a list or string, got {type(criteria).__name__}"
        )

    validated: list[str] = []
    for item in criteria:
        if not isinstance(item, str):
            raise ValidationError(
                f"Each verification criterion must be a string, got {type(item).__name__}"
            )
        if item.strip():
            validated.append(item.strip())

    return validated if validated else None


def _validate_spec_files(spec_files: Any) -> list[str] | None:
    """Validate and normalize spec_files to a list of file paths."""
    if spec_files is None:
        return None

    # Handle comma-separated string
    if isinstance(spec_files, str):
        if not spec_files.strip():
            return None
        spec_list = [s.strip() for s in spec_files.split(",") if s.strip()]
        if not spec_list:
            return None
        spec_files = spec_list

    if not isinstance(spec_files, list):
        raise ValidationError(
            f"spec_files must be a list or comma-separated string, "
            f"got {type(spec_files).__name__}"
        )

    validated: list[str] = []
    for spec in spec_files:
        if not isinstance(spec, str):
            raise ValidationError(
                f"Each spec file must be a string, got {type(spec).__name__}"
            )
        if spec.strip():
            validated.append(spec.strip())

    return validated if validated else None


# Global tools instance - will be set by create_ralph_mcp_server
_ralph_tools: RalphTools | None = None


def _format_result(result: ToolResult) -> dict[str, Any]:
    """Format a ToolResult for MCP response."""
    if result.success:
        if result.data:
            text = f"{result.content}\n\n{json.dumps(result.data, indent=2)}"
        else:
            text = result.content
        return {"content": [{"type": "text", "text": text}]}
    else:
        error_text = f"Error: {result.content}"
        if result.error:
            error_text += f"\nDetails: {result.error}"
        return {"content": [{"type": "text", "text": error_text}], "is_error": True}


def _get_tools() -> RalphTools:
    """Get the global RalphTools instance."""
    if _ralph_tools is None:
        raise RuntimeError("Ralph MCP tools not initialized. Call create_ralph_mcp_server first.")
    return _ralph_tools


@tool(
    "ralph_get_next_task",
    "Get the highest-priority incomplete task from the implementation plan",
    {},
)
async def ralph_get_next_task(args: dict[str, Any]) -> dict[str, Any]:
    """Get the next task to work on."""
    tools = _get_tools()
    result = tools.get_next_task()
    return _format_result(result)


@tool(
    "ralph_mark_task_complete",
    "Mark a task as completed with optional verification notes",
    {
        "task_id": str,
        "verification_notes": str,
        "tokens_used": int,
    },
)
async def ralph_mark_task_complete(args: dict[str, Any]) -> dict[str, Any]:
    """Mark a task as complete."""
    try:
        task_id = _validate_task_id(args.get("task_id"))
        tokens_used = _validate_tokens_used(args.get("tokens_used"))
    except ValidationError as e:
        return {"content": [{"type": "text", "text": f"Validation error: {e}"}], "is_error": True}

    tools = _get_tools()
    result = tools.mark_task_complete(
        task_id=task_id,
        verification_notes=args.get("verification_notes"),
        tokens_used=tokens_used,
    )
    return _format_result(result)


@tool(
    "ralph_mark_task_blocked",
    "Mark a task as blocked with a reason",
    {
        "task_id": str,
        "reason": str,
    },
)
async def ralph_mark_task_blocked(args: dict[str, Any]) -> dict[str, Any]:
    """Mark a task as blocked."""
    try:
        task_id = _validate_task_id(args.get("task_id"))
        reason = args.get("reason", "")
        if not reason or not str(reason).strip():
            raise ValidationError("reason cannot be empty")
    except ValidationError as e:
        return {"content": [{"type": "text", "text": f"Validation error: {e}"}], "is_error": True}

    tools = _get_tools()
    result = tools.mark_task_blocked(
        task_id=task_id,
        reason=str(reason).strip(),
    )
    return _format_result(result)


@tool(
    "ralph_mark_task_in_progress",
    "Mark a task as in progress",
    {
        "task_id": str,
    },
)
async def ralph_mark_task_in_progress(args: dict[str, Any]) -> dict[str, Any]:
    """Mark a task as in progress."""
    try:
        task_id = _validate_task_id(args.get("task_id"))
    except ValidationError as e:
        return {"content": [{"type": "text", "text": f"Validation error: {e}"}], "is_error": True}

    tools = _get_tools()
    result = tools.mark_task_in_progress(task_id=task_id)
    return _format_result(result)


@tool(
    "ralph_append_learning",
    "Record a learning for future iterations (patterns, antipatterns, debugging insights)",
    {
        "learning": str,
        "category": str,
    },
)
async def ralph_append_learning(args: dict[str, Any]) -> dict[str, Any]:
    """Append a learning to progress.txt."""
    try:
        learning = args.get("learning", "")
        if not learning or not str(learning).strip():
            raise ValidationError("learning cannot be empty")
        learning = str(learning).strip()
        if len(learning) > MAX_LEARNING_LENGTH:
            raise ValidationError(f"learning too long (max {MAX_LEARNING_LENGTH} chars)")
        category = _validate_category(args.get("category", "pattern"))
    except ValidationError as e:
        return {"content": [{"type": "text", "text": f"Validation error: {e}"}], "is_error": True}

    tools = _get_tools()
    result = tools.append_learning(
        learning=learning,
        category=category,
    )
    return _format_result(result)


@tool(
    "ralph_get_plan_summary",
    "Get a summary of the current implementation plan including task counts and next task",
    {},
)
async def ralph_get_plan_summary(args: dict[str, Any]) -> dict[str, Any]:
    """Get plan summary."""
    tools = _get_tools()
    result = tools.get_plan_summary()
    return _format_result(result)


@tool(
    "ralph_get_state_summary",
    "Get a summary of current Ralph state including phase, costs, and circuit breaker status",
    {},
)
async def ralph_get_state_summary(args: dict[str, Any]) -> dict[str, Any]:
    """Get state summary."""
    tools = _get_tools()
    result = tools.get_state_summary()
    return _format_result(result)


@tool(
    "ralph_add_task",
    "Add a new task to the implementation plan",
    {
        "task_id": str,
        "description": str,
        "priority": int,
        "dependencies": list,
        "verification_criteria": list,
        "estimated_tokens": int,
        "spec_files": list,
    },
)
async def ralph_add_task(args: dict[str, Any]) -> dict[str, Any]:
    """Add a new task to the plan."""
    try:
        task_id = _validate_task_id(args.get("task_id"))
        description = args.get("description", "")
        if not description or not str(description).strip():
            raise ValidationError("description cannot be empty")
        description = str(description).strip()
        if len(description) > MAX_DESCRIPTION_LENGTH:
            raise ValidationError(f"description too long (max {MAX_DESCRIPTION_LENGTH} chars)")
        priority = _validate_priority(args.get("priority"))
        estimated_tokens = _validate_tokens_used(args.get("estimated_tokens", 30_000)) or 30_000
        dependencies = _validate_dependencies(args.get("dependencies"))
        verification_criteria = _validate_verification_criteria(args.get("verification_criteria"))
        spec_files = _validate_spec_files(args.get("spec_files"))
    except ValidationError as e:
        return {"content": [{"type": "text", "text": f"Validation error: {e}"}], "is_error": True}

    tools = _get_tools()
    result = tools.add_task(
        task_id=task_id,
        description=description,
        priority=priority,
        dependencies=dependencies,
        verification_criteria=verification_criteria,
        estimated_tokens=estimated_tokens,
        spec_files=spec_files,
    )
    return _format_result(result)


@tool(
    "ralph_increment_retry",
    "Increment the retry count for a task and reset it to pending status",
    {
        "task_id": str,
    },
)
async def ralph_increment_retry(args: dict[str, Any]) -> dict[str, Any]:
    """Increment retry count for a task."""
    try:
        task_id = _validate_task_id(args.get("task_id"))
    except ValidationError as e:
        return {"content": [{"type": "text", "text": f"Validation error: {e}"}], "is_error": True}

    tools = _get_tools()
    result = tools.increment_retry(task_id=task_id)
    return _format_result(result)


@tool(
    "ralph_validate_discovery_outputs",
    (
        "Validate that all required discovery outputs exist. "
        "Call this BEFORE signaling completion to verify PRD.md, SPEC files, "
        "and TECHNICAL_ARCHITECTURE.md are all present."
    ),
    {},
)
async def ralph_validate_discovery_outputs(args: dict[str, Any]) -> dict[str, Any]:
    """Validate discovery phase outputs exist."""
    tools = _get_tools()
    project_root = tools.project_root
    specs_dir = project_root / "specs"

    results: dict[str, Any] = {
        "prd_exists": False,
        "architecture_exists": False,
        "spec_files": [],
        "all_valid": False,
    }

    if specs_dir.exists():
        results["prd_exists"] = (specs_dir / "PRD.md").exists()
        results["architecture_exists"] = (specs_dir / "TECHNICAL_ARCHITECTURE.md").exists()
        results["spec_files"] = [f.name for f in specs_dir.glob("SPEC-*.md")]

    results["all_valid"] = (
        results["prd_exists"]
        and results["architecture_exists"]
        and len(results["spec_files"]) > 0
    )

    if results["all_valid"]:
        content = (
            f"All required documents exist:\n"
            f"- specs/PRD.md: EXISTS\n"
            f"- specs/TECHNICAL_ARCHITECTURE.md: EXISTS\n"
            f"- SPEC files: {len(results['spec_files'])} found "
            f"({', '.join(results['spec_files'])})\n\n"
            f"You may now call ralph_signal_discovery_complete."
        )
        return {"content": [{"type": "text", "text": content}]}
    else:
        missing = []
        if not results["prd_exists"]:
            missing.append("specs/PRD.md")
        if not results["architecture_exists"]:
            missing.append("specs/TECHNICAL_ARCHITECTURE.md")
        if not results["spec_files"]:
            missing.append("specs/SPEC-NNN-*.md (at least one)")
        content = (
            f"MISSING DOCUMENTS - Cannot signal completion yet:\n"
            f"- {chr(10).join(f'  - {m}' for m in missing)}\n\n"
            f"Create the missing documents before signaling completion."
        )
        return {"content": [{"type": "text", "text": content}], "is_error": True}


@tool(
    "ralph_signal_discovery_complete",
    (
        "Signal discovery phase complete. Call ONLY when all required documents exist: "
        "PRD.md, at least one SPEC-NNN-*.md file, and TECHNICAL_ARCHITECTURE.md. "
        "Use ralph_validate_discovery_outputs first to verify."
    ),
    {
        "summary": str,
        "specs_created": list,
        "prd_created": bool,
        "architecture_created": bool,
    },
)
async def ralph_signal_discovery_complete(args: dict[str, Any]) -> dict[str, Any]:
    """Signal that discovery phase is complete with validation."""
    tools = _get_tools()
    summary = args.get("summary", "Discovery complete")
    specs = args.get("specs_created", [])
    prd_created = args.get("prd_created", False)
    architecture_created = args.get("architecture_created", False)

    # Validation warnings (non-blocking, but logged)
    warnings: list[str] = []
    if not prd_created:
        warnings.append("Warning: PRD.md not confirmed as created (prd_created=false)")
    if not architecture_created:
        warnings.append(
            "Warning: TECHNICAL_ARCHITECTURE.md not confirmed as created "
            "(architecture_created=false)"
        )
    if not specs or len(specs) == 0:
        warnings.append("Warning: No SPEC files confirmed as created (specs_created empty)")

    # Update state to signal completion with validation info
    result = tools.signal_phase_complete(
        phase="discovery",
        summary=str(summary),
        artifacts={
            "specs_created": specs,
            "prd_created": prd_created,
            "architecture_created": architecture_created,
            "validation_warnings": warnings,
        },
    )
    return _format_result(result)


@tool(
    "ralph_signal_planning_complete",
    "Signal planning phase complete. Call when implementation plan is ready with all tasks.",
    {
        "summary": str,
        "task_count": int,
    },
)
async def ralph_signal_planning_complete(args: dict[str, Any]) -> dict[str, Any]:
    """Signal that planning phase is complete."""
    tools = _get_tools()
    summary = args.get("summary", "Planning complete")
    task_count = args.get("task_count", 0)

    result = tools.signal_phase_complete(
        phase="planning",
        summary=str(summary),
        artifacts={"task_count": task_count},
    )
    return _format_result(result)


@tool(
    "ralph_signal_building_complete",
    "Signal that the building phase is complete. Call this when all implementation tasks are done.",
    {
        "summary": str,
        "tasks_completed": int,
    },
)
async def ralph_signal_building_complete(args: dict[str, Any]) -> dict[str, Any]:
    """Signal that building phase is complete."""
    tools = _get_tools()
    summary = args.get("summary", "Building complete")
    tasks_completed = args.get("tasks_completed", 0)

    result = tools.signal_phase_complete(
        phase="building",
        summary=str(summary),
        artifacts={"tasks_completed": tasks_completed},
    )
    return _format_result(result)


@tool(
    "ralph_signal_validation_complete",
    "Signal that the validation phase is complete. Call this when all verification is done.",
    {
        "summary": str,
        "passed": bool,
        "issues": list,
    },
)
async def ralph_signal_validation_complete(args: dict[str, Any]) -> dict[str, Any]:
    """Signal that validation phase is complete."""
    tools = _get_tools()
    summary = args.get("summary", "Validation complete")
    passed = args.get("passed", True)
    issues = args.get("issues", [])

    result = tools.signal_phase_complete(
        phase="validation",
        summary=str(summary),
        artifacts={"passed": passed, "issues": issues},
    )
    return _format_result(result)


@tool(
    "ralph_update_memory",
    (
        "Update session memory for future sessions. Content is written to .ralph/MEMORY.md "
        "after the iteration completes. Use 'replace' mode to overwrite all memory, "
        "'append' mode to add to existing memory."
    ),
    {
        "content": str,
        "mode": str,
    },
)
async def ralph_update_memory(args: dict[str, Any]) -> dict[str, Any]:
    """Queue a memory update for end of iteration."""
    try:
        content = args.get("content", "")
        if not isinstance(content, str):
            raise ValidationError(f"content must be a string, got {type(content).__name__}")
        if not content.strip():
            raise ValidationError("content cannot be empty")
        content = content.strip()
        if len(content) > MAX_MEMORY_CONTENT_LENGTH:
            raise ValidationError(f"content too long (max {MAX_MEMORY_CONTENT_LENGTH} chars)")

        mode = args.get("mode", "append")
        if not isinstance(mode, str):
            raise ValidationError(f"mode must be a string, got {type(mode).__name__}")
        mode = mode.lower().strip()
        if mode not in VALID_MEMORY_MODES:
            raise ValidationError(f"mode must be one of: {', '.join(VALID_MEMORY_MODES)}")
    except ValidationError as e:
        return {"content": [{"type": "text", "text": f"Validation error: {e}"}], "is_error": True}

    tools = _get_tools()
    result = tools.update_memory(content=content, mode=mode)
    return _format_result(result)


# List of all Ralph tools
RALPH_MCP_TOOLS = [
    ralph_get_next_task,
    ralph_mark_task_complete,
    ralph_mark_task_blocked,
    ralph_mark_task_in_progress,
    ralph_append_learning,
    ralph_get_plan_summary,
    ralph_get_state_summary,
    ralph_add_task,
    ralph_increment_retry,
    ralph_validate_discovery_outputs,
    ralph_signal_discovery_complete,
    ralph_signal_planning_complete,
    ralph_signal_building_complete,
    ralph_signal_validation_complete,
    ralph_update_memory,
]


def create_ralph_mcp_server(project_root: Path) -> Any:
    """Create an MCP server with all Ralph tools.

    Args:
        project_root: Path to the project root directory

    Returns:
        SDK MCP server instance
    """
    global _ralph_tools
    _ralph_tools = RalphTools(project_root)

    return create_sdk_mcp_server(
        name="ralph",
        version="0.1.0",
        tools=RALPH_MCP_TOOLS,
    )


def get_ralph_tool_names(server_name: str = "ralph") -> list[str]:
    """Get the allowed tool names for Ralph MCP tools.

    Args:
        server_name: The name used for the MCP server

    Returns:
        List of fully qualified tool names (mcp__{server}__{tool})
    """
    tool_base_names = [
        "ralph_get_next_task",
        "ralph_mark_task_complete",
        "ralph_mark_task_blocked",
        "ralph_mark_task_in_progress",
        "ralph_append_learning",
        "ralph_get_plan_summary",
        "ralph_get_state_summary",
        "ralph_add_task",
        "ralph_increment_retry",
        "ralph_validate_discovery_outputs",
        "ralph_signal_discovery_complete",
        "ralph_signal_planning_complete",
        "ralph_signal_building_complete",
        "ralph_signal_validation_complete",
        "ralph_update_memory",
    ]
    return [f"mcp__{server_name}__{name}" for name in tool_base_names]
