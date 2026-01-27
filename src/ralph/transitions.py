"""Phase transition helpers with auto-continue functionality.

This module provides interactive prompts for transitioning between Ralph phases
with countdown timers that auto-continue if no user input is received.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from ralph.async_input_reader import AsyncInputReader
from ralph.cleanup import CleanupResult, cleanup_state_files
from ralph.models import Phase

if TYPE_CHECKING:
    pass

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
    """Rich-based countdown prompt for phase transitions.

    Shows a countdown timer with the option to:
    - Press Enter or 'y' to continue immediately
    - Press 'n' to exit
    - Let timer expire to auto-continue
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
            timeout_seconds: Seconds before auto-continuing (default 60)
        """
        self.console = console
        self.current_phase = current_phase
        self.next_phase = next_phase
        self.timeout_seconds = timeout_seconds
        self._remaining = timeout_seconds
        self._cancelled = False

    def _render(self) -> Panel:
        """Render the countdown display."""
        text = Text()
        text.append("Phase ", style="bold")
        text.append(f"{self.current_phase.value}", style="bold cyan")
        text.append(" complete!\n\n", style="bold")

        text.append("Continue to ", style="white")
        text.append(f"{self.next_phase.value}", style="bold green")
        text.append("? ", style="white")
        text.append("(Y/n)", style="dim")
        text.append("\n\n", style="white")

        # Countdown display
        text.append("Auto-continuing in ", style="yellow")
        text.append(f"{self._remaining}", style="bold yellow")
        text.append(" seconds...", style="yellow")
        text.append("\n", style="white")
        text.append("Press ", style="dim")
        text.append("Enter", style="bold dim")
        text.append(" to continue, ", style="dim")
        text.append("n", style="bold dim")
        text.append(" to exit", style="dim")

        return Panel(
            text,
            title="[bold blue]Phase Transition[/bold blue]",
            border_style="blue",
        )

    async def _countdown_task(
        self,
        live: Live,
        input_received_event: asyncio.Event | None = None,
        completion_lock: asyncio.Lock | None = None,
        result_holder: dict[str, bool | str] | None = None
    ) -> None:
        """Countdown timer that updates the display.

        Args:
            live: Rich Live object for updating display
            input_received_event: Event that signals when user input is received
            completion_lock: Lock to prevent race conditions on completion
            result_holder: Dict to store the result safely
        """
        try:
            while (
                self._remaining > 0
                and not self._cancelled
                and (input_received_event is None or not input_received_event.is_set())
            ):
                live.update(self._render())
                await asyncio.sleep(1)
                self._remaining -= 1

            # Final update before completion
            live.update(self._render())

            # Set result atomically if we completed first
            if completion_lock and result_holder and not result_holder["set"]:
                async with completion_lock:
                    if not result_holder["set"]:
                        result_holder["value"] = True  # Countdown expiry = auto-continue
                        result_holder["set"] = True

        except asyncio.CancelledError:
            # Clean cancellation - update display one final time if possible
            with contextlib.suppress(Exception):
                live.update(self._render())
            raise

    async def _input_task(
        self,
        input_received_event: asyncio.Event | None = None,
        completion_lock: asyncio.Lock | None = None,
        result_holder: dict[str, bool | str] | None = None
    ) -> str:
        """Read user input asynchronously using AsyncInputReader.

        Args:
            input_received_event: Event to signal when input is received
            completion_lock: Lock to prevent race conditions on completion
            result_holder: Dict to store the result safely

        Returns:
            User input string
        """
        reader = AsyncInputReader()
        try:
            user_input = await reader.read_input()
            # Process the input (strip and lowercase for consistency)
            processed_input = user_input.strip().lower()

            # Set result atomically if we completed first
            if completion_lock and result_holder and not result_holder["set"]:
                async with completion_lock:
                    if not result_holder["set"]:
                        # 'n' or 'no' means don't continue, anything else means continue
                        result_holder["value"] = processed_input not in ("n", "no")
                        result_holder["set"] = True

            # Signal that input was received if event provided
            if input_received_event is not None:
                input_received_event.set()

            return processed_input

        except EOFError:
            # Non-interactive mode or end of input
            if completion_lock and result_holder and not result_holder["set"]:
                async with completion_lock:
                    if not result_holder["set"]:
                        result_holder["value"] = True  # Default to continue
                        result_holder["set"] = True

            if input_received_event is not None:
                input_received_event.set()

            return ""

        except asyncio.CancelledError:
            # Clean cancellation - still signal event if needed
            if input_received_event is not None:
                input_received_event.set()
            raise

        except Exception:
            # Handle other exceptions gracefully
            if completion_lock and result_holder and not result_holder["set"]:
                async with completion_lock:
                    if not result_holder["set"]:
                        result_holder["value"] = True  # Default to continue on error
                        result_holder["set"] = True

            if input_received_event is not None:
                input_received_event.set()

            return ""

    async def prompt(self) -> bool:
        """Show the countdown prompt and return user decision.

        Returns:
            True if should continue to next phase, False if should exit
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

        # Create event for coordinating input reception and completion
        input_received_event = asyncio.Event()
        completion_lock = asyncio.Lock()
        result_holder: dict[str, bool | str] = {"value": True, "set": False}

        with Live(
            self._render(),
            console=self.console,
            refresh_per_second=2,
            transient=False,
        ) as live:
            # Check if methods support the new event-based coordination
            input_task_sig = inspect.signature(self._input_task)
            countdown_task_sig = inspect.signature(self._countdown_task)

            # Create tasks - use event coordination if signatures support it
            # New signature: _input_task(event, lock, result_holder)
            # Old signature: _input_task() or _input_task(event)
            if len(input_task_sig.parameters) >= 3:
                # New signature with race condition prevention
                countdown = asyncio.create_task(
                    self._countdown_task(live, input_received_event, completion_lock, result_holder)
                )
                input_task = asyncio.create_task(
                    self._input_task(input_received_event, completion_lock, result_holder)
                )
            elif len(input_task_sig.parameters) > 0 and len(countdown_task_sig.parameters) > 1:
                # Old signature with basic event coordination
                countdown = asyncio.create_task(self._countdown_task(live, input_received_event))
                input_task = asyncio.create_task(self._input_task(input_received_event))
            else:
                # Legacy signature - no event coordination
                countdown = asyncio.create_task(self._countdown_task(live))
                input_task = asyncio.create_task(self._input_task())

            try:
                # Wait for either countdown to finish or user input
                done, pending = await asyncio.wait(
                    [countdown, input_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Cancel all pending tasks with proper cleanup
                for task in pending:
                    task.cancel()

                # Wait for cancelled tasks to finish cleanup
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)

                # Use the result from whichever task completed first
                if result_holder["set"]:
                    return bool(result_holder["value"])

                # Fallback: check what completed (for backward compatibility)
                if input_task in done:
                    try:
                        user_input = input_task.result()
                        # 'n' or 'no' means don't continue, anything else means continue
                        return user_input not in ("n", "no")
                    except Exception:
                        return True

                # Countdown finished - auto-continue
                return True

            except asyncio.CancelledError:
                self._cancelled = True
                # Cancel all tasks before re-raising
                for task in [countdown, input_task]:
                    if not task.done():
                        task.cancel()

                # Clean up cancelled tasks
                await asyncio.gather(countdown, input_task, return_exceptions=True)
                raise


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
        text.append("  \u2022 progress.txt\n", style="dim")

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
    """Prompt user for phase transition with countdown.

    Args:
        console: Rich Console for display
        current_phase: The phase that just completed
        timeout_seconds: Seconds to wait before auto-continuing
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

    prompt = PhaseTransitionPrompt(
        console=console,
        current_phase=current_phase,
        next_phase=next_phase,
        timeout_seconds=timeout_seconds,
    )

    try:
        should_continue = await prompt.prompt()
        if should_continue:
            return True, next_phase
        else:
            console.print("\n[yellow]Phase transition cancelled by user.[/yellow]")
            return False, None
    except KeyboardInterrupt:
        console.print("\n[yellow]Phase transition interrupted.[/yellow]")
        return False, None
