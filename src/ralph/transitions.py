"""Phase transition helpers with auto-continue functionality.

This module provides prompts for transitioning between Ralph phases.
Transitions auto-continue after a brief pause.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ralph.cleanup import CleanupResult, cleanup_state_files
from ralph.models import Phase

# Phase order for transitions
PHASE_ORDER: list[Phase] = [
    Phase.DISCOVERY,
    Phase.PLANNING,
    Phase.BUILDING,
    Phase.VALIDATION,
]


def get_next_phase(current_phase: Phase) -> Phase | None:
    """Get the next phase in the workflow.

    Args:
        current_phase: The phase that just completed

    Returns:
        The next phase, or None if current phase is VALIDATION (final phase)
    """
    try:
        current_index = PHASE_ORDER.index(current_phase)
        if current_index < len(PHASE_ORDER) - 1:
            return PHASE_ORDER[current_index + 1]
    except ValueError:
        pass
    return None


class PhaseTransitionPrompt:
    """Phase transition prompt that auto-continues after a brief pause.

    Displays a message showing the completed phase and the next phase,
    then automatically continues after a short delay.
    """

    def __init__(
        self,
        console: Console,
        current_phase: Phase,
        next_phase: Phase,
        timeout_seconds: int = 60,
    ) -> None:
        """Initialize the phase transition prompt.

        Args:
            console: Rich Console for display
            current_phase: The phase that just completed
            next_phase: The phase to transition to
            timeout_seconds: Kept for API compatibility (ignored)
        """
        self.console = console
        self.current_phase = current_phase
        self.next_phase = next_phase
        self.timeout_seconds = timeout_seconds

    def _render(self) -> Panel:
        """Render the transition display."""
        text = Text()
        text.append("Phase ", style="bold")
        text.append(f"{self.current_phase.value}", style="bold cyan")
        text.append(" complete!\n\n", style="bold")

        text.append("Continuing to ", style="white")
        text.append(f"{self.next_phase.value}", style="bold green")
        text.append("...", style="white")

        return Panel(
            text,
            title="[bold blue]Phase Transition[/bold blue]",
            border_style="blue",
        )

    async def prompt(self) -> bool:
        """Show the transition message and auto-continue after a brief pause.

        Returns:
            True (always auto-continues)
        """
        # Non-interactive mode detection
        if not sys.stdin.isatty():
            self.console.print(
                f"\n[yellow]Non-interactive mode: auto-continuing to "
                f"{self.next_phase.value}[/yellow]"
            )
            return True

        # Handle zero timeout - auto-continue immediately
        if self.timeout_seconds == 0:
            return True

        # Show transition message and pause briefly
        self.console.print(self._render())
        await asyncio.sleep(2)
        return True


class WorkflowCleanupPrompt:
    """Prompt for cleaning up state after workflow completion."""

    def __init__(self, console: Console) -> None:
        """Initialize the cleanup prompt.

        Args:
            console: Rich Console for display
        """
        self.console = console

    def _render_cleanup_preview(self, include_memory: bool) -> Panel:
        """Render information about what will be cleaned up.

        Args:
            include_memory: Whether memory files are included

        Returns:
            Rich Panel showing cleanup preview
        """
        text = Text()
        text.append("The following files will be ", style="white")
        text.append("removed", style="bold red")
        text.append(":\n\n", style="white")

        text.append("  \u2022 .ralph/state.json\n", style="dim")
        text.append("  \u2022 .ralph/implementation_plan.json\n", style="dim")
        text.append("  \u2022 .ralph/injections.json\n", style="dim")

        if include_memory:
            text.append("\n  \u2022 .ralph/MEMORY.md\n", style="dim yellow")
            text.append("  \u2022 .ralph/memory/ (directory)\n", style="dim yellow")

        text.append("\n", style="white")
        text.append("Configuration (.ralph/config.yaml) will be ", style="white")
        text.append("preserved", style="bold green")
        text.append(".", style="white")

        return Panel(
            text,
            title="[bold]Cleanup Preview[/bold]",
            border_style="yellow",
        )

    def prompt(self, project_root: Path) -> tuple[bool, bool]:
        """Prompt user for cleanup decision.

        Args:
            project_root: Path to project root

        Returns:
            Tuple of (should_cleanup, include_memory)
        """
        # Non-interactive mode - don't cleanup by default
        if not sys.stdin.isatty():
            self.console.print(
                "\n[yellow]Non-interactive mode: skipping cleanup prompt[/yellow]"
            )
            return False, False

        self.console.print()  # Blank line after workflow complete

        # First prompt: cleanup state?
        should_cleanup = typer.confirm(
            "Clean up workflow state for a fresh start?",
            default=False,
        )

        if not should_cleanup:
            self.console.print(
                "[dim]State preserved. Run 'ralph reset' later if needed.[/dim]"
            )
            return False, False

        # Second prompt: include memory?
        include_memory = typer.confirm(
            "Also remove session memory (MEMORY.md)?",
            default=False,
        )

        # Show what will be cleaned
        self.console.print(self._render_cleanup_preview(include_memory))

        # Final confirmation
        final_confirm = typer.confirm("Proceed with cleanup?", default=True)

        if not final_confirm:
            self.console.print("[dim]Cleanup cancelled.[/dim]")
            return False, False

        return True, include_memory

    def execute_cleanup(
        self,
        project_root: Path,
        include_memory: bool,
    ) -> CleanupResult:
        """Execute the cleanup and display results.

        Args:
            project_root: Path to project root
            include_memory: Whether to include memory files

        Returns:
            CleanupResult with details of what was deleted
        """
        result = cleanup_state_files(project_root, include_memory)

        if result.any_cleaned:
            self.console.print()
            for deleted in result.files_deleted:
                self.console.print(f"[green]\u2713 Deleted: {deleted}[/green]")

        if result.errors:
            self.console.print()
            for error in result.errors:
                self.console.print(f"[red]\u2717 Error: {error}[/red]")

        if result.success and result.any_cleaned:
            self.console.print()
            self.console.print(
                Panel(
                    "[bold green]Cleanup complete![/bold green]\n\n"
                    "Run 'ralph init' to start a new workflow.",
                    title="[bold]Ready for Next Project[/bold]",
                    border_style="green",
                )
            )
        elif not result.any_cleaned:
            self.console.print("[dim]No files to clean up.[/dim]")

        return result


async def prompt_phase_transition(
    console: Console,
    current_phase: Phase,
    timeout_seconds: int = 60,
    project_root: Path | None = None,
) -> tuple[bool, Phase | None]:
    """Prompt user for phase transition.

    Args:
        console: Rich Console for display
        current_phase: The phase that just completed
        timeout_seconds: Kept for API compatibility (ignored)
        project_root: Path to project root (for cleanup on final phase)

    Returns:
        Tuple of (should_continue, next_phase)
        - (True, Phase) if should continue to next phase
        - (False, None) if user chose to exit
        - (True, None) if current phase is final (VALIDATION)
    """
    next_phase = get_next_phase(current_phase)

    if next_phase is None:
        # Final phase - show completion and offer cleanup
        console.print(
            Panel(
                "[bold green]All phases complete![/bold green]\n\n"
                "The Ralph workflow has finished successfully.",
                title="[bold]Workflow Complete[/bold]",
                border_style="green",
            )
        )

        # Offer cleanup if project_root provided
        if project_root is not None:
            cleanup_prompt = WorkflowCleanupPrompt(console)
            should_cleanup, include_memory = cleanup_prompt.prompt(project_root)

            if should_cleanup:
                cleanup_prompt.execute_cleanup(project_root, include_memory)

        return True, None

    transition = PhaseTransitionPrompt(
        console=console,
        current_phase=current_phase,
        next_phase=next_phase,
        timeout_seconds=timeout_seconds,
    )

    try:
        should_continue = await transition.prompt()
        if should_continue:
            return True, next_phase
        else:
            console.print("\n[yellow]Phase transition cancelled by user.[/yellow]")
            return False, None
    except KeyboardInterrupt:
        console.print("\n[yellow]Phase transition interrupted.[/yellow]")
        return False, None
