"""Ralph CLI entry point using Typer."""

import asyncio
import subprocess
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ralph import __version__
from ralph.config import load_config
from ralph.context import (
    add_injection,
    execute_context_handoff,
    load_session_history,
)
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
) -> None:
    """Run the Discovery phase with JTBD framework."""
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
        state.current_phase = Phase.DISCOVERY
        save_state(state, path)

        console.print(Panel("[bold cyan]Discovery Phase[/bold cyan]", border_style="cyan"))
        if goal:
            console.print(f"[bold]Goal:[/bold] {goal}")

        # Execute discovery phase
        executor = DiscoveryExecutor(path)
        result = asyncio.run(executor.execute(initial_goal=goal))

        if result.success:
            console.print("[green]Discovery complete![/green]")
            if result.artifacts.get("specs_created"):
                specs = ", ".join(result.artifacts["specs_created"])
                console.print(f"[dim]Created specs: {specs}[/dim]")
        else:
            console.print(f"[red]Discovery failed: {result.error}[/red]")
            raise typer.Exit(1)

    except (StateNotFoundError, CorruptedStateError) as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def plan(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
) -> None:
    """Run the Planning phase with gap analysis."""
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
        state.current_phase = Phase.PLANNING
        save_state(state, path)

        console.print(Panel("[bold blue]Planning Phase[/bold blue]", border_style="blue"))

        # Execute planning phase
        executor = PlanningExecutor(path)
        result = asyncio.run(executor.execute())

        if result.success:
            console.print("[green]Planning complete![/green]")
            if result.artifacts.get("tasks_created"):
                console.print(f"[dim]Created {result.artifacts['tasks_created']} tasks[/dim]")
        else:
            console.print(f"[red]Planning failed: {result.error}[/red]")
            raise typer.Exit(1)

    except (StateNotFoundError, CorruptedStateError) as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def build(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
    task_id: str = typer.Option(None, "--task", "-t", help="Specific task to work on"),
) -> None:
    """Run the Building phase with iterative task execution."""
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
        state.current_phase = Phase.BUILDING
        save_state(state, path)

        console.print(Panel("[bold green]Building Phase[/bold green]", border_style="green"))

        if task_id:
            console.print(f"[bold]Target task:[/bold] {task_id}")

        # Execute building phase
        executor = BuildingExecutor(path)
        result = asyncio.run(executor.execute(target_task_id=task_id))

        if result.success:
            console.print("[green]Building complete![/green]")
            tasks = result.tasks_completed
            iters = result.iterations_run
            console.print(f"[dim]Completed {tasks} tasks in {iters} iterations[/dim]")
        else:
            console.print(f"[red]Building failed: {result.error}[/red]")
            raise typer.Exit(1)

    except (StateNotFoundError, CorruptedStateError) as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def validate(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory"),
) -> None:
    """Run the Validation phase with verification."""
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
        state.current_phase = Phase.VALIDATION
        save_state(state, path)

        console.print(Panel("[bold yellow]Validation Phase[/bold yellow]", border_style="yellow"))

        # Execute validation phase
        executor = ValidationExecutor(path)
        result = asyncio.run(executor.execute())

        if result.success:
            console.print("[green]Validation complete![/green]")
            console.print("[dim]All checks passed[/dim]")
        else:
            msg = result.error or "Some checks failed"
            console.print(f"[yellow]Validation incomplete: {msg}[/yellow]")
            raise typer.Exit(1)

    except (StateNotFoundError, CorruptedStateError) as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None


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
