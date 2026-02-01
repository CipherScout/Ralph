"""Terminal animations and patience phrases for Ralph CLI.

This module provides engaging terminal animations similar to Claude Code's
spinner experience - an animated in-place spinner with status messages
and token counters.
"""

from __future__ import annotations

import contextlib
import random
import threading
import time

from rich.console import Console
from rich.live import Live
from rich.text import Text

# Claude Code style braille spinner frames (fixed-width for smooth animation)
BRAILLE_SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# Thinking verbs (like Claude Code uses)
THINKING_VERBS: list[str] = [
    "Thinking",
    "Pondering",
    "Analyzing",
    "Processing",
    "Considering",
    "Reasoning",
    "Working",
    "Computing",
    "Evaluating",
    "Synthesizing",
]

# Patience phrases organized by category
PATIENCE_PHRASES: dict[str, list[str]] = {
    "thinking": [
        "Pondering the mysteries of code...",
        "Consulting the algorithm oracles...",
        "Weaving digital threads...",
        "Searching the knowledge matrix...",
        "Communing with the code spirits...",
        "Synthesizing solutions...",
        "Architecting elegance...",
        "Channeling creativity...",
        "Exploring the codescape...",
        "Brewing fresh ideas...",
    ],
    "reading": [
        "Absorbing knowledge...",
        "Studying the codebase...",
        "Parsing patterns...",
        "Connecting the dots...",
        "Comprehending complexity...",
        "Mapping the terrain...",
        "Understanding the architecture...",
        "Learning the ways...",
        "Decoding the structure...",
        "Analyzing relationships...",
    ],
    "writing": [
        "Crafting code with care...",
        "Sculpting solutions...",
        "Building brick by brick...",
        "Weaving new functionality...",
        "Painting with pixels of logic...",
        "Constructing carefully...",
        "Creating something beautiful...",
        "Assembling the pieces...",
        "Forging new features...",
        "Implementing with intention...",
    ],
    "testing": [
        "Ensuring quality...",
        "Verifying correctness...",
        "Testing all the things...",
        "Hunting for bugs...",
        "Validating assumptions...",
        "Checking our work...",
        "Running the gauntlet...",
        "Stress testing...",
        "Confirming behavior...",
        "Double-checking everything...",
    ],
    "planning": [
        "Charting the course...",
        "Mapping the journey...",
        "Strategizing...",
        "Plotting the path forward...",
        "Designing the approach...",
        "Outlining the plan...",
        "Calculating the route...",
        "Preparing the blueprint...",
        "Setting milestones...",
        "Defining the roadmap...",
    ],
    "discovery": [
        "Asking the right questions...",
        "Gathering requirements...",
        "Understanding your needs...",
        "Exploring possibilities...",
        "Uncovering insights...",
        "Listening carefully...",
        "Clarifying the vision...",
        "Diving deep...",
        "Finding the essence...",
        "Illuminating the path...",
    ],
    "waiting": [
        "Good things take time...",
        "Patience is a virtue...",
        "Almost there...",
        "Working diligently...",
        "Making progress...",
        "Hang tight...",
        "Worth the wait...",
        "Coming together nicely...",
        "Taking shape...",
        "Getting closer...",
    ],
}

# Fun facts about coding to display during long waits
CODING_FACTS: list[str] = [
    "The first computer bug was an actual bug - a moth found in a relay.",
    "Python was named after Monty Python, not the snake.",
    "The first programmer was Ada Lovelace, in the 1840s.",
    "Git was created by Linus Torvalds in just two weeks.",
    "The term 'debugging' predates computers by centuries.",
    "'Hello World' was first used in a 1972 C tutorial.",
    "FORTRAN, created in 1957, is still used in scientific computing.",
    "JavaScript was created in just 10 days.",
    "The @ symbol was almost forgotten before email revived it.",
    "USB was designed to be flipped in the wrong way first.",
]


def get_random_phrase(category: str = "thinking") -> str:
    """Get a random patience phrase from the specified category."""
    phrases = PATIENCE_PHRASES.get(category, PATIENCE_PHRASES["waiting"])
    return random.choice(phrases)


def get_random_thinking_verb() -> str:
    """Get a random thinking verb."""
    return random.choice(THINKING_VERBS)


def get_random_fact() -> str:
    """Get a random coding fact."""
    return random.choice(CODING_FACTS)


def format_token_count(tokens: int) -> str:
    """Format token count for display with compact representation for large numbers.

    Args:
        tokens: Number of tokens to format

    Returns:
        Formatted string (e.g., "1,500", "1.2M", "2.5M")
    """
    if tokens >= 1_000_000:
        # Format millions with one decimal place
        millions = tokens / 1_000_000
        return f"{millions:.1f}M"
    elif tokens >= 1000:
        # Use comma formatting for thousands
        return f"{tokens:,}"
    else:
        # Regular formatting for small numbers
        return str(tokens)


class ThinkingSpinner:
    """Claude Code-style animated spinner with token counter.

    Shows an animated braille spinner that updates in-place with:
    - Animated spinner character
    - Thinking verb that changes periodically
    - Token counter (if provided)
    - Optional tip/phrase

    Thread-safe implementation using threading.Event for synchronization.
    """

    def __init__(
        self,
        console: Console,
        refresh_rate: float = 0.1,
        show_tips: bool = True,
    ) -> None:
        """Initialize the thinking spinner.

        Args:
            console: Rich Console for output
            refresh_rate: How often to update the animation (seconds)
            show_tips: Whether to show patience phrases
        """
        self.console = console
        self.refresh_rate = refresh_rate
        self.show_tips = show_tips

        # Thread synchronization
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._animation_thread: threading.Thread | None = None

        # Animation state
        self._frame_index = 0
        self._tokens = 0
        self._cost = 0.0
        self._verb = get_random_thinking_verb()
        self._tip = get_random_phrase("thinking") if show_tips else ""
        self._live: Live | None = None
        self._last_verb_change = time.time()
        self._verb_change_interval = 3.0  # Change verb every 3 seconds

    def _render(self) -> Text:
        """Render the current spinner state."""
        # Get current spinner frame
        frame = BRAILLE_SPINNER[self._frame_index % len(BRAILLE_SPINNER)]

        # Build the display text
        text = Text()

        # Spinner and verb
        text.append(f" {frame} ", style="bold cyan")
        text.append(f"{self._verb}", style="bold white")

        # Token counter if we have tokens
        if self._tokens > 0:
            formatted_tokens = format_token_count(self._tokens)
            text.append(f" ({formatted_tokens} tokens", style="dim")
            if self._cost > 0:
                text.append(f", ${self._cost:.4f}", style="dim")
            text.append(")", style="dim")
        else:
            text.append("...", style="dim")

        # Tip on the same line (shortened)
        if self.show_tips and self._tip:
            # Truncate tip to fit
            max_tip_len = 40
            if len(self._tip) > max_tip_len:
                tip_display = self._tip[:max_tip_len] + "..."
            else:
                tip_display = self._tip
            text.append(f"  {tip_display}", style="dim cyan italic")

        return text

    def start(self) -> None:
        """Start the animated spinner."""
        # Wait for any previous thread to finish first
        if self._animation_thread is not None and self._animation_thread.is_alive():
            self._stop_event.set()
            self._animation_thread.join(timeout=0.5)

        # Clear the stop event for the new run
        self._stop_event.clear()

        # Reset animation state
        self._frame_index = 0
        self._verb = get_random_thinking_verb()
        self._tip = get_random_phrase("thinking") if self.show_tips else ""
        self._last_verb_change = time.time()

        # Create and start Live display with lock protection
        with self._lock:
            self._live = Live(
                self._render(),
                console=self.console,
                refresh_per_second=int(1 / self.refresh_rate),
                transient=True,  # Remove spinner when stopped
            )
            self._live.start()

        # Start animation thread
        self._animation_thread = threading.Thread(target=self._animate, daemon=True)
        self._animation_thread.start()

    def _animate(self) -> None:
        """Animation loop running in background thread."""
        while not self._stop_event.is_set():
            self._frame_index += 1

            # Periodically change the thinking verb
            now = time.time()
            if now - self._last_verb_change > self._verb_change_interval:
                self._verb = get_random_thinking_verb()
                self._tip = get_random_phrase("thinking") if self.show_tips else ""
                self._last_verb_change = now

            # Update the display with lock protection
            with self._lock:
                if self._live:
                    try:
                        self._live.update(self._render())
                    except Exception:
                        # Live display may have been stopped
                        break

            # Interruptible sleep - returns True if stop event is set
            if self._stop_event.wait(self.refresh_rate):
                break

    def update(
        self,
        tokens: int | None = None,
        cost: float | None = None,
        message: str | None = None,
    ) -> None:
        """Update the spinner with new information.

        Args:
            tokens: Updated token count
            cost: Updated cost
            message: Custom message to display as tip
        """
        if tokens is not None:
            self._tokens = tokens
        if cost is not None:
            self._cost = cost
        if message is not None:
            self._tip = message

    def stop(self) -> None:
        """Stop the spinner animation."""
        # Signal the animation thread to stop
        self._stop_event.set()

        # Wait for thread to finish
        if self._animation_thread is not None:
            self._animation_thread.join(timeout=0.5)
            self._animation_thread = None

        # Clean up Live display with lock protection
        with self._lock:
            if self._live:
                with contextlib.suppress(Exception):
                    self._live.stop()
                self._live = None


class PhaseAnimation:
    """Animated display for phase transitions."""

    PHASE_ART: dict[str, str] = {
        "discovery": """
[bold cyan]
    Discovery Phase
    ===============
      ?   ?   ?
     / \\ / \\ / \\
    Gathering Requirements
[/bold cyan]""",
        "planning": """
[bold blue]
    Planning Phase
    ==============
    [ ] -> [ ] -> [ ]
     |      |      |
    Mapping the Path
[/bold blue]""",
        "building": """
[bold green]
    Building Phase
    ==============
       ___
      |   |  /\\
      |___|_/  \\
     [=======]
    Constructing...
[/bold green]""",
        "validation": """
[bold yellow]
    Validation Phase
    ================
      [OK]  [OK]  [OK]
       |     |     |
    Verifying Quality
[/bold yellow]""",
    }

    def __init__(self, console: Console) -> None:
        """Initialize phase animation display."""
        self.console = console

    def show_phase_banner(self, phase: str) -> None:
        """Show an animated banner for phase transition."""
        phase_lower = phase.lower()
        art = self.PHASE_ART.get(phase_lower, f"[bold]{phase} Phase[/bold]")
        self.console.print(art)
