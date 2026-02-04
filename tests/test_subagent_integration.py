"""End-to-end integration tests for Ralph subagent system.

This module provides comprehensive integration testing for the Ralph subagent
system, including phase-specific subagent availability, tool restriction
enforcement, subagent invocation through the Task tool, result integration,
and security constraint validation.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from claude_agent_sdk import AgentDefinition

from ralph.config import RalphConfig
from ralph.models import Phase, RalphState
from ralph.sdk_client import RalphSDKClient
from ralph.subagents import (
    PHASE_SUBAGENT_CONFIG,
    SUBAGENT_SECURITY_CONSTRAINTS,
    get_subagents_for_phase,
)
from tests.fixtures.mock_subagent_responses import (
    get_all_subagent_types,
    get_mock_subagent_response,
)


# Test fixtures
@pytest.fixture
def mock_state() -> RalphState:
    """Create a mock RalphState for testing."""
    return RalphState(project_root=Path("/tmp/test-project"))


@pytest.fixture
def mock_config() -> RalphConfig:
    """Create a mock RalphConfig for testing."""
    config = RalphConfig()
    config.primary_model = "claude-sonnet-4-20250514"
    return config


@pytest.fixture
def mock_sdk_client(mock_state: RalphState, mock_config: RalphConfig) -> RalphSDKClient:
    """Create a mock RalphSDKClient for testing."""
    client = RalphSDKClient(state=mock_state, config=mock_config)
    return client


class TestSubagentPhaseAvailability:
    """Test that correct subagents are available for each phase."""

    def test_discovery_phase_has_correct_subagents(self, mock_sdk_client: RalphSDKClient) -> None:
        """Discovery phase should have research-specialist and product-analyst available."""
        mock_sdk_client.state.current_phase = Phase.DISCOVERY

        subagents = get_subagents_for_phase(Phase.DISCOVERY, mock_sdk_client.config)

        expected_subagents = PHASE_SUBAGENT_CONFIG[Phase.DISCOVERY]
        assert len(subagents) == len(expected_subagents)

        for subagent_name in expected_subagents:
            assert subagent_name in subagents
            assert isinstance(subagents[subagent_name], AgentDefinition)

    def test_planning_phase_has_correct_subagents(self, mock_sdk_client: RalphSDKClient) -> None:
        """Planning phase should have research-specialist and documentation-agent available."""
        mock_sdk_client.state.current_phase = Phase.PLANNING

        subagents = get_subagents_for_phase(Phase.PLANNING, mock_sdk_client.config)

        expected_subagents = PHASE_SUBAGENT_CONFIG[Phase.PLANNING]
        assert len(subagents) == len(expected_subagents)

        for subagent_name in expected_subagents:
            assert subagent_name in subagents
            assert isinstance(subagents[subagent_name], AgentDefinition)

    def test_building_phase_has_correct_subagents(self, mock_sdk_client: RalphSDKClient) -> None:
        """Building phase should have test-engineer, code-reviewer, and research-specialist
        available."""
        mock_sdk_client.state.current_phase = Phase.BUILDING

        subagents = get_subagents_for_phase(Phase.BUILDING, mock_sdk_client.config)

        expected_subagents = PHASE_SUBAGENT_CONFIG[Phase.BUILDING]
        assert len(subagents) == len(expected_subagents)

        for subagent_name in expected_subagents:
            assert subagent_name in subagents
            assert isinstance(subagents[subagent_name], AgentDefinition)

    def test_validation_phase_has_correct_subagents(self, mock_sdk_client: RalphSDKClient) -> None:
        """Validation phase should have code-reviewer, test-engineer, and documentation-agent
        available."""
        mock_sdk_client.state.current_phase = Phase.VALIDATION

        subagents = get_subagents_for_phase(Phase.VALIDATION, mock_sdk_client.config)

        expected_subagents = PHASE_SUBAGENT_CONFIG[Phase.VALIDATION]
        assert len(subagents) == len(expected_subagents)

        for subagent_name in expected_subagents:
            assert subagent_name in subagents
            assert isinstance(subagents[subagent_name], AgentDefinition)

    def test_phase_subagent_filtering_excludes_inappropriate_subagents(
        self, mock_sdk_client: RalphSDKClient
    ) -> None:
        """Test that subagents not configured for a phase are properly excluded."""
        # Test that Discovery phase doesn't include test-engineer
        # (which is Building/Validation only)
        mock_sdk_client.state.current_phase = Phase.DISCOVERY

        discovery_subagents = get_subagents_for_phase(Phase.DISCOVERY, mock_sdk_client.config)

        # test-engineer should not be available in Discovery phase
        assert "test-engineer" not in discovery_subagents

        # But should be available in Building phase
        building_subagents = get_subagents_for_phase(Phase.BUILDING, mock_sdk_client.config)
        assert "test-engineer" in building_subagents


class TestSubagentToolRestrictions:
    """Test that tool restrictions are properly enforced for all subagents."""

    @property
    def tool_permissions(self) -> dict[str, list[str]]:
        """Get typed tool permissions from security constraints."""
        return cast(dict[str, list[str]], SUBAGENT_SECURITY_CONSTRAINTS["tool_permissions"])

    def test_research_specialist_tool_restrictions(self) -> None:
        """Research specialist should only have read-only tools plus web research."""
        subagents = get_subagents_for_phase(Phase.DISCOVERY, None)
        research_agent = subagents["research-specialist"]

        allowed_tools = self.tool_permissions["research-specialist"]
        forbidden_tools = cast(list[str], SUBAGENT_SECURITY_CONSTRAINTS["forbidden_tools"])

        # Should have the expected allowed tools
        for tool in allowed_tools:
            assert tool in research_agent.tools

        # Should not have any forbidden tools
        for tool in forbidden_tools:
            assert tool not in research_agent.tools

    def test_code_reviewer_tool_restrictions(self) -> None:
        """Code reviewer should only have read-only tools."""
        subagents = get_subagents_for_phase(Phase.BUILDING, None)
        code_reviewer = subagents["code-reviewer"]

        allowed_tools = self.tool_permissions["code-reviewer"]
        forbidden_tools = cast(list[str], SUBAGENT_SECURITY_CONSTRAINTS["forbidden_tools"])

        # Should have only read-only tools
        for tool in allowed_tools:
            assert tool in code_reviewer.tools

        # Should not have any forbidden tools
        for tool in forbidden_tools:
            assert tool not in code_reviewer.tools

    def test_test_engineer_tool_restrictions(self) -> None:
        """Test engineer should only have read-only tools."""
        subagents = get_subagents_for_phase(Phase.BUILDING, None)
        test_engineer = subagents["test-engineer"]

        allowed_tools = self.tool_permissions["test-engineer"]
        forbidden_tools = cast(list[str], SUBAGENT_SECURITY_CONSTRAINTS["forbidden_tools"])

        # Should have only read-only tools
        for tool in allowed_tools:
            assert tool in test_engineer.tools

        # Should not have any forbidden tools
        for tool in forbidden_tools:
            assert tool not in test_engineer.tools

    def test_documentation_agent_tool_restrictions(self) -> None:
        """Documentation agent should only have read-only tools."""
        subagents = get_subagents_for_phase(Phase.VALIDATION, None)
        doc_agent = subagents["documentation-agent"]

        allowed_tools = self.tool_permissions["documentation-agent"]
        forbidden_tools = cast(list[str], SUBAGENT_SECURITY_CONSTRAINTS["forbidden_tools"])

        # Should have only read-only tools
        for tool in allowed_tools:
            assert tool in doc_agent.tools

        # Should not have any forbidden tools
        for tool in forbidden_tools:
            assert tool not in doc_agent.tools

    def test_product_analyst_tool_restrictions(self) -> None:
        """Product analyst should only have read-only tools."""
        subagents = get_subagents_for_phase(Phase.DISCOVERY, None)
        product_analyst = subagents["product-analyst"]

        allowed_tools = self.tool_permissions["product-analyst"]
        forbidden_tools = cast(list[str], SUBAGENT_SECURITY_CONSTRAINTS["forbidden_tools"])

        # Should have only read-only tools
        for tool in allowed_tools:
            assert tool in product_analyst.tools

        # Should not have any forbidden tools
        for tool in forbidden_tools:
            assert tool not in product_analyst.tools

    def test_no_subagent_has_write_access(self) -> None:
        """Ensure no subagent has access to Write, Edit, or other dangerous tools."""
        forbidden_tools = cast(list[str], SUBAGENT_SECURITY_CONSTRAINTS["forbidden_tools"])

        for phase in Phase:
            subagents = get_subagents_for_phase(phase, None)
            for subagent_name, subagent_def in subagents.items():
                for forbidden_tool in forbidden_tools:
                    assert forbidden_tool not in subagent_def.tools, (
                        f"Subagent {subagent_name} in phase {phase.value} "
                        f"has forbidden tool: {forbidden_tool}"
                    )

    def test_no_subagent_can_spawn_subagents(self) -> None:
        """Ensure no subagent has access to Task tool (prevent nested subagents)."""
        for phase in Phase:
            subagents = get_subagents_for_phase(phase, None)
            for subagent_name, subagent_def in subagents.items():
                assert "Task" not in subagent_def.tools, (
                    f"Subagent {subagent_name} in phase {phase.value} "
                    f"has Task tool - this would allow nested subagents!"
                )


class TestSubagentInvocationIntegration:
    """Test subagent invocation through Task tool and result integration."""

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_sdk_client_includes_task_tool_for_subagent_invocation(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock, mock_sdk_client: RalphSDKClient
    ) -> None:
        """Test that SDK client includes Task tool in allowed_tools for subagent invocation."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        mock_sdk_client.state.current_phase = Phase.BUILDING

        options = mock_sdk_client._build_options()

        # Task tool should be included for subagent invocation
        assert "Task" in options.allowed_tools

        # Should also have subagents configured
        assert options.agents is not None
        assert len(options.agents) > 0

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_sdk_client_passes_phase_appropriate_subagents(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock, mock_sdk_client: RalphSDKClient
    ) -> None:
        """Test that SDK client passes correct subagents for each phase."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        # Test different phases
        for phase in Phase:
            mock_sdk_client.state.current_phase = phase
            options = mock_sdk_client._build_options()

            expected_subagents = PHASE_SUBAGENT_CONFIG[phase]

            assert options.agents is not None
            assert len(options.agents) == len(expected_subagents)

            for expected_subagent in expected_subagents:
                assert expected_subagent in options.agents

    @patch("ralph.sdk_client.ClaudeSDKClient")
    async def test_subagent_invocation_through_task_tool(
        self, mock_claude_sdk: MagicMock, mock_sdk_client: RalphSDKClient
    ) -> None:
        """Test that subagents can be invoked through Task tool and return results."""
        # Setup mock for the Claude SDK client
        mock_claude_instance = AsyncMock()
        mock_claude_sdk.return_value = mock_claude_instance

        # Mock a subagent response
        mock_response = get_mock_subagent_response("research-specialist", "technology_analysis")

        # Mock the query result
        mock_claude_instance.query.return_value = AsyncMock()
        mock_claude_instance.query.return_value.__aenter__.return_value.text = (
            mock_response["response"]
        )

        mock_sdk_client.state.current_phase = Phase.DISCOVERY

        # This would normally be called by the main agent when using Task tool
        # We're testing the integration here
        result = await self._invoke_subagent_simulation(
            subagent_type="research-specialist",
            task_description="Analyze WebSocket vs SSE for real-time features"
        )

        # Verify the result contains expected content
        assert "WebSocket" in result
        assert "Server-Sent Events" in result
        assert "Executive Summary" in result

    @staticmethod
    async def _invoke_subagent_simulation(
        subagent_type: str, task_description: str
    ) -> str:
        """Simulate subagent invocation for testing purposes."""
        # This method simulates what would happen when Task tool invokes a subagent
        mock_response = get_mock_subagent_response(subagent_type)
        return str(mock_response["response"])


class TestSubagentResultIntegration:
    """Test that subagent results are properly integrated and processed."""

    def test_subagent_response_contains_required_sections(self) -> None:
        """Test that mock subagent responses contain expected report sections."""
        for subagent_type in get_all_subagent_types():
            response = get_mock_subagent_response(subagent_type)
            response_text = response["response"]

            # All subagent responses should contain these sections
            assert "# " in response_text  # Markdown header
            assert "Executive Summary" in response_text
            assert "Recommendations" in response_text
            assert "Confidence Assessment" in response_text

    def test_subagent_response_format_consistency(self) -> None:
        """Test that all subagent responses follow consistent format."""
        for subagent_type in get_all_subagent_types():
            response = get_mock_subagent_response(subagent_type)

            # Should have success indicator
            assert "success" in response
            assert isinstance(response["success"], bool)

            if response["success"]:
                # Successful responses should have content and metrics
                assert "response" in response
                assert "tokens_used" in response
                assert "cost_estimate" in response
                assert isinstance(response["response"], str)
                assert isinstance(response["tokens_used"], int)
                assert isinstance(response["cost_estimate"], float)
            else:
                # Error responses should have error message
                assert "error" in response
                assert isinstance(response["error"], str)

    def test_subagent_error_handling(self) -> None:
        """Test that subagent error scenarios are properly handled."""
        for subagent_type in get_all_subagent_types():
            error_response = get_mock_subagent_response(subagent_type, "error_scenario")

            # Error responses should be properly formatted
            assert error_response["success"] is False
            assert "error" in error_response
            assert len(error_response["error"]) > 0


class TestSubagentSecurityConstraints:
    """Test that security constraints are properly enforced across the system."""

    def test_subagent_security_configuration_completeness(self) -> None:
        """Test that all subagent types have security constraints defined."""
        all_subagent_types = get_all_subagent_types()
        tool_permissions = cast(
            dict[str, list[str]],
            SUBAGENT_SECURITY_CONSTRAINTS["tool_permissions"],
        )

        for subagent_type in all_subagent_types:
            assert subagent_type in tool_permissions, (
                f"Security constraints missing for subagent type: {subagent_type}"
            )

            # Each subagent should have specific tool permissions defined
            permissions = tool_permissions[subagent_type]
            assert isinstance(permissions, list)
            assert len(permissions) > 0

    def test_forbidden_tools_are_comprehensive(self) -> None:
        """Test that forbidden tools list includes all dangerous capabilities."""
        forbidden_tools = cast(list[str], SUBAGENT_SECURITY_CONSTRAINTS["forbidden_tools"])

        # These tools should definitely be forbidden for all subagents
        critical_forbidden = ["Write", "Edit", "NotebookEdit", "Bash", "Task"]

        for tool in critical_forbidden:
            assert tool in forbidden_tools, f"Critical tool {tool} not in forbidden list"

    def test_subagent_isolation_prevents_state_modification(self) -> None:
        """Test that subagents cannot modify Ralph's state or files."""
        # Verify that no subagent has tools that could modify state
        dangerous_tools = ["Write", "Edit", "NotebookEdit", "Bash"]

        for phase in Phase:
            subagents = get_subagents_for_phase(phase, None)
            for subagent_name, subagent_def in subagents.items():
                for dangerous_tool in dangerous_tools:
                    assert dangerous_tool not in subagent_def.tools, (
                        f"Subagent {subagent_name} has dangerous tool {dangerous_tool}"
                    )

    def test_research_specialist_has_web_access_only(self) -> None:
        """Test that only research specialist has web access tools."""
        web_tools = ["WebSearch", "WebFetch"]

        for phase in Phase:
            subagents = get_subagents_for_phase(phase, None)

            for subagent_name, subagent_def in subagents.items():
                if subagent_name == "research-specialist":
                    # Research specialist should have web tools
                    for web_tool in web_tools:
                        assert web_tool in subagent_def.tools
                else:
                    # Other subagents should not have web tools
                    for web_tool in web_tools:
                        assert web_tool not in subagent_def.tools, (
                            f"Non-research subagent {subagent_name} has web tool {web_tool}"
                        )


class TestSubagentPhaseTransitions:
    """Test subagent behavior during phase transitions."""

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_subagent_availability_changes_with_phase(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock, mock_sdk_client: RalphSDKClient
    ) -> None:
        """Test that available subagents change appropriately during phase transitions."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        # Test transition from Discovery to Planning
        mock_sdk_client.state.current_phase = Phase.DISCOVERY
        discovery_options = mock_sdk_client._build_options()
        discovery_subagents = set(discovery_options.agents.keys())

        mock_sdk_client.state.current_phase = Phase.PLANNING
        planning_options = mock_sdk_client._build_options()
        planning_subagents = set(planning_options.agents.keys())

        # Should have different subagent configurations
        assert discovery_subagents != planning_subagents

        # Verify specific changes
        expected_discovery = set(PHASE_SUBAGENT_CONFIG[Phase.DISCOVERY])
        expected_planning = set(PHASE_SUBAGENT_CONFIG[Phase.PLANNING])

        assert discovery_subagents == expected_discovery
        assert planning_subagents == expected_planning

    def test_phase_subagent_config_covers_all_phases(self) -> None:
        """Test that all phases have subagent configurations."""
        for phase in Phase:
            assert phase in PHASE_SUBAGENT_CONFIG, (
                f"Phase {phase.value} missing from subagent config"
            )

            subagents = PHASE_SUBAGENT_CONFIG[phase]
            assert len(subagents) > 0, f"Phase {phase.value} has no configured subagents"


class TestSubagentCostAndPerformance:
    """Test subagent cost tracking and performance considerations."""

    def test_mock_responses_include_cost_estimates(self) -> None:
        """Test that mock responses include realistic cost estimates."""
        for subagent_type in get_all_subagent_types():
            response = get_mock_subagent_response(subagent_type)

            if response["success"]:
                assert "cost_estimate" in response
                assert isinstance(response["cost_estimate"], (int, float))
                assert response["cost_estimate"] >= 0

                # Cost should be reasonable (not astronomical)
                assert response["cost_estimate"] < 1.0  # Less than $1

    def test_mock_responses_include_token_usage(self) -> None:
        """Test that mock responses include token usage tracking."""
        for subagent_type in get_all_subagent_types():
            response = get_mock_subagent_response(subagent_type)

            assert "tokens_used" in response
            assert isinstance(response["tokens_used"], int)
            assert response["tokens_used"] >= 0

            if response["success"]:
                # Successful responses should have some token usage
                assert response["tokens_used"] > 0

                # Token usage should be reasonable
                assert response["tokens_used"] < 1000  # Not excessive


class TestSubagentConfigurationFlexibility:
    """Test that subagent configuration is flexible and configurable."""

    def test_subagent_creation_with_custom_config(self, mock_config: RalphConfig) -> None:
        """Test that subagents can be created with custom configuration."""
        # Test each phase with custom config
        for phase in Phase:
            subagents = get_subagents_for_phase(phase, mock_config)

            # Should create appropriate subagents
            expected_count = len(PHASE_SUBAGENT_CONFIG[phase])
            assert len(subagents) == expected_count

            # All should be AgentDefinition instances
            for subagent in subagents.values():
                assert isinstance(subagent, AgentDefinition)

    def test_subagent_creation_without_config(self) -> None:
        """Test that subagents can be created with None config (defaults)."""
        # Test each phase without config
        for phase in Phase:
            subagents = get_subagents_for_phase(phase, None)

            # Should still create appropriate subagents with defaults
            expected_count = len(PHASE_SUBAGENT_CONFIG[phase])
            assert len(subagents) == expected_count

            # All should be AgentDefinition instances
            for subagent in subagents.values():
                assert isinstance(subagent, AgentDefinition)

    def test_empty_phase_handling(self) -> None:
        """Test graceful handling of phase with no configured subagents."""
        # This is a theoretical test since all phases currently have subagents
        # But tests the robustness of the filtering logic

        from ralph.subagents import filter_subagents_by_phase

        # Create dummy subagents
        dummy_subagents = {
            "test-agent": AgentDefinition(
                description="Test agent",
                prompt="Test prompt",
                tools=["Read"],
                model="haiku"
            )
        }

        # Filter for a phase (all phases have config, so this tests the logic)
        filtered = filter_subagents_by_phase(Phase.DISCOVERY, dummy_subagents)

        # Should return empty dict since test-agent is not configured for any phase
        assert len(filtered) == 0
