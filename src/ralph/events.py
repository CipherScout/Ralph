"""Event streaming infrastructure for Ralph orchestrator.

This module defines the event types and data structures used to stream
real-time updates from Ralph's agentic loop to the CLI and other consumers.

The event streaming architecture transforms Ralph from a callback-based system
that only reports at iteration boundaries into a fully transparent system that
yields events as they happen, enabling real-time display and user interaction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal


class StreamEventType(str, Enum):
    """Types of events that can be streamed from Ralph's execution.

    Events are categorized into:
    - Lifecycle: Iteration and phase management
    - LLM Output: Text and thinking from the model
    - Tool Events: Tool invocations and results
    - User Interaction: Questions requiring user input
    - Task Events: Task status changes
    - Context Events: Session and handoff management
    - Error Events: Warnings and errors
    """

    # Lifecycle events
    ITERATION_START = "iteration_start"
    ITERATION_END = "iteration_end"
    PHASE_CHANGE = "phase_change"

    # LLM output events
    TEXT_DELTA = "text_delta"  # Streaming text chunk

    # Tool events
    TOOL_USE_START = "tool_use_start"  # Tool invocation begins
    TOOL_USE_END = "tool_use_end"  # Tool invocation completes
    TOOL_RESULT = "tool_result"  # Tool result received

    # User interaction events (critical for discovery phase)
    NEEDS_INPUT = "needs_input"  # AskUserQuestion tool called

    # Task events
    TASK_COMPLETE = "task_complete"  # Task marked complete
    TASK_BLOCKED = "task_blocked"  # Task blocked

    # Subagent events
    SUBAGENT_START = "subagent_start"  # Subagent starting execution
    SUBAGENT_END = "subagent_end"  # Subagent finished execution

    # Context events
    HANDOFF_START = "handoff_start"  # Context handoff starting
    HANDOFF_COMPLETE = "handoff_complete"  # Handoff finished

    # Error events
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    # Context budget events (SPEC-005)
    CONTEXT_WARNING = "context_warning"  # Approaching context limit
    CONTEXT_EMERGENCY = "context_emergency"  # At emergency limit


@dataclass
class StreamEvent:
    """A single event in the Ralph event stream.

    Events are yielded by async generators throughout the system, allowing
    real-time display and user interaction. The event carries all necessary
    data for the CLI or other consumers to handle it appropriately.

    Attributes:
        type: The type of event (from StreamEventType enum)
        data: Arbitrary event-specific data dictionary
        timestamp: When the event occurred
        text: For TEXT_DELTA events, the text content
        tool_name: For tool events, the name of the tool
        tool_input: For TOOL_USE_START, the tool's input parameters
        tool_result: For TOOL_RESULT, the tool's output
        tool_id: For tool events, the unique tool use ID
        question: For NEEDS_INPUT, the question text
        options: For NEEDS_INPUT, available answer options
        task_id: For task events, the task identifier
        error_message: For ERROR events, the error description
        phase: For phase-related events, the phase name
        iteration: For iteration events, the iteration number
    """

    type: StreamEventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    # Text streaming fields
    text: str | None = None

    # Tool event fields
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_result: Any | None = None
    tool_id: str | None = None

    # User interaction fields
    question: str | None = None
    options: list[dict[str, Any]] | None = None

    # Task event fields
    task_id: str | None = None

    # Error fields
    error_message: str | None = None

    # Context fields
    phase: str | None = None
    iteration: int | None = None
    session_id: str | None = None

    # Token usage and cost fields
    token_usage: int | None = None
    cost_usd: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary for serialization."""
        result: dict[str, Any] = {
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
        }

        # Add non-None optional fields
        if self.text is not None:
            result["text"] = self.text
        if self.tool_name is not None:
            result["tool_name"] = self.tool_name
        if self.tool_input is not None:
            result["tool_input"] = self.tool_input
        if self.tool_result is not None:
            result["tool_result"] = self.tool_result
        if self.tool_id is not None:
            result["tool_id"] = self.tool_id
        if self.question is not None:
            result["question"] = self.question
        if self.options is not None:
            result["options"] = self.options
        if self.task_id is not None:
            result["task_id"] = self.task_id
        if self.error_message is not None:
            result["error_message"] = self.error_message
        if self.phase is not None:
            result["phase"] = self.phase
        if self.iteration is not None:
            result["iteration"] = self.iteration
        if self.session_id is not None:
            result["session_id"] = self.session_id
        if self.token_usage is not None:
            result["token_usage"] = self.token_usage
        if self.cost_usd is not None:
            result["cost_usd"] = self.cost_usd

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StreamEvent:
        """Create event from dictionary."""
        event_type = StreamEventType(data["type"])
        timestamp = datetime.fromisoformat(data["timestamp"])

        return cls(
            type=event_type,
            timestamp=timestamp,
            data=data.get("data", {}),
            text=data.get("text"),
            tool_name=data.get("tool_name"),
            tool_input=data.get("tool_input"),
            tool_result=data.get("tool_result"),
            tool_id=data.get("tool_id"),
            question=data.get("question"),
            options=data.get("options"),
            task_id=data.get("task_id"),
            error_message=data.get("error_message"),
            phase=data.get("phase"),
            iteration=data.get("iteration"),
            session_id=data.get("session_id"),
            token_usage=data.get("token_usage"),
            cost_usd=data.get("cost_usd"),
        )


# Subagent type definitions
SubagentType = Literal[
    "research-specialist",
    "code-reviewer",
    "test-engineer",
    "documentation-agent",
    "product-analyst"
]


@dataclass
class SubagentStartEvent:
    """Event data for subagent lifecycle start.

    Tracks when a subagent begins execution with its assigned task.

    Attributes:
        subagent_type: Type of subagent being started (using Literal type annotation)
        task_description: Description of the task assigned to the subagent
    """
    subagent_type: SubagentType
    task_description: str


@dataclass
class SubagentEndEvent:
    """Event data for subagent lifecycle end.

    Tracks when a subagent completes execution with results.

    Attributes:
        subagent_type: Type of subagent that finished (using Literal type annotation)
        success: Whether the subagent completed successfully
        report_length: Length of the subagent's report/output in characters
    """
    subagent_type: SubagentType
    success: bool
    report_length: int


# Factory functions for common event types


def iteration_start_event(
    iteration: int,
    phase: str,
    session_id: str | None = None,
    task_id: str | None = None,
    **extra_data: Any,
) -> StreamEvent:
    """Create an ITERATION_START event."""
    return StreamEvent(
        type=StreamEventType.ITERATION_START,
        iteration=iteration,
        phase=phase,
        session_id=session_id,
        task_id=task_id,
        data=extra_data,
    )


def iteration_end_event(
    iteration: int,
    phase: str,
    success: bool,
    tokens_used: int = 0,
    cost_usd: float = 0.0,
    **extra_data: Any,
) -> StreamEvent:
    """Create an ITERATION_END event."""
    return StreamEvent(
        type=StreamEventType.ITERATION_END,
        iteration=iteration,
        phase=phase,
        token_usage=tokens_used,
        cost_usd=cost_usd,
        data={
            "success": success,
            "tokens_used": tokens_used,
            "cost_usd": cost_usd,
            **extra_data,
        },
    )


def text_delta_event(text: str) -> StreamEvent:
    """Create a TEXT_DELTA event for streaming text."""
    return StreamEvent(
        type=StreamEventType.TEXT_DELTA,
        text=text,
    )


def tool_start_event(
    tool_name: str,
    tool_input: dict[str, Any] | None = None,
    tool_id: str | None = None,
) -> StreamEvent:
    """Create a TOOL_USE_START event."""
    return StreamEvent(
        type=StreamEventType.TOOL_USE_START,
        tool_name=tool_name,
        tool_input=tool_input,
        tool_id=tool_id,
    )


def tool_end_event(
    tool_name: str,
    tool_result: Any = None,
    tool_id: str | None = None,
    success: bool = True,
) -> StreamEvent:
    """Create a TOOL_USE_END event."""
    return StreamEvent(
        type=StreamEventType.TOOL_USE_END,
        tool_name=tool_name,
        tool_result=tool_result,
        tool_id=tool_id,
        data={"success": success},
    )


def needs_input_event(
    question: str,
    options: list[dict[str, Any]] | None = None,
    tool_id: str | None = None,
) -> StreamEvent:
    """Create a NEEDS_INPUT event for AskUserQuestion tool."""
    return StreamEvent(
        type=StreamEventType.NEEDS_INPUT,
        question=question,
        options=options,
        tool_id=tool_id,
    )


def task_complete_event(
    task_id: str,
    verification_notes: str | None = None,
) -> StreamEvent:
    """Create a TASK_COMPLETE event."""
    return StreamEvent(
        type=StreamEventType.TASK_COMPLETE,
        task_id=task_id,
        data={"verification_notes": verification_notes} if verification_notes else {},
    )


def task_blocked_event(
    task_id: str,
    reason: str,
) -> StreamEvent:
    """Create a TASK_BLOCKED event."""
    return StreamEvent(
        type=StreamEventType.TASK_BLOCKED,
        task_id=task_id,
        data={"reason": reason},
    )


def error_event(
    message: str,
    error_type: str | None = None,
    **extra_data: Any,
) -> StreamEvent:
    """Create an ERROR event."""
    return StreamEvent(
        type=StreamEventType.ERROR,
        error_message=message,
        data={"error_type": error_type, **extra_data} if error_type else extra_data,
    )


def warning_event(message: str, **extra_data: Any) -> StreamEvent:
    """Create a WARNING event."""
    return StreamEvent(
        type=StreamEventType.WARNING,
        error_message=message,
        data=extra_data,
    )


def info_event(message: str, **extra_data: Any) -> StreamEvent:
    """Create an INFO event."""
    return StreamEvent(
        type=StreamEventType.INFO,
        data={"message": message, **extra_data},
    )


def phase_change_event(
    old_phase: str,
    new_phase: str,
) -> StreamEvent:
    """Create a PHASE_CHANGE event."""
    return StreamEvent(
        type=StreamEventType.PHASE_CHANGE,
        phase=new_phase,
        data={"old_phase": old_phase, "new_phase": new_phase},
    )


def handoff_start_event(
    reason: str,
    session_id: str | None = None,
) -> StreamEvent:
    """Create a HANDOFF_START event."""
    return StreamEvent(
        type=StreamEventType.HANDOFF_START,
        session_id=session_id,
        data={"reason": reason},
    )


def handoff_complete_event(
    new_session_id: str,
    memory_path: str | None = None,
) -> StreamEvent:
    """Create a HANDOFF_COMPLETE event."""
    return StreamEvent(
        type=StreamEventType.HANDOFF_COMPLETE,
        session_id=new_session_id,
        data={"memory_path": memory_path} if memory_path else {},
    )


def context_warning_event(
    usage_percent: float,
    current_tokens: int,
    threshold_percent: float = 80.0,
) -> StreamEvent:
    """Create a CONTEXT_WARNING event when approaching limit (SPEC-005).

    Args:
        usage_percent: Current context usage as percentage
        current_tokens: Current token count
        threshold_percent: The handoff threshold percentage (default 80%)

    Returns:
        StreamEvent with context warning information
    """
    return StreamEvent(
        type=StreamEventType.CONTEXT_WARNING,
        data={
            "usage_percent": usage_percent,
            "current_tokens": current_tokens,
            "threshold_percent": threshold_percent,
            "message": (
                f"Context at {usage_percent:.1f}% - "
                f"approaching {threshold_percent:.0f}% limit"
            ),
        },
    )


def context_emergency_event(
    usage_percent: float,
    current_tokens: int,
) -> StreamEvent:
    """Create a CONTEXT_EMERGENCY event at critical limit (SPEC-005).

    Args:
        usage_percent: Current context usage as percentage
        current_tokens: Current token count

    Returns:
        StreamEvent with emergency context information
    """
    return StreamEvent(
        type=StreamEventType.CONTEXT_EMERGENCY,
        data={
            "usage_percent": usage_percent,
            "current_tokens": current_tokens,
            "message": f"Emergency: Context at {usage_percent:.1f}% - forcing handoff",
        },
    )


def subagent_start_event(
    subagent_type: SubagentType,
    task_description: str,
) -> StreamEvent:
    """Create a SUBAGENT_START event for tracking subagent lifecycle.

    Args:
        subagent_type: Type of subagent being started
        task_description: Description of the task assigned to the subagent

    Returns:
        StreamEvent with subagent start information
    """
    return StreamEvent(
        type=StreamEventType.SUBAGENT_START,
        data={
            "subagent_type": subagent_type,
            "task_description": task_description,
        },
    )


def subagent_end_event(
    subagent_type: SubagentType,
    success: bool,
    report_length: int,
) -> StreamEvent:
    """Create a SUBAGENT_END event for tracking subagent lifecycle.

    Args:
        subagent_type: Type of subagent that finished
        success: Whether the subagent completed successfully
        report_length: Length of the subagent's report/output in characters

    Returns:
        StreamEvent with subagent end information
    """
    return StreamEvent(
        type=StreamEventType.SUBAGENT_END,
        data={
            "subagent_type": subagent_type,
            "success": success,
            "report_length": report_length,
        },
    )
