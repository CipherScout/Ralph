"""Integration tests for tool access parity across all phases (SPEC-002).

This module verifies that all Claude Agent SDK tools are available in all
Ralph phases, eliminating artificial restrictions like TodoWrite being
unavailable in validation.
"""

from __future__ import annotations

import pytest

from ralph.models import Phase
from ralph.sdk_client import ALL_SDK_TOOLS, PHASE_TOOLS, get_tools_for_phase


class TestToolAccessParity:
    """Tests to verify SPEC-002 tool access parity requirements."""

    def test_interactive_phases_have_identical_tools(self) -> None:
        """Discovery, Planning, Validation have identical tools (all including AskUserQuestion)."""
        discovery_tools = set(get_tools_for_phase(Phase.DISCOVERY))
        planning_tools = set(get_tools_for_phase(Phase.PLANNING))
        validation_tools = set(get_tools_for_phase(Phase.VALIDATION))

        assert discovery_tools == planning_tools == validation_tools

    def test_building_phase_excludes_askuserquestion(self) -> None:
        """Building phase has all tools except AskUserQuestion."""
        building_tools = set(get_tools_for_phase(Phase.BUILDING))
        discovery_tools = set(get_tools_for_phase(Phase.DISCOVERY))

        # Building should have all tools except AskUserQuestion
        assert building_tools == discovery_tools - {"AskUserQuestion"}

    def test_todowrite_available_in_validation(self) -> None:
        """SPEC-002 requirement: TodoWrite must work in validation phase."""
        tools = get_tools_for_phase(Phase.VALIDATION)
        assert "TodoWrite" in tools, "TodoWrite must be available in validation"

    def test_askuserquestion_available_in_interactive_phases(self) -> None:
        """AskUserQuestion available in Discovery, Planning, Validation - not Building."""
        # AskUserQuestion allowed in interactive phases
        for phase in [Phase.DISCOVERY, Phase.PLANNING, Phase.VALIDATION]:
            tools = get_tools_for_phase(phase)
            assert "AskUserQuestion" in tools, f"AskUserQuestion missing from {phase}"

        # AskUserQuestion NOT allowed in Building - agent should focus on implementation
        building_tools = get_tools_for_phase(Phase.BUILDING)
        assert "AskUserQuestion" not in building_tools, "AskUserQuestion should not be in Building"

    def test_all_sdk_tools_in_all_phases_except_askuserquestion(self) -> None:
        """All SDK tools except AskUserQuestion available in all phases."""
        tools_in_all_phases = [t for t in ALL_SDK_TOOLS if t != "AskUserQuestion"]
        for phase in Phase:
            phase_tools = set(get_tools_for_phase(phase))
            missing = set(tools_in_all_phases) - phase_tools
            assert not missing, f"Phase {phase.value} missing tools: {missing}"

    def test_phase_tools_dict_consistency(self) -> None:
        """PHASE_TOOLS dict must be consistent with get_tools_for_phase."""
        for phase in Phase:
            dict_tools = set(PHASE_TOOLS[phase])
            func_tools = set(get_tools_for_phase(phase))
            assert dict_tools == func_tools, f"Inconsistency in {phase.value}"

    @pytest.mark.parametrize("tool", [
        "Read", "Write", "Edit", "Bash", "BashOutput", "KillBash",
        "Glob", "Grep", "Task", "TodoWrite", "WebSearch", "WebFetch",
        "NotebookEdit", "ExitPlanMode",  # AskUserQuestion excluded - not in Building
    ])
    def test_tool_in_all_phases(self, tool: str) -> None:
        """Each universal tool must be available in all phases."""
        for phase in Phase:
            tools = get_tools_for_phase(phase)
            assert tool in tools, f"{tool} not in {phase.value} phase"


class TestToolListCompleteness:
    """Tests to verify ALL_SDK_TOOLS contains expected tools."""

    def test_file_operation_tools(self) -> None:
        """File operation tools are present."""
        assert "Read" in ALL_SDK_TOOLS
        assert "Write" in ALL_SDK_TOOLS
        assert "Edit" in ALL_SDK_TOOLS
        assert "NotebookEdit" in ALL_SDK_TOOLS

    def test_command_execution_tools(self) -> None:
        """Command execution tools are present."""
        assert "Bash" in ALL_SDK_TOOLS
        assert "BashOutput" in ALL_SDK_TOOLS
        assert "KillBash" in ALL_SDK_TOOLS

    def test_search_tools(self) -> None:
        """File discovery and search tools are present."""
        assert "Glob" in ALL_SDK_TOOLS
        assert "Grep" in ALL_SDK_TOOLS

    def test_web_tools(self) -> None:
        """Web capability tools are present."""
        assert "WebSearch" in ALL_SDK_TOOLS
        assert "WebFetch" in ALL_SDK_TOOLS

    def test_interaction_tools(self) -> None:
        """User interaction tools are present."""
        assert "AskUserQuestion" in ALL_SDK_TOOLS
        assert "ExitPlanMode" in ALL_SDK_TOOLS

    def test_utility_tools(self) -> None:
        """Utility tools are present."""
        assert "Task" in ALL_SDK_TOOLS
        assert "TodoWrite" in ALL_SDK_TOOLS

    def test_mcp_resource_tools(self) -> None:
        """MCP resource tools are present."""
        assert "ListMcpResourcesTool" in ALL_SDK_TOOLS
        assert "ReadMcpResourceTool" in ALL_SDK_TOOLS


class TestBackwardsCompatibility:
    """Tests to ensure backwards compatibility with existing code."""

    def test_phase_tools_dict_exists(self) -> None:
        """PHASE_TOOLS dict is still available."""
        assert isinstance(PHASE_TOOLS, dict)
        assert len(PHASE_TOOLS) == 4

    def test_get_tools_for_phase_returns_list(self) -> None:
        """get_tools_for_phase returns a list."""
        for phase in Phase:
            tools = get_tools_for_phase(phase)
            assert isinstance(tools, list)
            assert len(tools) > 0

    def test_phase_tools_are_independent_copies(self) -> None:
        """Each phase gets an independent copy of tools list."""
        discovery_tools = get_tools_for_phase(Phase.DISCOVERY)
        planning_tools = get_tools_for_phase(Phase.PLANNING)

        # Modifying one shouldn't affect the other
        discovery_tools.append("TestTool")
        assert "TestTool" not in get_tools_for_phase(Phase.PLANNING)
        assert "TestTool" not in planning_tools
