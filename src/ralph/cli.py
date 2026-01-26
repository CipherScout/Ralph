"""Ralph CLI entry point using Typer."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ralph.sdk_client import UserInputCallbacks

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from ralph import __version__
from ralph.animations import (
    PhaseAnimation,
    ThinkingSpinner,
    get_random_fact,
    get_random_phrase,
    get_tool_category,
)
from ralph.config import load_config
from ralph.context import (
    add_injection,
    execute_context_handoff,
    load_session_history,
)
from ralph.events import StreamEvent, StreamEventType
from ralph.executors import (
    BuildingExecutor,
    DiscoveryExecutor,
    PlanningExecutor,
    ValidationExecutor,
)
from ralph.models import Phase, TaskStatus
from ralph.persistence import (
    CorruptedStateError,
    StateNotFoundError,
    initialize_plan,
    initialize_state,
    load_plan,
    load_state,
    plan_exists,
    save_plan,
    save_state,
    state_exists,
)

app = typer.Typer(
    name="ralph",
    help="Deterministic agentic coding loop using Claude Agent SDK",
    no_args_is_help=True,
)
console = Console()


class RalphLiveDisplay:
    """Rich-based live display for Ralph execution with real-time event handling.

    This class provides a transparent, real-time CLI experience by handling
    StreamEvents from the Ralph execution loop. It displays tool calls,
    text output, and handles user interaction when questions are asked.

    Attributes:
        console: Rich Console instance for output
        verbosity: 0=quiet, 1=normal, 2=verbose
        current_text: Accumulated text from TEXT_DELTA events
        tool_stack: Stack of currently executing tools
    """

    def __init__(self, console: Console, verbosity: int = 1) -> None:
        """Initialize the live display.

        Args:
            console: Rich Console for output
            verbosity: Output verbosity level (0=quiet, 1=normal, 2=verbose)
        """
        self.console = console
        self.verbosity = verbosity
        self.current_text = ""
        self.tool_stack: list[str] = []
        self._iteration_count = 0
        self._total_cost = 0.0
        self._total_tokens = 0
        self._spinner: ThinkingSpinner | None = None
        self._phase_animation = PhaseAnimation(console)
        self._show_fun_fact_at = 5  # Show a fun fact every N iterations
        self._spinner_active = False

    def handle_event(self, event: StreamEvent) -> str | None:
        """Handle a stream event and return user input if needed.

        This method processes each event type and produces appropriate
        CLI output. For NEEDS_INPUT events, it pauses to get user input
        and returns the response.

        Args:
            event: The StreamEvent to handle

        Returns:
            User input string if event was NEEDS_INPUT, otherwise None
        """
        if event.type == StreamEventType.ITERATION_START:
            self._iteration_count = event.iteration or 0
            if self.verbosity >= 1:
                phase = event.phase or "unknown"
                self.console.print(
                    f"\n[bold blue]Iteration {self._iteration_count}[/bold blue] "
                    f"[dim]({phase})[/dim]"
                )
                # Show a fun fact every N iterations
                if self._iteration_count > 0 and self._iteration_count % self._show_fun_fact_at == 0:
                    fact = get_random_fact()
                    self.console.print(f"  [dim italic]Did you know? {fact}[/dim italic]")
            # Start the animated thinking spinner
            self._start_spinner()

        elif event.type == StreamEventType.ITERATION_END:
            # Stop the spinner before showing results
            self._stop_spinner()

            tokens = event.data.get("tokens_used", 0)
            cost = event.data.get("cost_usd", 0.0)
            self._total_tokens += tokens
            self._total_cost += cost

            if self.verbosity >= 1:
                success = event.data.get("success", False)
                status = "[green]OK[/green]" if success else "[red]FAILED[/red]"
                self.console.print(
                    f"  {status} [dim]({tokens:,} tokens, ${cost:.4f})[/dim]"
                )

        elif event.type == StreamEventType.TEXT_DELTA:
            self.current_text += event.text or ""
            # Only stop spinner when actually printing text (verbose mode)
            if self.verbosity >= 2 and event.text:
                self._stop_spinner()
                self.console.print(event.text, end="")

        elif event.type == StreamEventType.TOOL_USE_START:
            # Stop spinner to show tool info
            self._stop_spinner()

            tool_name = event.tool_name or "unknown"
            self.tool_stack.append(tool_name)

            if self.verbosity >= 1:
                # Summarize tool input for display
                summary = self._summarize_tool_input(tool_name, event.tool_input)
                if summary:
                    self.console.print(f"[dim]  -> {tool_name}: {summary}[/dim]")
                else:
                    self.console.print(f"[dim]  -> {tool_name}[/dim]")

            # Start spinner while tool executes
            self._start_spinner()

        elif event.type == StreamEventType.TOOL_USE_END:
            # Stop spinner when tool completes
            self._stop_spinner()
            if self.tool_stack:
                self.tool_stack.pop()
            # Restart spinner - LLM continues processing after tool completes
            self._start_spinner()

        elif event.type == StreamEventType.NEEDS_INPUT:
            # Stop spinner to show question
            self._stop_spinner()
            # Display question with Rich formatting
            self.console.print()
            question_text = event.question or "Please provide input:"
            self.console.print(
                Panel(
                    question_text,
                    title="[bold yellow]Question[/bold yellow]",
                    border_style="yellow",
                )
            )

            # Show options if provided
            if event.options:
                for i, opt in enumerate(event.options, 1):
                    if isinstance(opt, dict):
                        label = opt.get("label", str(opt))
                        desc = opt.get("description", "")
                        if desc:
                            self.console.print(f"  {i}. {label} [dim]- {desc}[/dim]")
                        else:
                            self.console.print(f"  {i}. {label}")
                    else:
                        self.console.print(f"  {i}. {opt}")
                self.console.print()

            # Get user response
            response = Prompt.ask("[bold]Your answer[/bold]")
            # Restart spinner - LLM continues processing after user input
            self._start_spinner()
            return response

        elif event.type == StreamEventType.TASK_COMPLETE:
            task_id = event.task_id or event.data.get("task_id", "unknown")
            notes = event.data.get("verification_notes", "")
            self.console.print(f"[green]  Task completed: {task_id}[/green]")
            if notes and self.verbosity >= 2:
                self.console.print(f"[dim]    Notes: {notes}[/dim]")

        elif event.type == StreamEventType.TASK_BLOCKED:
            task_id = event.task_id or event.data.get("task_id", "unknown")
            reason = event.data.get("reason", "Unknown reason")
            self.console.print(f"[yellow]  Task blocked: {task_id}[/yellow]")
            self.console.print(f"[dim]    Reason: {reason}[/dim]")

        elif event.type == StreamEventType.PHASE_CHANGE:
            old_phase = event.data.get("old_phase", "unknown")
            new_phase = event.data.get("new_phase", event.phase or "unknown")
            self.console.print(
                f"\n[bold blue]Phase transition: {old_phase} -> {new_phase}[/bold blue]"
            )
            # Show phase animation banner
            if self.verbosity >= 1:
                self._phase_animation.show_phase_banner(str(new_phase))

        elif event.type == StreamEventType.HANDOFF_START:
            reason = event.data.get("reason", "context budget")
            self.console.print(f"\n[yellow]Context handoff ({reason})...[/yellow]")

        elif event.type == StreamEventType.HANDOFF_COMPLETE:
            new_session = event.session_id or "new"
            self.console.print(f"[green]Handoff complete. New session: {new_session}[/green]")

        elif event.type == StreamEventType.ERROR:
            message = event.error_message or event.data.get("message", "Unknown error")
            error_type = event.data.get("error_type", "")
            if error_type:
                self.console.print(f"[red]Error ({error_type}): {message}[/red]")
            else:
                self.console.print(f"[red]Error: {message}[/red]")

        elif event.type == StreamEventType.WARNING:
            message = event.error_message or event.data.get("message", "Warning")
            self.console.print(f"[yellow]Warning: {message}[/yellow]")

        elif event.type == StreamEventType.INFO:
            message = event.data.get("message", "")
            if message and self.verbosity >= 1:
                self.console.print(f"[dim]{message}[/dim]")

        return None

    def _summarize_tool_input(
        self, tool_name: str | None, input_data: dict[str, Any] | None
    ) -> str:
        """Summarize tool input for concise display.

        Args:
            tool_name: Name of the tool
            input_data: Tool input parameters

        Returns:
            Summarized string representation
        """
        if not tool_name or not input_data:
            return ""

        if tool_name == "Read":
            path = input_data.get("file_path", "")
            return str(path)[-60:] if len(str(path)) > 60 else str(path)

        elif tool_name == "Write":
            path = input_data.get("file_path", "")
            content_len = len(input_data.get("content", ""))
            return f"{path} ({content_len} chars)"

        elif tool_name == "Edit":
            path = input_data.get("file_path", "")
            return str(path)[-50:] if len(str(path)) > 50 else str(path)

        elif tool_name == "Bash":
            cmd = input_data.get("command", "")
            return (cmd[:60] + "...") if len(cmd) > 60 else cmd

        elif tool_name == "Grep":
            pattern = input_data.get("pattern", "")
            path = input_data.get("path", ".")
            return f"'{pattern}' in {path}"

        elif tool_name == "Glob":
            pattern = input_data.get("pattern", "")
            return pattern

        elif tool_name == "WebSearch":
            query = input_data.get("query", "")
            return f'"{query}"'

        elif tool_name == "WebFetch":
            url = input_data.get("url", "")
            return url[:60] if len(url) > 60 else url

        elif tool_name == "Task":
            desc = input_data.get("description", "")
            return desc[:40] if len(desc) > 40 else desc

        elif tool_name == "AskUserQuestion":
            # Don't summarize - NEEDS_INPUT event handles display
            return ""

        elif tool_name.startswith("ralph_"):
            # Ralph MCP tools
            return json.dumps(input_data)[:50]

        else:
            # Generic summary
            if self.verbosity >= 2:
                return json.dumps(input_data)[:80]
            return ""

    def _start_spinner(self) -> None:
        """Start the thinking spinner animation."""
        if self._spinner_active:
            return
        try:
            self._spinner = ThinkingSpinner(
                self.console,
                refresh_rate=0.1,
                show_tips=self.verbosity >= 1,
            )
            self._spinner.start()
            self._spinner_active = True
        except Exception:
            # Don't crash if spinner fails to start
            self._spinner_active = False

    def _stop_spinner(self) -> None:
        """Stop the thinking spinner animation."""
        if not self._spinner_active:
            return
        try:
            if self._spinner:
                self._spinner.stop()
                self._spinner = None
            self._spinner_active = False
        except Exception:
            # Don't crash if spinner fails to stop
            self._spinner_active = False

    def _update_spinner(self, tokens: int = 0, cost: float = 0.0) -> None:
        """Update the spinner with current stats."""
        if self._spinner and self._spinner_active:
            try:
                self._spinner.update(tokens=tokens, cost=cost)
            except Exception:
                pass

    def get_user_input_callbacks(self) -> "UserInputCallbacks":
        """Get callbacks for SDK user input handling.

        Returns callbacks that allow the SDK's AskUserQuestion handler to
        properly integrate with the CLI's spinner lifecycle. This ensures
        the spinner stops before showing questions and restarts after
        collecting user input.

        Returns:
            UserInputCallbacks with spinner control functions
        """
        from ralph.sdk_client import UserInputCallbacks

        return UserInputCallbacks(
            on_question_start=self._stop_spinner,
            on_question_end=self._start_spinner,
            console=self.console,
        )

    def get_summary(self) -> str:
        """Get a summary of the execution statistics.

        Returns:
            Formatted summary string
        """
        return (
            f"Total: {self._iteration_count} iterations, "
            f"{self._total_tokens:,} tokens, ${self._total_cost:.4f}"
        )

    def reset(self) -> None:
        """Reset the display state for a new execution."""
        self._stop_spinner()  # Ensure spinner is stopped
        self.current_text = ""
        self.tool_stack = []
        self._iteration_count = 0
        self._total_cost = 0.0
        self._total_tokens = 0
        self._spinner_active = False


def _resolve_project_root(project_root: str) -> Path:
    """Resolve and validate project root path."""
    path = Path(project_root).resolve()
    if not path.exists():
        raise typer.BadParameter(f"Directory does not exist: {path}")
    if not path.is_dir():
        raise typer.BadParameter(f"Not a directory: {path}")
    return path


def _validate_phase_transition(
    target_phase: Phase, project_root: Path
) -> tuple[bool, str | None]:
    """Validate that a phase transition is allowed.

    Args:
        target_phase: The phase to transition to
        project_root: Path to project root

    Returns:
        Tuple of (is_valid, warning_message)
    """
    # DISCOVERY is always valid - it's the starting phase
    if target_phase == Phase.DISCOVERY:
        return True, None

    # PLANNING requires state to exist
    if target_phase == Phase.PLANNING:
        if not state_exists(project_root):
            return False, "Cannot start planning without initializing Ralph first"
        return True, None

    # BUILDING requires a plan
    if target_phase == Phase.BUILDING:
        if not plan_exists(project_root):
            return False, "Cannot start building without a plan (run planning phase first)"
        plan = load_plan(project_root)
        if not plan.tasks:
            return False, "Cannot start building with an empty plan"
        return True, None

    # VALIDATION requires completed tasks
    if target_phase == Phase.VALIDATION:
        if not plan_exists(project_root):
            return False, "Cannot validate without a plan"
        plan = load_plan(project_root)
        completed = sum(1 for t in plan.tasks if t.status == TaskStatus.COMPLETE)
        if completed == 0:
            return False, "Cannot validate without any completed tasks"
        return True, None

    return True, None


@app.command()
def version() -> None:
    """Show Ralph version."""
    console.print(f"Ralph v{__version__}")


@app.command()
def init(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
    force: bool = typer.Option(False, "--force", "-f", help="Reinitialize even if already exists"),
) -> None:
    """Initialize Ralph in a project directory.

    Creates .ralph/ directory with state.json and implementation_plan.json.
    """
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    # Check if already initialized
    if state_exists(path) and not force:
        console.print(f"[yellow]Ralph already initialized in {path}[/yellow]")
        console.print("Use --force to reinitialize")
        raise typer.Exit(1)

    console.print(f"[blue]Initializing Ralph in {path}...[/blue]")

    # Initialize state and plan
    state = initialize_state(path)
    plan = initialize_plan(path)

    console.print("[green]✓ Created .ralph/state.json[/green]")
    console.print("[green]✓ Created .ralph/implementation_plan.json[/green]")
    console.print("[green]Ralph initialized successfully![/green]")
    console.print(f"\n[dim]Current phase: {state.current_phase.value}[/dim]")
    console.print(f"[dim]Tasks in plan: {len(plan.tasks)}[/dim]")


@app.command()
def status(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
) -> None:
    """Show current Ralph state."""
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    if not state_exists(path):
        console.print(f"[yellow]Ralph not initialized in {path}[/yellow]")
        console.print("Run 'ralph init' to initialize")
        raise typer.Exit(1)

    try:
        state = load_state(path)
    except (StateNotFoundError, CorruptedStateError) as e:
        console.print(f"[red]Error loading state: {e}[/red]")
        raise typer.Exit(1) from None

    # Status panel
    phase_colors = {
        Phase.DISCOVERY: "cyan",
        Phase.PLANNING: "blue",
        Phase.BUILDING: "green",
        Phase.VALIDATION: "yellow",
    }
    phase_color = phase_colors.get(state.current_phase, "white")

    status_text = f"""[bold]Phase:[/bold] [{phase_color}]{state.current_phase.value}[/{phase_color}]
[bold]Iteration:[/bold] {state.iteration_count}
[bold]Session ID:[/bold] {state.session_id or 'None'}
[bold]Started:[/bold] {state.started_at.strftime('%Y-%m-%d %H:%M:%S')}
[bold]Last Activity:[/bold] {state.last_activity_at.strftime('%Y-%m-%d %H:%M:%S')}"""

    console.print(Panel(status_text, title="Ralph Status", border_style="blue"))

    # Cost information
    cost_text = f"""[bold]Total Cost:[/bold] ${state.total_cost_usd:.4f}
[bold]Total Tokens:[/bold] {state.total_tokens_used:,}
[bold]Session Cost:[/bold] ${state.session_cost_usd:.4f}
[bold]Session Tokens:[/bold] {state.session_tokens_used:,}"""

    console.print(Panel(cost_text, title="Cost Tracking", border_style="green"))

    # Circuit breaker status
    cb = state.circuit_breaker
    cb_color = "green" if cb.state == "closed" else "red" if cb.state == "open" else "yellow"
    cb_text = f"""[bold]State:[/bold] [{cb_color}]{cb.state}[/{cb_color}]
[bold]Failure Count:[/bold] {cb.failure_count}/{cb.max_consecutive_failures}
[bold]Stagnation Count:[/bold] {cb.stagnation_count}/{cb.max_stagnation_iterations}
[bold]Cost Used:[/bold] ${state.total_cost_usd:.2f}/${cb.max_cost_usd:.2f}"""

    if cb.last_failure_reason:
        cb_text += f"\n[bold]Last Failure:[/bold] {cb.last_failure_reason}"

    console.print(Panel(cb_text, title="Circuit Breaker", border_style=cb_color))

    # Context budget
    budget = state.context_budget
    if budget.total_capacity > 0:
        usage_pct = (budget.current_usage / budget.total_capacity) * 100
    else:
        usage_pct = 0.0
    budget_color = "green" if usage_pct < 60 else "yellow" if usage_pct < 80 else "red"

    budget_text = (
        f"[bold]Usage:[/bold] [{budget_color}]{usage_pct:.1f}%[/{budget_color}] "
        f"({budget.current_usage:,}/{budget.total_capacity:,})\n"
        f"[bold]Smart Zone Max:[/bold] {budget.smart_zone_max:,} (60%)\n"
        f"[bold]Available:[/bold] {budget.available_tokens:,}\n"
        f"[bold]Should Handoff:[/bold] {'Yes' if budget.should_handoff() else 'No'}"
    )

    console.print(Panel(budget_text, title="Context Budget", border_style=budget_color))

    # Load and show plan if verbose
    if verbose and plan_exists(path):
        try:
            plan = load_plan(path)
            if plan.tasks:
                table = Table(title="Implementation Plan")
                table.add_column("ID", style="dim")
                table.add_column("Priority", justify="center")
                table.add_column("Status")
                table.add_column("Description")

                status_styles = {
                    TaskStatus.PENDING: "white",
                    TaskStatus.IN_PROGRESS: "yellow",
                    TaskStatus.COMPLETE: "green",
                    TaskStatus.BLOCKED: "red",
                }

                for task in sorted(plan.tasks, key=lambda t: t.priority):
                    style = status_styles.get(task.status, "white")
                    if len(task.description) > 50:
                        desc = task.description[:50] + "..."
                    else:
                        desc = task.description
                    task_id = task.id[:16] + "..." if len(task.id) > 16 else task.id
                    table.add_row(
                        task_id,
                        str(task.priority),
                        f"[{style}]{task.status.value}[/{style}]",
                        desc,
                    )

                console.print(table)
                pct = f"{plan.completion_percentage:.1%}"
                count_info = f"{plan.complete_count}/{len(plan.tasks)}"
                console.print(f"\n[dim]Completion: {pct} ({count_info} tasks)[/dim]")
            else:
                console.print("[dim]No tasks in implementation plan[/dim]")
        except (StateNotFoundError, CorruptedStateError) as e:
            console.print(f"[yellow]Could not load plan: {e}[/yellow]")


@app.command()
def tasks(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
    pending: bool = typer.Option(False, "--pending", help="Show only pending tasks"),
    show_all: bool = typer.Option(False, "--all", "-a", help="Show all tasks including completed"),
) -> None:
    """List tasks in the implementation plan."""
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    if not plan_exists(path):
        console.print(f"[yellow]No implementation plan found in {path}[/yellow]")
        console.print("Run 'ralph init' to initialize")
        raise typer.Exit(1)

    try:
        plan = load_plan(path)
    except (StateNotFoundError, CorruptedStateError) as e:
        console.print(f"[red]Error loading plan: {e}[/red]")
        raise typer.Exit(1) from None

    if not plan.tasks:
        console.print("[dim]No tasks in implementation plan[/dim]")
        return

    # Filter tasks
    tasks_to_show = plan.tasks
    if pending:
        tasks_to_show = [t for t in tasks_to_show if t.status == TaskStatus.PENDING]
    elif not show_all:
        tasks_to_show = [t for t in tasks_to_show if t.status != TaskStatus.COMPLETE]

    if not tasks_to_show:
        if pending:
            console.print("[green]No pending tasks[/green]")
        else:
            console.print("[green]All tasks complete![/green]")
        return

    table = Table(title="Tasks")
    table.add_column("ID", style="dim")
    table.add_column("Pri", justify="center")
    table.add_column("Status")
    table.add_column("Description")
    table.add_column("Deps", justify="center")

    status_styles = {
        TaskStatus.PENDING: "white",
        TaskStatus.IN_PROGRESS: "yellow",
        TaskStatus.COMPLETE: "green",
        TaskStatus.BLOCKED: "red",
    }

    for task in sorted(tasks_to_show, key=lambda t: (t.priority, t.id)):
        style = status_styles.get(task.status, "white")
        deps = len(task.dependencies)
        desc = task.description[:60] + "..." if len(task.description) > 60 else task.description
        task_id = task.id[:20] + "..." if len(task.id) > 20 else task.id
        table.add_row(
            task_id,
            str(task.priority),
            f"[{style}]{task.status.value}[/{style}]",
            desc,
            str(deps) if deps > 0 else "-",
        )

    console.print(table)

    # Summary
    total = len(plan.tasks)
    complete = plan.complete_count
    pending_count = plan.pending_count
    pct = f"{plan.completion_percentage:.1%}"
    console.print(
        f"\n[dim]Total: {total} | Complete: {complete} | Pending: {pending_count} | "
        f"Completion: {pct}[/dim]"
    )

    # Show next task
    next_task = plan.get_next_task()
    if next_task:
        console.print(f"\n[bold]Next task:[/bold] {next_task.description}")


@app.command()
def reset(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
    keep_plan: bool = typer.Option(False, "--keep-plan", help="Keep implementation plan"),
) -> None:
    """Reset Ralph state to initial values."""
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    if not state_exists(path):
        console.print(f"[yellow]Ralph not initialized in {path}[/yellow]")
        raise typer.Exit(1)

    # Confirm reset
    confirm = typer.confirm("This will reset all state. Continue?")
    if not confirm:
        console.print("[dim]Aborted[/dim]")
        raise typer.Exit(0)

    # Reset state
    initialize_state(path)
    console.print("[green]✓ State reset[/green]")

    if not keep_plan:
        initialize_plan(path)
        console.print("[green]✓ Plan reset[/green]")

    console.print("[green]Ralph reset complete[/green]")


# ============================================================================
# Development Helper Commands
# ============================================================================


def _run_uv_command(args: list[str], project_root: Path) -> int:
    """Run a uv command and return exit code."""
    cmd = ["uv"] + args
    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")
    result = subprocess.run(cmd, cwd=project_root)
    return result.returncode


@app.command()
def test(
    project_root: str = typer.Option(
        ".", "--project-root", "-p", help="Project root directory"
    ),
    args: list[str] = typer.Argument(None, help="Additional pytest arguments"),  # noqa: B008
) -> None:
    """Run tests using uv run pytest."""
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    pytest_args = ["run", "pytest"]
    if args:
        pytest_args.extend(args)

    exit_code = _run_uv_command(pytest_args, path)
    raise typer.Exit(exit_code)


@app.command()
def lint(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
    fix: bool = typer.Option(False, "--fix", help="Auto-fix issues"),
) -> None:
    """Run linting using uv run ruff."""
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    ruff_args = ["run", "ruff", "check", "."]
    if fix:
        ruff_args.append("--fix")

    exit_code = _run_uv_command(ruff_args, path)
    raise typer.Exit(exit_code)


@app.command()
def typecheck(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
) -> None:
    """Run type checking using uv run mypy."""
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    exit_code = _run_uv_command(["run", "mypy", "."], path)
    raise typer.Exit(exit_code)


# Create deps subcommand group
deps_app = typer.Typer(help="Dependency management commands")
app.add_typer(deps_app, name="deps")


@deps_app.command("add")
def deps_add(
    packages: list[str] = typer.Argument(..., help="Packages to add"),  # noqa: B008
    dev: bool = typer.Option(False, "--dev", "-d", help="Dev dependency"),
    project_root: str = typer.Option(
        ".", "--project-root", "-p", help="Project root directory"
    ),
) -> None:
    """Add dependencies using uv add."""
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    add_args = ["add"]
    if dev:
        add_args.append("--dev")
    add_args.extend(packages)

    exit_code = _run_uv_command(add_args, path)
    raise typer.Exit(exit_code)


@deps_app.command("sync")
def deps_sync(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
) -> None:
    """Sync dependencies using uv sync."""
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    exit_code = _run_uv_command(["sync"], path)
    raise typer.Exit(exit_code)


@deps_app.command("remove")
def deps_remove(
    packages: list[str] = typer.Argument(..., help="Packages to remove"),  # noqa: B008
    project_root: str = typer.Option(
        ".", "--project-root", "-p", help="Project root directory"
    ),
) -> None:
    """Remove dependencies using uv remove."""
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    remove_args = ["remove"] + list(packages)
    exit_code = _run_uv_command(remove_args, path)
    raise typer.Exit(exit_code)


# ============================================================================
# Control Commands
# ============================================================================


@app.command()
def inject(
    message: str = typer.Argument(..., help="Message to inject into context"),
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
    priority: int = typer.Option(0, "--priority", help="Injection priority (higher = first)"),
) -> None:
    """Inject a message into the next iteration's context."""
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    if not state_exists(path):
        console.print(f"[yellow]Ralph not initialized in {path}[/yellow]")
        raise typer.Exit(1)

    add_injection(path, message, source="user", priority=priority)
    console.print(f"[green]Injected message with priority {priority}[/green]")
    console.print(f"[dim]Message: {message[:100]}{'...' if len(message) > 100 else ''}[/dim]")


@app.command()
def pause(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
) -> None:
    """Pause the Ralph loop after current iteration."""
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    if not state_exists(path):
        console.print(f"[yellow]Ralph not initialized in {path}[/yellow]")
        raise typer.Exit(1)

    try:
        state = load_state(path)
        state.paused = True
        save_state(state, path)
        console.print("[yellow]Ralph loop paused[/yellow]")
        console.print("[dim]Loop will stop after current iteration completes[/dim]")
    except (StateNotFoundError, CorruptedStateError) as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def resume(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
) -> None:
    """Resume a paused Ralph loop."""
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    if not state_exists(path):
        console.print(f"[yellow]Ralph not initialized in {path}[/yellow]")
        raise typer.Exit(1)

    try:
        state = load_state(path)
        if not state.paused:
            console.print("[dim]Ralph loop is not paused[/dim]")
            return
        state.paused = False
        save_state(state, path)
        console.print("[green]Ralph loop resumed[/green]")
    except (StateNotFoundError, CorruptedStateError) as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def skip(
    task_id: str = typer.Argument(..., help="Task ID to skip"),
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
    reason: str = typer.Option("", "--reason", "-r", help="Reason for skipping"),
) -> None:
    """Skip a task by marking it as blocked."""
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    if not plan_exists(path):
        console.print(f"[yellow]No implementation plan found in {path}[/yellow]")
        raise typer.Exit(1)

    try:
        plan = load_plan(path)
        task = plan.get_task_by_id(task_id)
        if not task:
            console.print(f"[red]Task not found: {task_id}[/red]")
            raise typer.Exit(1)

        task.status = TaskStatus.BLOCKED
        if reason:
            task.blockers.append(reason)
        save_plan(plan, path)

        console.print(f"[yellow]Task skipped: {task.description}[/yellow]")
        if reason:
            console.print(f"[dim]Reason: {reason}[/dim]")
    except (StateNotFoundError, CorruptedStateError) as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None


# ============================================================================
# History Command
# ============================================================================


@app.command()
def history(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of sessions to show"),
) -> None:
    """Show session history."""
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    sessions = load_session_history(path, limit=limit)

    if not sessions:
        console.print("[dim]No session history found[/dim]")
        return

    table = Table(title="Session History")
    table.add_column("Session ID", style="dim")
    table.add_column("Phase")
    table.add_column("Iterations", justify="center")
    table.add_column("Cost", justify="right")
    table.add_column("Reason")
    table.add_column("Timestamp")

    for session in sessions:
        table.add_row(
            session.session_id[:12] + "...",
            session.phase.value if hasattr(session.phase, "value") else str(session.phase),
            str(session.iteration),
            f"${session.cost_usd:.4f}",
            session.handoff_reason,
            session.ended_at.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)


# ============================================================================
# Phase Commands (Placeholders for phase implementations)
# ============================================================================


@app.command()
def run(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
    phase: str = typer.Option(None, "--phase", help="Start from specific phase"),
    max_iterations: int = typer.Option(None, "--max-iterations", "-n", help="Maximum iterations"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without executing"
    ),
) -> None:
    """Run the full Ralph loop.

    This command orchestrates the complete Ralph development workflow:
    1. DISCOVERY - Gather requirements using JTBD framework
    2. PLANNING - Create implementation plan with sized tasks
    3. BUILDING - Execute tasks with TDD and backpressure
    4. VALIDATION - Verify implementation meets requirements

    The loop continues until all tasks are complete, the circuit breaker
    trips, or max iterations is reached.
    """
    from ralph.runner import LoopRunner, LoopStatus

    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    if not state_exists(path):
        console.print(f"[yellow]Ralph not initialized in {path}[/yellow]")
        console.print("Run 'ralph init' to initialize")
        raise typer.Exit(1)

    # Load config
    config = load_config(path)
    if max_iterations:
        config.max_iterations = max_iterations

    # Set starting phase if specified
    if phase:
        try:
            start_phase = Phase(phase.lower())
            # Validate phase transition preconditions
            is_valid, error_msg = _validate_phase_transition(start_phase, path)
            if not is_valid:
                console.print(f"[red]Cannot transition to {start_phase.value}: {error_msg}[/red]")
                raise typer.Exit(1) from None
            state = load_state(path)
            state.current_phase = start_phase
            save_state(state, path)
            console.print(f"[dim]Starting from phase: {start_phase.value}[/dim]")
        except ValueError:
            console.print(f"[red]Invalid phase: {phase}[/red]")
            console.print(f"[dim]Valid phases: {', '.join(p.value for p in Phase)}[/dim]")
            raise typer.Exit(1) from None

    console.print(Panel("[bold]Ralph Loop Starting[/bold]", border_style="blue"))
    console.print(f"[dim]Project: {path}[/dim]")
    console.print(f"[dim]Max iterations: {config.max_iterations}[/dim]")

    if dry_run:
        console.print("[yellow]Dry run mode - showing what would be done[/yellow]")
        state = load_state(path)
        plan = load_plan(path) if plan_exists(path) else None
        console.print(f"[dim]Current phase: {state.current_phase.value}[/dim]")
        console.print(f"[dim]Iteration count: {state.iteration_count}[/dim]")
        if plan:
            console.print(f"[dim]Pending tasks: {plan.pending_count}[/dim]")
            next_task = plan.get_next_task()
            if next_task:
                console.print(f"[dim]Next task: {next_task.description}[/dim]")
        return

    # Create loop runner with callbacks
    def on_iteration_start(context: dict[str, Any]) -> None:
        console.print(
            f"\n[bold]Iteration {context['iteration']}[/bold] "
            f"({context['phase']}) - {context['usage_percentage']:.1f}% context used"
        )

    def on_iteration_end(result: Any) -> None:
        status = "[green]SUCCESS[/green]" if result.success else "[red]FAILED[/red]"
        console.print(f"  {status} - ${result.cost_usd:.4f} ({result.tokens_used:,} tokens)")
        if result.task_completed:
            console.print(f"  [green]Task completed: {result.task_id}[/green]")

    def on_phase_change(old_phase: Phase, new_phase: Phase) -> None:
        console.print(
            f"\n[bold blue]Phase transition: {old_phase.value} -> {new_phase.value}[/bold blue]"
        )

    def on_handoff(session_id: str) -> None:
        console.print(f"\n[yellow]Context handoff - New session: {session_id}[/yellow]")

    def on_halt(reason: str) -> None:
        console.print(f"\n[red]Loop halted: {reason}[/red]")

    runner = LoopRunner(
        project_root=path,
        config=config,
        on_iteration_start=on_iteration_start,
        on_iteration_end=on_iteration_end,
        on_phase_change=on_phase_change,
        on_handoff=on_handoff,
        on_halt=on_halt,
    )

    # Note: The actual execution requires an execute_fn that integrates with Claude SDK
    # For now, we show how to use the runner but don't execute actual LLM calls
    console.print("\n[yellow]Note: Full LLM integration requires ANTHROPIC_API_KEY[/yellow]")
    console.print("[dim]The runner is ready. To execute iterations, use the SDK integration.[/dim]")
    console.print("\n[bold]Current state:[/bold]")
    console.print(f"  Phase: {runner.current_phase.value}")
    console.print(f"  Session: {runner.state.session_id or 'None'}")

    # Show what the runner would do
    should_continue, reason = runner.should_continue()
    if should_continue:
        console.print("  [green]Ready to run[/green]")
        system_prompt = runner.get_system_prompt()
        console.print(f"\n[dim]System prompt ({len(system_prompt)} chars) ready for phase[/dim]")
    else:
        console.print(f"  [yellow]Would not continue: {reason}[/yellow]")

    # Final status
    status_map = {
        LoopStatus.RUNNING: "[green]RUNNING[/green]",
        LoopStatus.PAUSED: "[yellow]PAUSED[/yellow]",
        LoopStatus.COMPLETED: "[green]COMPLETED[/green]",
        LoopStatus.FAILED: "[red]FAILED[/red]",
        LoopStatus.HALTED: "[red]HALTED[/red]",
    }
    console.print(f"\n[bold]Loop status:[/bold] {status_map.get(runner.status, runner.status)}")


@app.command()
def discover(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
    goal: str = typer.Option(None, "--goal", "-g", help="Project goal"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Quiet output (hide LLM text)"),
    no_auto: bool = typer.Option(
        False, "--no-auto", help="Disable auto-transition to next phase"
    ),
    auto_timeout: int = typer.Option(
        60, "--auto-timeout", "-t", help="Seconds before auto-transition (default: 60)"
    ),
) -> None:
    """Run the Discovery phase with JTBD framework.

    This command runs interactively, asking questions to clarify requirements
    and creating specification files in the specs/ directory.

    By default, shows full LLM output as it streams.
    Use --quiet to hide LLM text and show only tool calls and summaries.

    After completion, automatically transitions to Planning phase in 60 seconds.
    Use --no-auto to disable auto-transition.
    """
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    if not state_exists(path):
        console.print(f"[yellow]Ralph not initialized in {path}[/yellow]")
        raise typer.Exit(1)

    # Determine verbosity level: default is verbose (2), --quiet gives normal (1)
    verbosity = 1 if quiet else 2

    async def run_streaming_discovery() -> bool:
        """Run discovery with streaming output."""
        display = RalphLiveDisplay(console, verbosity=verbosity)

        try:
            state = load_state(path)
            state.current_phase = Phase.DISCOVERY
            save_state(state, path)

            if verbosity >= 1:
                console.print(Panel("[bold cyan]Discovery Phase[/bold cyan]", border_style="cyan"))
                if goal:
                    console.print(f"[bold]Goal:[/bold] {goal}\n")

            # Execute discovery phase with streaming
            # Pass UI callbacks so spinner integrates with user input
            executor = DiscoveryExecutor(
                path, user_input_callbacks=display.get_user_input_callbacks()
            )
            gen = executor.stream_execution(initial_goal=goal)

            # Start the generator
            event = await gen.asend(None)

            while True:
                try:
                    # Handle event and get potential user input
                    user_input = display.handle_event(event)

                    # Send user input back (if any) and get next event
                    event = await gen.asend(user_input)

                except StopAsyncIteration:
                    break

            # Show summary
            if verbosity >= 1:
                console.print("\n[green]Discovery complete![/green]")
                console.print(f"[dim]{display.get_summary()}[/dim]")

                # List created specs
                specs_dir = path / "specs"
                if specs_dir.exists():
                    specs = [f.name for f in specs_dir.glob("*.md")]
                    if specs:
                        console.print(f"[dim]Created specs: {', '.join(specs)}[/dim]")

            return True

        except (StateNotFoundError, CorruptedStateError) as e:
            console.print(f"[red]Error: {e}[/red]")
            return False
        except KeyboardInterrupt:
            console.print("\n[yellow]Discovery interrupted by user[/yellow]")
            return False
        except Exception as e:
            console.print(f"[red]Discovery failed: {e}[/red]")
            return False

    success = asyncio.run(run_streaming_discovery())
    if not success:
        raise typer.Exit(1)

    # Auto-transition to next phase
    if not no_auto:
        from ralph.transitions import prompt_phase_transition

        should_continue, next_phase = asyncio.run(
            prompt_phase_transition(console, Phase.DISCOVERY, auto_timeout)
        )
        if should_continue and next_phase == Phase.PLANNING:
            plan(
                project_root=project_root,
                quiet=quiet,
                no_auto=no_auto,
                auto_timeout=auto_timeout,
            )


@app.command()
def plan(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Quiet output (hide LLM text)"),
    no_auto: bool = typer.Option(
        False, "--no-auto", help="Disable auto-transition to next phase"
    ),
    auto_timeout: int = typer.Option(
        60, "--auto-timeout", "-t", help="Seconds before auto-transition (default: 60)"
    ),
) -> None:
    """Run the Planning phase with gap analysis.

    This command analyzes specs and creates an implementation plan with
    sized, prioritized tasks.

    By default, shows full LLM output as it streams.
    Use --quiet to hide LLM text and show only tool calls and summaries.

    After completion, automatically transitions to Building phase in 60 seconds.
    Use --no-auto to disable auto-transition.
    """
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    if not state_exists(path):
        console.print(f"[yellow]Ralph not initialized in {path}[/yellow]")
        raise typer.Exit(1)

    # Determine verbosity level: default is verbose (2), --quiet gives normal (1)
    verbosity = 1 if quiet else 2

    async def run_streaming_planning() -> bool:
        """Run planning with streaming output."""
        display = RalphLiveDisplay(console, verbosity=verbosity)

        try:
            state = load_state(path)
            state.current_phase = Phase.PLANNING
            save_state(state, path)

            if verbosity >= 1:
                console.print(Panel("[bold blue]Planning Phase[/bold blue]", border_style="blue"))

            # Execute planning phase with streaming
            # Pass UI callbacks so spinner integrates with user input
            executor = PlanningExecutor(
                path, user_input_callbacks=display.get_user_input_callbacks()
            )
            gen = executor.stream_execution()

            # Start the generator
            event = await gen.asend(None)

            while True:
                try:
                    # Handle event and get potential user input
                    user_input = display.handle_event(event)

                    # Send user input back (if any) and get next event
                    event = await gen.asend(user_input)

                except StopAsyncIteration:
                    break

            # Show summary
            if verbosity >= 1:
                console.print("\n[green]Planning complete![/green]")
                console.print(f"[dim]{display.get_summary()}[/dim]")

                # List created tasks
                if plan_exists(path):
                    plan = load_plan(path)
                    if plan.tasks:
                        console.print(f"[dim]Created {len(plan.tasks)} tasks[/dim]")

            return True

        except (StateNotFoundError, CorruptedStateError) as e:
            console.print(f"[red]Error: {e}[/red]")
            return False
        except KeyboardInterrupt:
            console.print("\n[yellow]Planning interrupted by user[/yellow]")
            return False
        except Exception as e:
            console.print(f"[red]Planning failed: {e}[/red]")
            return False

    success = asyncio.run(run_streaming_planning())
    if not success:
        raise typer.Exit(1)

    # Auto-transition to next phase
    if not no_auto:
        from ralph.transitions import prompt_phase_transition

        should_continue, next_phase = asyncio.run(
            prompt_phase_transition(console, Phase.PLANNING, auto_timeout)
        )
        if should_continue and next_phase == Phase.BUILDING:
            build(
                project_root=project_root,
                task_id=None,
                quiet=quiet,
                no_auto=no_auto,
                auto_timeout=auto_timeout,
            )


@app.command()
def build(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
    task_id: str = typer.Option(None, "--task", "-t", help="Specific task to work on"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Quiet output (hide LLM text)"),
    no_auto: bool = typer.Option(
        False, "--no-auto", help="Disable auto-transition to next phase"
    ),
    auto_timeout: int = typer.Option(
        60, "--auto-timeout", help="Seconds before auto-transition (default: 60)"
    ),
) -> None:
    """Run the Building phase with iterative task execution.

    This command implements tasks from the plan using TDD and backpressure.
    It can target a specific task with --task or work through all pending tasks.

    By default, shows full LLM output as it streams.
    Use --quiet to hide LLM text and show only tool calls and summaries.

    After completion, automatically transitions to Validation phase in 60 seconds.
    Use --no-auto to disable auto-transition.
    """
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    if not state_exists(path):
        console.print(f"[yellow]Ralph not initialized in {path}[/yellow]")
        raise typer.Exit(1)

    # Determine verbosity level: default is verbose (2), --quiet gives normal (1)
    verbosity = 1 if quiet else 2

    async def run_streaming_building() -> bool:
        """Run building with streaming output."""
        display = RalphLiveDisplay(console, verbosity=verbosity)

        try:
            state = load_state(path)
            state.current_phase = Phase.BUILDING
            save_state(state, path)

            if verbosity >= 1:
                console.print(
                    Panel("[bold green]Building Phase[/bold green]", border_style="green")
                )
                if task_id:
                    console.print(f"[bold]Target task:[/bold] {task_id}\n")

            # Execute building phase with streaming
            # Pass UI callbacks so spinner integrates with user input
            executor = BuildingExecutor(
                path, user_input_callbacks=display.get_user_input_callbacks()
            )
            gen = executor.stream_execution(target_task_id=task_id)

            # Start the generator
            event = await gen.asend(None)

            while True:
                try:
                    # Handle event and get potential user input
                    user_input = display.handle_event(event)

                    # Send user input back (if any) and get next event
                    event = await gen.asend(user_input)

                except StopAsyncIteration:
                    break

            # Show summary
            if verbosity >= 1:
                console.print("\n[green]Building complete![/green]")
                console.print(f"[dim]{display.get_summary()}[/dim]")

            return True

        except (StateNotFoundError, CorruptedStateError) as e:
            console.print(f"[red]Error: {e}[/red]")
            return False
        except KeyboardInterrupt:
            console.print("\n[yellow]Building interrupted by user[/yellow]")
            return False
        except Exception as e:
            console.print(f"[red]Building failed: {e}[/red]")
            return False

    success = asyncio.run(run_streaming_building())
    if not success:
        raise typer.Exit(1)

    # Auto-transition to next phase
    if not no_auto:
        from ralph.transitions import prompt_phase_transition

        should_continue, next_phase = asyncio.run(
            prompt_phase_transition(console, Phase.BUILDING, auto_timeout)
        )
        if should_continue and next_phase == Phase.VALIDATION:
            validate(
                project_root=project_root,
                quiet=quiet,
            )


@app.command()
def validate(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Quiet output (hide LLM text)"),
) -> None:
    """Run the Validation phase with verification.

    This command runs comprehensive verification including tests, linting,
    type checking, and spec compliance. It may require human approval
    if configured.

    By default, shows full LLM output as it streams.
    Use --quiet to hide LLM text and show only tool calls and summaries.

    This is the final phase in the workflow.
    """
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    if not state_exists(path):
        console.print(f"[yellow]Ralph not initialized in {path}[/yellow]")
        raise typer.Exit(1)

    # Determine verbosity level: default is verbose (2), --quiet gives normal (1)
    verbosity = 1 if quiet else 2

    async def run_streaming_validation() -> bool:
        """Run validation with streaming output."""
        display = RalphLiveDisplay(console, verbosity=verbosity)

        try:
            state = load_state(path)
            state.current_phase = Phase.VALIDATION
            save_state(state, path)

            if verbosity >= 1:
                console.print(
                    Panel("[bold yellow]Validation Phase[/bold yellow]", border_style="yellow")
                )

            # Execute validation phase with streaming
            # Pass UI callbacks so spinner integrates with user input
            executor = ValidationExecutor(
                path, user_input_callbacks=display.get_user_input_callbacks()
            )
            gen = executor.stream_execution()

            # Start the generator
            event = await gen.asend(None)

            while True:
                try:
                    # Handle event and get potential user input
                    user_input = display.handle_event(event)

                    # Send user input back (if any) and get next event
                    event = await gen.asend(user_input)

                except StopAsyncIteration:
                    break

            # Show summary
            if verbosity >= 1:
                console.print("\n[green]Validation complete![/green]")
                console.print(f"[dim]{display.get_summary()}[/dim]")

            return True

        except (StateNotFoundError, CorruptedStateError) as e:
            console.print(f"[red]Error: {e}[/red]")
            return False
        except KeyboardInterrupt:
            console.print("\n[yellow]Validation interrupted by user[/yellow]")
            return False
        except Exception as e:
            console.print(f"[red]Validation failed: {e}[/red]")
            return False

    success = asyncio.run(run_streaming_validation())
    if not success:
        raise typer.Exit(1)

    # Show workflow completion message (VALIDATION is the final phase)
    from ralph.transitions import prompt_phase_transition

    asyncio.run(prompt_phase_transition(console, Phase.VALIDATION, 0))


@app.command("regenerate-plan")
def regenerate_plan(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
    discard_completed: bool = typer.Option(
        False, "--discard-completed", help="Discard completed tasks (default: keep them)"
    ),
) -> None:
    """Regenerate the implementation plan from specs.

    Discards the current plan and re-runs the planning phase.
    Useful when the plan has diverged from reality or specs have changed.
    """
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    if not state_exists(path):
        console.print(f"[yellow]Ralph not initialized in {path}[/yellow]")
        raise typer.Exit(1)

    try:
        # Load current plan to preserve completed tasks if requested
        completed_tasks = []
        if not discard_completed and plan_exists(path):
            old_plan = load_plan(path)
            completed_tasks = [t for t in old_plan.tasks if t.status == TaskStatus.COMPLETE]
            if completed_tasks:
                console.print(f"[dim]Preserving {len(completed_tasks)} completed tasks[/dim]")

        # Confirm regeneration
        if plan_exists(path):
            plan = load_plan(path)
            pending = plan.pending_count
            if pending > 0:
                confirm = typer.confirm(
                    f"This will discard {pending} pending tasks. Continue?"
                )
                if not confirm:
                    console.print("[dim]Aborted[/dim]")
                    raise typer.Exit(0)

        # Reset plan
        new_plan = initialize_plan(path)

        # Re-add completed tasks if requested
        if not discard_completed and completed_tasks:
            new_plan.tasks = completed_tasks
            save_plan(new_plan, path)

        # Update state to planning phase
        state = load_state(path)
        state.current_phase = Phase.PLANNING
        save_state(state, path)

        console.print("[green]✓ Plan regenerated[/green]")
        console.print("[dim]Phase set to: planning[/dim]")
        if not discard_completed:
            console.print(f"[dim]Preserved tasks: {len(completed_tasks)}[/dim]")
        console.print("\n[bold]Run 'ralph plan' to create new tasks from specs[/bold]")

    except (StateNotFoundError, CorruptedStateError) as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def handoff(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
    reason: str = typer.Option("manual", "--reason", "-r", help="Handoff reason"),
    summary: str = typer.Option(None, "--summary", "-s", help="Session summary"),
) -> None:
    """Manually trigger a context handoff."""
    try:
        path = _resolve_project_root(project_root)
    except typer.BadParameter as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    if not state_exists(path):
        console.print(f"[yellow]Ralph not initialized in {path}[/yellow]")
        raise typer.Exit(1)

    try:
        state = load_state(path)
        plan = load_plan(path) if plan_exists(path) else None

        if plan is None:
            console.print("[yellow]No plan found, creating empty plan[/yellow]")
            plan = initialize_plan(path)

        result = execute_context_handoff(
            state=state,
            plan=plan,
            project_root=path,
            reason=reason,
            session_summary=summary,
        )

        if result.success:
            console.print("[green]Context handoff completed successfully[/green]")
            console.print(f"[dim]Memory file: {result.memory_path}[/dim]")
            console.print(f"[dim]Next session ID: {result.next_session_id}[/dim]")
        else:
            console.print(f"[red]Handoff failed: {result.reason}[/red]")
            raise typer.Exit(1)

    except (StateNotFoundError, CorruptedStateError) as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()
