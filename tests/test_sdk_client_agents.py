"""Tests for RalphSDKClient integration with subagents.

This module tests the specific integration between RalphSDKClient and the subagents
module, ensuring that _build_options() correctly includes agents parameter, Task tool
is added to allowed_tools, phase-specific filtering works, and subagents are passed
to ClaudeAgentOptions.
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from claude_agent_sdk import AgentDefinition

from ralph.config import CostLimits, RalphConfig
from ralph.models import Phase, RalphState
from ralph.sdk_client import RalphSDKClient


# Helper function to create a mock RalphState
def create_mock_state(
    phase: Phase = Phase.BUILDING,
    project_root: Path | None = None,
) -> RalphState:
    """Create a mock RalphState for testing."""
    state = RalphState(project_root=project_root or Path("/tmp/test"))
    state.current_phase = phase
    return state


def create_mock_config() -> RalphConfig:
    """Create a mock RalphConfig for testing."""
    config = RalphConfig()
    config.primary_model = "claude-sonnet-4-20250514"
    config.planning_model = "claude-opus-4-20250514"
    config.cost_limits = CostLimits(per_iteration=2.0, per_session=50.0, total=200.0)
    return config


class TestRalphSDKClientSubagentIntegration:
    """Comprehensive tests for RalphSDKClient subagent integration."""

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @patch("ralph.sdk_client.get_subagents_for_phase")
    def test_build_options_calls_get_subagents_for_phase_with_correct_parameters(
        self, mock_get_subagents: MagicMock, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """_build_options calls get_subagents_for_phase with current phase and config."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None
        mock_get_subagents.return_value = {}

        state = create_mock_state(phase=Phase.BUILDING)
        config = create_mock_config()
        client = RalphSDKClient(state=state, config=config)
        client.mcp_servers = {}

        client._build_options()

        # Should call get_subagents_for_phase with current phase and config
        mock_get_subagents.assert_called_once_with(Phase.BUILDING, config)

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @patch("ralph.sdk_client.get_subagents_for_phase")
    def test_build_options_calls_get_subagents_for_phase_with_phase_override(
        self, mock_get_subagents: MagicMock, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """_build_options uses phase override when calling get_subagents_for_phase."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None
        mock_get_subagents.return_value = {}

        state = create_mock_state(phase=Phase.BUILDING)
        config = create_mock_config()
        client = RalphSDKClient(state=state, config=config)
        client.mcp_servers = {}

        # Override phase to VALIDATION
        client._build_options(phase=Phase.VALIDATION)

        # Should call get_subagents_for_phase with overridden phase
        mock_get_subagents.assert_called_once_with(Phase.VALIDATION, config)

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @patch("ralph.sdk_client.get_subagents_for_phase")
    def test_build_options_calls_get_subagents_for_phase_without_config(
        self, mock_get_subagents: MagicMock, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """_build_options passes None for config when no config is provided."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None
        mock_get_subagents.return_value = {}

        state = create_mock_state(phase=Phase.DISCOVERY)
        client = RalphSDKClient(state=state, config=None)
        client.mcp_servers = {}

        client._build_options()

        # Should call get_subagents_for_phase with None config
        mock_get_subagents.assert_called_once_with(Phase.DISCOVERY, None)

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @patch("ralph.sdk_client.get_subagents_for_phase")
    def test_build_options_includes_task_tool_in_allowed_tools(
        self, mock_get_subagents: MagicMock, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """_build_options ensures Task tool is included in allowed_tools list."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None
        mock_get_subagents.return_value = {}

        state = create_mock_state(phase=Phase.BUILDING)
        client = RalphSDKClient(state=state)
        client.mcp_servers = {}

        options = client._build_options()

        # Task tool should be in allowed_tools for subagent invocation
        assert "Task" in options.allowed_tools

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @patch("ralph.sdk_client.get_subagents_for_phase")
    def test_build_options_task_tool_added_even_if_not_in_phase_tools(
        self, mock_get_subagents: MagicMock, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """_build_options adds Task tool even if it's not in phase-specific tools."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None
        mock_get_subagents.return_value = {}

        # Test with a phase that doesn't naturally include Task tool
        state = create_mock_state(phase=Phase.VALIDATION)
        client = RalphSDKClient(state=state)
        client.mcp_servers = {}

        # Mock get_tools_for_phase to return tools without Task
        with patch("ralph.sdk_client.get_tools_for_phase") as mock_get_tools:
            mock_get_tools.return_value = ["Read", "Write", "Edit"]  # No Task

            options = client._build_options()

        # Task tool should still be added for subagent support
        assert "Task" in options.allowed_tools
        # Other phase tools should also be included
        assert "Read" in options.allowed_tools
        assert "Write" in options.allowed_tools
        assert "Edit" in options.allowed_tools

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @patch("ralph.sdk_client.get_subagents_for_phase")
    def test_build_options_passes_subagents_as_agents_parameter(
        self, mock_get_subagents: MagicMock, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """_build_options passes subagents as agents parameter to ClaudeAgentOptions."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        # Create mock subagents with proper AgentDefinition objects
        mock_subagents = {
            "code-reviewer": AgentDefinition(
                description="Test code reviewer agent",
                prompt="You are a code reviewer",
                tools=["Read", "Grep"],
                model="sonnet"
            ),
            "research-specialist": AgentDefinition(
                description="Test research specialist agent",
                prompt="You are a research specialist",
                tools=["Read", "WebSearch"],
                model="sonnet"
            )
        }
        mock_get_subagents.return_value = mock_subagents

        state = create_mock_state(phase=Phase.BUILDING)
        client = RalphSDKClient(state=state)
        client.mcp_servers = {}

        options = client._build_options()

        # Should pass the subagents dictionary as agents parameter
        assert hasattr(options, "agents")
        assert options.agents == mock_subagents

        # Verify the specific agents are present
        assert "code-reviewer" in options.agents
        assert "research-specialist" in options.agents

        # Verify they are proper AgentDefinition objects
        assert isinstance(options.agents["code-reviewer"], AgentDefinition)
        assert isinstance(options.agents["research-specialist"], AgentDefinition)

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @patch("ralph.sdk_client.get_subagents_for_phase")
    def test_build_options_handles_empty_subagents_dict(
        self, mock_get_subagents: MagicMock, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """_build_options handles empty subagents dict correctly."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None
        mock_get_subagents.return_value = {}

        state = create_mock_state(phase=Phase.VALIDATION)
        client = RalphSDKClient(state=state)
        client.mcp_servers = {}

        options = client._build_options()

        # Should pass empty dict as agents parameter
        assert hasattr(options, "agents")
        assert options.agents == {}

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @patch("ralph.sdk_client.get_subagents_for_phase")
    def test_build_options_phase_specific_subagent_filtering(
        self, mock_get_subagents: MagicMock, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """_build_options gets phase-specific subagents based on current phase."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        # Mock different subagents for different phases
        building_subagents = {
            "code-reviewer": AgentDefinition(
                description="Code reviewer",
                prompt="Review code",
                tools=["Read", "Grep"],
                model="sonnet"
            ),
            "test-engineer": AgentDefinition(
                description="Test engineer",
                prompt="Write tests",
                tools=["Read", "Grep"],
                model="sonnet"
            )
        }

        planning_subagents = {
            "research-specialist": AgentDefinition(
                description="Research specialist",
                prompt="Research solutions",
                tools=["Read", "WebSearch"],
                model="sonnet"
            )
        }

        state = create_mock_state(phase=Phase.BUILDING)
        client = RalphSDKClient(state=state)
        client.mcp_servers = {}

        # Test building phase
        mock_get_subagents.return_value = building_subagents
        options = client._build_options()

        assert options.agents == building_subagents
        assert "code-reviewer" in options.agents
        assert "test-engineer" in options.agents

        # Test planning phase with phase override
        mock_get_subagents.return_value = planning_subagents
        options = client._build_options(phase=Phase.PLANNING)

        # Should have called with PLANNING phase and gotten different subagents
        assert "research-specialist" in options.agents

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @patch("ralph.sdk_client.get_subagents_for_phase")
    def test_build_options_subagents_integration_with_other_options(
        self, mock_get_subagents: MagicMock, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """_build_options correctly integrates subagents with other ClaudeAgentOptions."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        mock_subagents = {
            "documentation-agent": AgentDefinition(
                description="Documentation agent",
                prompt="Generate docs",
                tools=["Read", "Glob"],
                model="haiku"
            )
        }
        mock_get_subagents.return_value = mock_subagents

        state = create_mock_state(phase=Phase.DISCOVERY)
        config = create_mock_config()
        client = RalphSDKClient(state=state, config=config)
        client.mcp_servers = {}

        options = client._build_options(
            phase=Phase.DISCOVERY,
            system_prompt="Test system prompt",
            max_turns=25
        )

        # Verify subagents are included
        assert options.agents == mock_subagents

        # Verify other options are still set correctly
        assert options.system_prompt == "Test system prompt"
        assert options.max_turns == 25
        assert options.cwd == str(state.project_root)
        assert options.max_budget_usd == config.cost_limits.per_iteration
        assert "Task" in options.allowed_tools

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @patch("ralph.sdk_client.get_subagents_for_phase")
    def test_build_options_handles_get_subagents_exception(
        self, mock_get_subagents: MagicMock, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """_build_options handles exceptions from get_subagents_for_phase gracefully."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        # Mock get_subagents_for_phase to raise an exception
        mock_get_subagents.side_effect = Exception("Subagents loading failed")

        state = create_mock_state(phase=Phase.BUILDING)
        client = RalphSDKClient(state=state)
        client.mcp_servers = {}

        # Should not raise an exception, should handle gracefully
        with pytest.raises(Exception, match="Subagents loading failed"):
            client._build_options()

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_build_options_subagents_not_called_when_mocked_out(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """Test behavior when subagents module is mocked to avoid dependencies."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        # Mock the entire subagents module to return empty dict
        with patch("ralph.sdk_client.get_subagents_for_phase") as mock_get_subagents:
            mock_get_subagents.return_value = {}

            state = create_mock_state(phase=Phase.BUILDING)
            client = RalphSDKClient(state=state)
            client.mcp_servers = {}

            options = client._build_options()

            # Should still work with empty subagents
            assert options.agents == {}
            assert "Task" in options.allowed_tools
            mock_get_subagents.assert_called_once()

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @patch("ralph.sdk_client.get_subagents_for_phase")
    def test_build_options_with_all_phases_gets_different_subagents(
        self, mock_get_subagents: MagicMock, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """_build_options gets different subagents for each phase."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        state = create_mock_state()
        client = RalphSDKClient(state=state)
        client.mcp_servers = {}

        # Test each phase gets subagents call
        phases_to_test = [Phase.DISCOVERY, Phase.PLANNING, Phase.BUILDING, Phase.VALIDATION]

        for phase in phases_to_test:
            mock_get_subagents.reset_mock()
            mock_get_subagents.return_value = {f"agent-for-{phase.value}": Mock()}

            options = client._build_options(phase=phase)

            # Verify get_subagents_for_phase was called with the correct phase
            mock_get_subagents.assert_called_once_with(phase, None)

            # Verify agents parameter is set
            assert hasattr(options, "agents")
            assert f"agent-for-{phase.value}" in options.agents
