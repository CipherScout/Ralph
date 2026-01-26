"""Terminal animations and patience phrases for Ralph CLI.

This module provides engaging terminal animations and patience phrases
to keep users engaged while Ralph is working on tasks.
"""

from __future__ import annotations

import random
from typing import Any

from rich.console import Console
from rich.spinner import Spinner
from rich.status import Status

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

# Spinner styles for different activities
SPINNER_STYLES: dict[str, str] = {
    "default": "dots",
    "thinking": "dots",
    "reading": "line",
    "writing": "dots12",
    "testing": "bouncingBar",
    "planning": "dots8Bit",
    "discovery": "aesthetic",
    "waiting": "moon",
}


def get_random_phrase(category: str = "thinking") -> str:
    """Get a random patience phrase from the specified category.

    Args:
        category: The category of phrases to choose from

    Returns:
        A random phrase string
    """
    phrases = PATIENCE_PHRASES.get(category, PATIENCE_PHRASES["waiting"])
    return random.choice(phrases)


def get_spinner_style(category: str = "default") -> str:
    """Get the spinner style for a category.

    Args:
        category: The activity category

    Returns:
        Spinner style name for Rich
    """
    return SPINNER_STYLES.get(category, SPINNER_STYLES["default"])


class PatienceDisplay:
    """Display patience phrases with animated spinners.

    This class provides context managers for showing animated
    status messages while Ralph is working.
    """

    def __init__(self, console: Console) -> None:
        """Initialize the patience display.

        Args:
            console: Rich Console instance for output
        """
        self.console = console
        self._status: Status | None = None
        self._phrase_counter = 0

    def start(self, category: str = "thinking") -> None:
        """Start showing an animated patience display.

        Args:
            category: The type of activity for phrase selection
        """
        phrase = get_random_phrase(category)
        spinner_style = get_spinner_style(category)
        self._status = self.console.status(
            f"[cyan]{phrase}[/cyan]",
            spinner=spinner_style,
            spinner_style="cyan",
        )
        self._status.start()

    def update(self, category: str = "thinking", custom_message: str | None = None) -> None:
        """Update the patience display with a new phrase.

        Args:
            category: The type of activity for phrase selection
            custom_message: Optional custom message to display
        """
        if self._status:
            if custom_message:
                self._status.update(f"[cyan]{custom_message}[/cyan]")
            else:
                phrase = get_random_phrase(category)
                self._status.update(f"[cyan]{phrase}[/cyan]")

    def stop(self) -> None:
        """Stop the patience display."""
        if self._status:
            self._status.stop()
            self._status = None


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
        """Initialize phase animation display.

        Args:
            console: Rich Console instance
        """
        self.console = console

    def show_phase_banner(self, phase: str) -> None:
        """Show an animated banner for phase transition.

        Args:
            phase: The phase name (discovery, planning, building, validation)
        """
        phase_lower = phase.lower()
        art = self.PHASE_ART.get(phase_lower, f"[bold]{phase} Phase[/bold]")
        self.console.print(art)


def get_tool_category(tool_name: str | None) -> str:
    """Map a tool name to a patience phrase category.

    Args:
        tool_name: The name of the tool being used

    Returns:
        Category string for phrase selection
    """
    if not tool_name:
        return "thinking"

    tool_categories: dict[str, str] = {
        "Read": "reading",
        "Glob": "reading",
        "Grep": "reading",
        "Write": "writing",
        "Edit": "writing",
        "Bash": "testing",
        "Task": "thinking",
        "WebSearch": "discovery",
        "WebFetch": "reading",
        "AskUserQuestion": "discovery",
    }

    return tool_categories.get(tool_name, "thinking")


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


def get_random_fact() -> str:
    """Get a random coding fact.

    Returns:
        A fun fact about coding/programming
    """
    return random.choice(CODING_FACTS)
