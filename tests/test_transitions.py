"""Tests for phase transitions module."""

import pytest

from ralph.models import Phase
from ralph.transitions import (
    PHASE_ORDER,
    PhaseTransitionPrompt,
    get_next_phase,
)


class TestPhaseOrder:
    """Tests for phase ordering."""

    def test_phase_order_contains_all_phases(self) -> None:
        """Phase order contains all four phases."""
        assert len(PHASE_ORDER) == 4
        assert Phase.DISCOVERY in PHASE_ORDER
        assert Phase.PLANNING in PHASE_ORDER
        assert Phase.BUILDING in PHASE_ORDER
        assert Phase.VALIDATION in PHASE_ORDER

    def test_phase_order_is_correct(self) -> None:
        """Phases are in the correct order."""
        assert PHASE_ORDER[0] == Phase.DISCOVERY
        assert PHASE_ORDER[1] == Phase.PLANNING
        assert PHASE_ORDER[2] == Phase.BUILDING
        assert PHASE_ORDER[3] == Phase.VALIDATION


class TestGetNextPhase:
    """Tests for get_next_phase function."""

    def test_discovery_to_planning(self) -> None:
        """Discovery transitions to Planning."""
        assert get_next_phase(Phase.DISCOVERY) == Phase.PLANNING

    def test_planning_to_building(self) -> None:
        """Planning transitions to Building."""
        assert get_next_phase(Phase.PLANNING) == Phase.BUILDING

    def test_building_to_validation(self) -> None:
        """Building transitions to Validation."""
        assert get_next_phase(Phase.BUILDING) == Phase.VALIDATION

    def test_validation_returns_none(self) -> None:
        """Validation is final phase, returns None."""
        assert get_next_phase(Phase.VALIDATION) is None


class TestPhaseTransitionPrompt:
    """Tests for PhaseTransitionPrompt class."""

    def test_creates_prompt_with_defaults(self) -> None:
        """Can create prompt with default timeout."""
        from rich.console import Console

        console = Console()
        prompt = PhaseTransitionPrompt(
            console=console,
            current_phase=Phase.DISCOVERY,
            next_phase=Phase.PLANNING,
        )

        assert prompt.current_phase == Phase.DISCOVERY
        assert prompt.next_phase == Phase.PLANNING
        assert prompt.timeout_seconds == 60

    def test_creates_prompt_with_custom_timeout(self) -> None:
        """Can create prompt with custom timeout."""
        from rich.console import Console

        console = Console()
        prompt = PhaseTransitionPrompt(
            console=console,
            current_phase=Phase.PLANNING,
            next_phase=Phase.BUILDING,
            timeout_seconds=30,
        )

        assert prompt.timeout_seconds == 30

    def test_render_returns_panel(self) -> None:
        """Render method returns a Rich Panel."""
        from rich.console import Console
        from rich.panel import Panel

        console = Console()
        prompt = PhaseTransitionPrompt(
            console=console,
            current_phase=Phase.BUILDING,
            next_phase=Phase.VALIDATION,
            timeout_seconds=10,
        )

        rendered = prompt._render()
        assert isinstance(rendered, Panel)
