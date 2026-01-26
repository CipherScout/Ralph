"""Claude Agent SDK client wrapper for Ralph orchestrator.

Provides a high-level interface to ClaudeSDKClient that integrates with
Ralph's phase-based architecture, tool allocation, and safety hooks.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    Message,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    query,
)
from claude_agent_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from ralph.events import (
    StreamEvent,
    error_event,
    iteration_end_event,
    iteration_start_event,
    task_blocked_event,
    task_complete_event,
    text_delta_event,
    tool_end_event,
    tool_start_event,
    warning_event,
)
from ralph.models import Phase, RalphState

if TYPE_CHECKING:
    from ralph.config import RalphConfig

logger = logging.getLogger(__name__)


# Lazy imports to avoid circular dependencies
def _get_mcp_server(project_root: Path) -> Any:
    """Lazy import MCP server to avoid circular imports."""
    from ralph.mcp_tools import create_ralph_mcp_server

    return create_ralph_mcp_server(project_root)


def _get_ralph_hooks(state: RalphState, config: Any | None = None) -> dict[str, list[Any]]:
    """Lazy import hooks to avoid circular imports."""
    from ralph.sdk_hooks import get_ralph_hooks

    max_cost = 2.0
    if config is not None:
        max_cost = config.cost_limits.per_iteration
    return get_ralph_hooks(state, max_cost_per_iteration=max_cost)


async def _handle_ask_user_question(
    input_data: dict[str, Any],
) -> PermissionResultAllow:
    """Handle AskUserQuestion tool by displaying questions and collecting answers.

    This follows the SDK's documented pattern for handling user input tools.
    The answers are returned via updated_input so Claude receives them.
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt

    console = Console()
    answers: dict[str, str] = {}

    questions = input_data.get("questions", [])
    for q in questions:
        header = q.get("header", "Question")
        question_text = q.get("question", "Please answer:")
        options = q.get("options", [])
        multi_select = q.get("multiSelect", False)

        # Display question with Rich formatting
        console.print()
        console.print(
            Panel(
                question_text,
                title=f"[bold yellow]{header}[/bold yellow]",
                border_style="yellow",
            )
        )

        # Display options
        for i, opt in enumerate(options, 1):
            if isinstance(opt, dict):
                label = opt.get("label", str(opt))
                desc = opt.get("description", "")
                if desc:
                    console.print(f"  {i}. {label} [dim]- {desc}[/dim]")
                else:
                    console.print(f"  {i}. {label}")
            else:
                console.print(f"  {i}. {opt}")

        # Show input hint
        if multi_select:
            console.print("  [dim](Enter numbers separated by commas, or type your own)[/dim]")
        else:
            console.print("  [dim](Enter a number, or type your own answer)[/dim]")

        # Get user response
        response = Prompt.ask("[bold]Your answer[/bold]")

        # Parse response - convert number to option label if applicable
        parsed_response = response.strip()
        if parsed_response.isdigit():
            idx = int(parsed_response) - 1
            if 0 <= idx < len(options):
                opt = options[idx]
                parsed_response = opt.get("label", str(opt)) if isinstance(opt, dict) else str(opt)

        answers[question_text] = parsed_response

    # Return with answers in updated_input so Claude receives them
    return PermissionResultAllow(
        updated_input={
            "questions": questions,
            "answers": answers,
        }
    )


async def _default_can_use_tool(
    tool_name: str,
    input_data: dict[str, Any],
    context: ToolPermissionContext,
) -> PermissionResultAllow | PermissionResultDeny:
    """Default permission callback that handles AskUserQuestion specially.

    For AskUserQuestion, this displays questions and collects user answers.
    For other tools, it allows them (other restrictions are handled by hooks).
    """
    if tool_name == "AskUserQuestion":
        return await _handle_ask_user_question(input_data)

    # Allow other tools (hooks handle restrictions)
    return PermissionResultAllow()


@dataclass
class IterationMetrics:
    """Metrics collected during an iteration."""

    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    session_id: str | None = None


@dataclass
class IterationResult:
    """Result from a single Ralph iteration."""

    success: bool
    task_completed: bool = False
    task_id: str | None = None
    tokens_used: int = 0
    cost_usd: float = 0.0
    needs_handoff: bool = False
    error: str | None = None
    completion_notes: str | None = None
    metrics: IterationMetrics = field(default_factory=IterationMetrics)
    messages: list[Message] = field(default_factory=list)
    final_text: str = ""


# Approximate pricing per 1M tokens (as of 2026)
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
    # Fallback for unknown models
    "default": {"input": 3.0, "output": 15.0},
}


def calculate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Calculate cost based on token usage and model."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["default"])
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return input_cost + output_cost


# Tool allocation by phase
PHASE_TOOLS: dict[Phase, list[str]] = {
    Phase.DISCOVERY: [
        "Read",
        "Glob",
        "Grep",
        "WebSearch",
        "WebFetch",
        "Write",
        "Task",
        "AskUserQuestion",
    ],
    Phase.PLANNING: [
        "Read",
        "Glob",
        "Grep",
        "WebSearch",
        "WebFetch",
        "Write",
        "Task",
        "ExitPlanMode",
    ],
    Phase.BUILDING: [
        "Read",
        "Write",
        "Edit",
        "Bash",
        "BashOutput",
        "KillBash",
        "Glob",
        "Grep",
        "Task",
        "TodoWrite",
        "WebSearch",
        "WebFetch",
        "NotebookEdit",
    ],
    Phase.VALIDATION: [
        "Read",
        "Glob",
        "Grep",
        "Bash",
        "Task",
        "WebFetch",
    ],
}


def get_tools_for_phase(phase: Phase) -> list[str]:
    """Get the list of allowed tools for a phase."""
    return PHASE_TOOLS.get(phase, PHASE_TOOLS[Phase.BUILDING])


def calculate_max_turns(phase: Phase) -> int:
    """Calculate maximum turns for a phase."""
    turn_limits = {
        Phase.DISCOVERY: 50,
        Phase.PLANNING: 30,
        Phase.BUILDING: 100,
        Phase.VALIDATION: 20,
    }
    return turn_limits.get(phase, 50)


def get_model_for_phase(phase: Phase, config: RalphConfig | None = None) -> str:
    """Get the appropriate model for a phase."""
    if config is not None:
        if phase == Phase.PLANNING:
            return config.planning_model
        return config.primary_model
    # Defaults
    if phase == Phase.PLANNING:
        return "claude-opus-4-20250514"
    return "claude-sonnet-4-20250514"


class RalphSDKClient:
    """Claude Agent SDK client wrapper for Ralph.

    Manages Claude SDK sessions with phase-specific configuration,
    tool allocation, hooks, and metrics tracking.
    """

    def __init__(
        self,
        state: RalphState,
        config: RalphConfig | None = None,
        hooks: dict[str, list[HookMatcher]] | None = None,
        mcp_servers: dict[str, Any] | None = None,
        auto_configure: bool = True,
    ) -> None:
        """Initialize the SDK client wrapper.

        Args:
            state: Current Ralph state
            config: Ralph configuration (optional)
            hooks: SDK hooks for tool validation (optional)
            mcp_servers: MCP server configurations (optional)
            auto_configure: Automatically configure hooks and MCP server (default True)
        """
        self.state = state
        self.config = config
        self._session_id: str | None = None

        # Auto-configure hooks and MCP server if not provided
        if auto_configure:
            self.hooks = hooks or _get_ralph_hooks(state, config)
            if mcp_servers is None:
                ralph_mcp = _get_mcp_server(state.project_root)
                self.mcp_servers = {"ralph": ralph_mcp}
            else:
                self.mcp_servers = mcp_servers
        else:
            self.hooks = hooks  # type: ignore[assignment]
            self.mcp_servers = mcp_servers or {}

    def _build_options(
        self,
        phase: Phase | None = None,
        system_prompt: str | None = None,
        max_turns: int | None = None,
    ) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions for the current phase.

        Args:
            phase: Override phase (defaults to state.current_phase)
            system_prompt: Custom system prompt
            max_turns: Override max turns

        Returns:
            Configured ClaudeAgentOptions
        """
        current_phase = phase or self.state.current_phase
        allowed_tools = get_tools_for_phase(current_phase)

        # Add Ralph MCP tools to allowed list if we have an MCP server
        if self.mcp_servers:
            from ralph.mcp_tools import get_ralph_tool_names

            for server_name in self.mcp_servers:
                allowed_tools.extend(get_ralph_tool_names(server_name))

        # Build budget limit if configured
        max_budget_usd: float | None = None
        if self.config:
            max_budget_usd = self.config.cost_limits.per_iteration

        return ClaudeAgentOptions(
            allowed_tools=allowed_tools,
            system_prompt=system_prompt,
            permission_mode="acceptEdits",
            cwd=str(self.state.project_root),
            max_turns=max_turns or calculate_max_turns(current_phase),
            max_budget_usd=max_budget_usd,
            model=get_model_for_phase(current_phase, self.config),
            hooks=self.hooks,  # type: ignore[arg-type]
            mcp_servers=self.mcp_servers,
            setting_sources=["project"],  # Load CLAUDE.md
            resume=self._session_id,  # Resume previous session if available
            can_use_tool=_default_can_use_tool,  # Handle AskUserQuestion
        )

    async def run_iteration(
        self,
        prompt: str,
        phase: Phase | None = None,
        system_prompt: str | None = None,
        max_turns: int | None = None,
    ) -> IterationResult:
        """Execute one iteration of the agentic loop.

        Args:
            prompt: The user prompt to send
            phase: Override phase (defaults to state.current_phase)
            system_prompt: Custom system prompt
            max_turns: Override max turns

        Returns:
            IterationResult with metrics and outcomes
        """
        options = self._build_options(phase, system_prompt, max_turns)
        start_time = datetime.now()

        metrics = IterationMetrics()
        messages: list[Message] = []
        final_text_parts: list[str] = []
        task_completed = False
        task_id: str | None = None
        completion_notes: str | None = None
        error: str | None = None

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt)

                async for msg in client.receive_response():
                    messages.append(msg)

                    # Capture session ID for continuation
                    if isinstance(msg, SystemMessage) and hasattr(msg, "session_id"):
                        self._session_id = msg.session_id
                        metrics.session_id = msg.session_id

                    # Process assistant messages
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                final_text_parts.append(block.text)
                            elif isinstance(block, ToolUseBlock):
                                metrics.tool_calls += 1
                                # Check for task completion tools
                                if "ralph_mark_task_complete" in block.name:
                                    task_completed = True
                                    if isinstance(block.input, dict):
                                        task_id = block.input.get("task_id")
                                        completion_notes = block.input.get(
                                            "verification_notes"
                                        )

                    # Process result messages for token counts
                    if isinstance(msg, ResultMessage) and hasattr(msg, "usage"):
                        usage = msg.usage
                        if usage is not None:
                            if hasattr(usage, "input_tokens"):
                                metrics.input_tokens += usage.input_tokens
                            if hasattr(usage, "output_tokens"):
                                metrics.output_tokens += usage.output_tokens

        except ConnectionError as e:
            error = f"Connection error: {e}"
            logger.error("SDK connection error: %s", e)
        except TimeoutError as e:
            error = f"Timeout error: {e}"
            logger.error("SDK timeout: %s", e)
        except PermissionError as e:
            error = f"Permission/authentication error: {e}"
            logger.error("SDK authentication error: %s", e)
        except Exception as e:
            # Check for rate limit patterns in exception message
            error_msg = str(e).lower()
            if "rate" in error_msg and "limit" in error_msg:
                error = f"Rate limit exceeded: {e}"
                logger.warning("SDK rate limit hit: %s", e)
            elif "auth" in error_msg or "key" in error_msg or "credential" in error_msg:
                error = f"Authentication error: {e}"
                logger.error("SDK authentication error: %s", e)
            elif "timeout" in error_msg:
                error = f"Timeout: {e}"
                logger.warning("SDK timeout: %s", e)
            else:
                error = str(e)
                logger.error("SDK error during iteration: %s", e, exc_info=True)

        # Calculate metrics
        end_time = datetime.now()
        metrics.duration_ms = int((end_time - start_time).total_seconds() * 1000)
        total_tokens = metrics.input_tokens + metrics.output_tokens
        metrics.cost_usd = calculate_cost(
            metrics.input_tokens,
            metrics.output_tokens,
            get_model_for_phase(phase or self.state.current_phase, self.config),
        )

        # Check if handoff is needed
        needs_handoff = False
        if self.state.context_budget.current_usage + total_tokens >= (
            self.state.context_budget.smart_zone_max
        ):
            needs_handoff = True

        return IterationResult(
            success=error is None,
            task_completed=task_completed,
            task_id=task_id,
            tokens_used=total_tokens,
            cost_usd=metrics.cost_usd,
            needs_handoff=needs_handoff,
            error=error,
            completion_notes=completion_notes,
            metrics=metrics,
            messages=messages,
            final_text="\n".join(final_text_parts),
        )

    async def stream_iteration(
        self,
        prompt: str,
        phase: Phase | None = None,
        system_prompt: str | None = None,
        max_turns: int | None = None,
    ) -> AsyncGenerator[StreamEvent, str | None]:
        """Stream events during iteration execution.

        This is an async generator that yields StreamEvent objects in real-time
        as the iteration progresses. When a NEEDS_INPUT event is yielded (from
        AskUserQuestion tool), the caller can send() the user's response back.

        This method enables transparent, real-time CLI output showing what the
        agent is thinking and doing.

        Args:
            prompt: The user prompt to send
            phase: Override phase (defaults to state.current_phase)
            system_prompt: Custom system prompt
            max_turns: Override max turns

        Yields:
            StreamEvent objects for text, tool use, user questions, etc.

        Example:
            async def run_with_display():
                gen = client.stream_iteration(prompt="Analyze this code")
                event = await gen.asend(None)  # Start generator
                while True:
                    try:
                        user_input = display_event(event)  # Returns input if NEEDS_INPUT
                        event = await gen.asend(user_input)
                    except StopAsyncIteration:
                        break
        """
        options = self._build_options(phase, system_prompt, max_turns)
        start_time = datetime.now()
        current_phase = phase or self.state.current_phase

        # Metrics tracking
        input_tokens = 0
        output_tokens = 0
        tool_calls = 0
        task_completed = False
        task_id: str | None = None
        completion_notes: str | None = None
        final_text_parts: list[str] = []

        # Yield iteration start event
        yield iteration_start_event(
            iteration=self.state.iteration_count,
            phase=current_phase.value,
            session_id=self._session_id,
            usage_percentage=self.state.context_budget.usage_percentage,
        )

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt)

                async for msg in client.receive_response():
                    # Capture session ID for continuation
                    if isinstance(msg, SystemMessage) and hasattr(msg, "session_id"):
                        self._session_id = msg.session_id

                    # Process assistant messages - yield events for each block
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                # Yield text delta for streaming display
                                final_text_parts.append(block.text)
                                yield text_delta_event(block.text)

                            elif isinstance(block, ToolUseBlock):
                                tool_calls += 1
                                tool_input_dict = (
                                    block.input
                                    if isinstance(block.input, dict)
                                    else {}
                                )

                                # Yield tool start event
                                yield tool_start_event(
                                    tool_name=block.name,
                                    tool_input=tool_input_dict,
                                    tool_id=block.id,
                                )

                                # Note: AskUserQuestion is handled by can_use_tool callback
                                # which displays questions and collects answers BEFORE
                                # the tool executes. We just observe the tool call here.

                                # Check for Ralph task management tools
                                if "ralph_mark_task_complete" in block.name:
                                    task_completed = True
                                    task_id = tool_input_dict.get("task_id")
                                    completion_notes = tool_input_dict.get(
                                        "verification_notes"
                                    )
                                    yield task_complete_event(
                                        task_id=task_id or "unknown",
                                        verification_notes=completion_notes,
                                    )

                                elif "ralph_mark_task_blocked" in block.name:
                                    blocked_task_id = tool_input_dict.get("task_id")
                                    blocked_reason = tool_input_dict.get(
                                        "reason", "Unknown"
                                    )
                                    yield task_blocked_event(
                                        task_id=blocked_task_id or "unknown",
                                        reason=blocked_reason,
                                    )

                                else:
                                    # For other tools, just yield tool end
                                    # (result will come separately)
                                    yield tool_end_event(
                                        tool_name=block.name,
                                        tool_id=block.id,
                                        success=True,
                                    )

                    # Process result messages for token counts
                    if isinstance(msg, ResultMessage) and hasattr(msg, "usage"):
                        usage = msg.usage
                        if usage is not None:
                            if hasattr(usage, "input_tokens"):
                                input_tokens += usage.input_tokens
                            if hasattr(usage, "output_tokens"):
                                output_tokens += usage.output_tokens

        except ConnectionError as e:
            yield error_event(f"Connection error: {e}", error_type="connection")
            logger.error("SDK connection error: %s", e)
        except TimeoutError as e:
            yield error_event(f"Timeout error: {e}", error_type="timeout")
            logger.error("SDK timeout: %s", e)
        except PermissionError as e:
            yield error_event(
                f"Permission/authentication error: {e}", error_type="auth"
            )
            logger.error("SDK authentication error: %s", e)
        except Exception as e:
            error_msg = str(e).lower()
            if "rate" in error_msg and "limit" in error_msg:
                yield warning_event(f"Rate limit exceeded: {e}")
                logger.warning("SDK rate limit hit: %s", e)
            else:
                yield error_event(str(e), error_type="unknown")
                logger.error("SDK error during iteration: %s", e, exc_info=True)

        # Calculate final metrics
        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        total_tokens = input_tokens + output_tokens
        cost_usd = calculate_cost(
            input_tokens,
            output_tokens,
            get_model_for_phase(current_phase, self.config),
        )

        # Check if handoff is needed
        needs_handoff = False
        if self.state.context_budget.current_usage + total_tokens >= (
            self.state.context_budget.smart_zone_max
        ):
            needs_handoff = True

        # Yield iteration end event with summary
        yield iteration_end_event(
            iteration=self.state.iteration_count,
            phase=current_phase.value,
            success=True,  # No exception means success
            tokens_used=total_tokens,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            tool_calls=tool_calls,
            task_completed=task_completed,
            task_id=task_id,
            needs_handoff=needs_handoff,
            final_text="\n".join(final_text_parts),
        )

    async def simple_query(
        self,
        prompt: str,
        allowed_tools: list[str] | None = None,
    ) -> str:
        """Execute a simple query and return the text response.

        This is a simpler interface for one-off queries that don't
        need full iteration tracking.

        Args:
            prompt: The prompt to send
            allowed_tools: Optional tool allowlist

        Returns:
            The assistant's text response
        """
        options = ClaudeAgentOptions(
            allowed_tools=allowed_tools or ["Read", "Glob", "Grep"],
            permission_mode="bypassPermissions",
            cwd=str(self.state.project_root),
            max_turns=10,
        )

        result_parts: list[str] = []

        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        result_parts.append(block.text)

        return "\n".join(result_parts)

    def reset_session(self) -> None:
        """Reset session ID to start a fresh conversation."""
        self._session_id = None

    @property
    def session_id(self) -> str | None:
        """Get the current session ID."""
        return self._session_id


def create_ralph_client(
    state: RalphState,
    config: RalphConfig | None = None,
    hooks: dict[str, list[HookMatcher]] | None = None,
    mcp_servers: dict[str, Any] | None = None,
) -> RalphSDKClient:
    """Create a RalphSDKClient for the given state.

    Args:
        state: Current Ralph state
        config: Optional Ralph configuration
        hooks: Optional SDK hooks
        mcp_servers: Optional MCP servers

    Returns:
        Configured RalphSDKClient
    """
    return RalphSDKClient(
        state=state,
        config=config,
        hooks=hooks,
        mcp_servers=mcp_servers,
    )
