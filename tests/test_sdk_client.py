"""Tests for Claude SDK client wrapper."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from claude_agent_sdk import HookMatcher

from ralph.config import CostLimits, RalphConfig
from ralph.models import ContextBudget, Phase, RalphState
from ralph.sdk_client import (
    MODEL_PRICING,
    PHASE_TOOLS,
    IterationMetrics,
    IterationResult,
    RalphSDKClient,
    calculate_cost,
    calculate_max_turns,
    create_ralph_client,
    get_model_for_phase,
    get_tools_for_phase,
)


# Helper function to create a mock RalphState
def create_mock_state(
    phase: Phase = Phase.BUILDING,
    session_cost: float = 0.0,
    context_usage: int = 0,
    context_capacity: int = 200_000,
    project_root: Path | None = None,
) -> RalphState:
    """Create a mock RalphState for testing."""
    state = RalphState(project_root=project_root or Path("/tmp/test"))
    state.current_phase = phase
    state.session_cost_usd = session_cost
    state.context_budget = ContextBudget(
        total_capacity=context_capacity,
        current_usage=context_usage,
    )
    return state


def create_mock_config() -> RalphConfig:
    """Create a mock RalphConfig for testing."""
    config = RalphConfig()
    config.primary_model = "claude-sonnet-4-20250514"
    config.planning_model = "claude-opus-4-20250514"
    config.cost_limits = CostLimits(per_iteration=2.0, per_session=50.0, total=200.0)
    return config


def create_mock_hook_matcher() -> HookMatcher:
    """Create a properly typed mock HookMatcher for testing."""
    from typing import Any

    from claude_agent_sdk.types import (
        AsyncHookJSONOutput,
        HookContext,
        SyncHookJSONOutput,
    )

    async def mock_hook(
        input_data: Any,
        tool_use_id: str | None,
        context: HookContext,
    ) -> AsyncHookJSONOutput | SyncHookJSONOutput:
        return {}

    return HookMatcher(hooks=[mock_hook])


def create_mock_hooks() -> dict[str, list[HookMatcher]]:
    """Create a properly typed mock hooks dict for testing."""
    return {"PreToolUse": [create_mock_hook_matcher()]}


class TestIterationMetrics:
    """Tests for IterationMetrics dataclass."""

    def test_default_values(self) -> None:
        """Default values are initialized correctly."""
        metrics = IterationMetrics()
        assert metrics.input_tokens == 0
        assert metrics.output_tokens == 0
        assert metrics.tool_calls == 0
        assert metrics.cost_usd == 0.0
        assert metrics.duration_ms == 0
        assert metrics.session_id is None

    def test_custom_values(self) -> None:
        """Custom values are set correctly."""
        metrics = IterationMetrics(
            input_tokens=1000,
            output_tokens=500,
            tool_calls=5,
            cost_usd=0.015,
            duration_ms=3000,
            session_id="test-session",
        )
        assert metrics.input_tokens == 1000
        assert metrics.output_tokens == 500
        assert metrics.tool_calls == 5
        assert metrics.cost_usd == 0.015
        assert metrics.duration_ms == 3000
        assert metrics.session_id == "test-session"


class TestIterationResult:
    """Tests for IterationResult dataclass."""

    def test_default_values(self) -> None:
        """Default values are initialized correctly."""
        result = IterationResult(success=True)
        assert result.success is True
        assert result.task_completed is False
        assert result.task_id is None
        assert result.tokens_used == 0
        assert result.cost_usd == 0.0
        assert result.needs_handoff is False
        assert result.error is None
        assert result.completion_notes is None
        assert isinstance(result.metrics, IterationMetrics)
        assert result.messages == []
        assert result.final_text == ""

    def test_failed_result(self) -> None:
        """Failed result with error message."""
        result = IterationResult(success=False, error="Something went wrong")
        assert result.success is False
        assert result.error == "Something went wrong"

    def test_successful_task_completion(self) -> None:
        """Successful result with task completion."""
        result = IterationResult(
            success=True,
            task_completed=True,
            task_id="task-001",
            completion_notes="All tests passed",
            tokens_used=5000,
            cost_usd=0.05,
        )
        assert result.success is True
        assert result.task_completed is True
        assert result.task_id == "task-001"
        assert result.completion_notes == "All tests passed"

    def test_needs_handoff(self) -> None:
        """Result indicating handoff is needed."""
        result = IterationResult(success=True, needs_handoff=True)
        assert result.needs_handoff is True


class TestModelPricing:
    """Tests for model pricing constants."""

    def test_sonnet_pricing_exists(self) -> None:
        """Sonnet model pricing is defined."""
        assert "claude-sonnet-4-20250514" in MODEL_PRICING
        assert "input" in MODEL_PRICING["claude-sonnet-4-20250514"]
        assert "output" in MODEL_PRICING["claude-sonnet-4-20250514"]

    def test_opus_pricing_exists(self) -> None:
        """Opus model pricing is defined."""
        assert "claude-opus-4-20250514" in MODEL_PRICING
        assert "input" in MODEL_PRICING["claude-opus-4-20250514"]
        assert "output" in MODEL_PRICING["claude-opus-4-20250514"]

    def test_default_pricing_exists(self) -> None:
        """Default pricing fallback is defined."""
        assert "default" in MODEL_PRICING

    def test_opus_more_expensive_than_sonnet(self) -> None:
        """Opus is more expensive than Sonnet."""
        sonnet = MODEL_PRICING["claude-sonnet-4-20250514"]
        opus = MODEL_PRICING["claude-opus-4-20250514"]
        assert opus["input"] > sonnet["input"]
        assert opus["output"] > sonnet["output"]


class TestCalculateCost:
    """Tests for cost calculation function."""

    def test_calculate_cost_sonnet(self) -> None:
        """Cost calculated correctly for Sonnet model."""
        # 1M input, 1M output tokens
        cost = calculate_cost(1_000_000, 1_000_000, "claude-sonnet-4-20250514")
        # Expected: $3 input + $15 output = $18
        assert cost == pytest.approx(18.0, rel=0.01)

    def test_calculate_cost_opus(self) -> None:
        """Cost calculated correctly for Opus model."""
        # 1M input, 1M output tokens
        cost = calculate_cost(1_000_000, 1_000_000, "claude-opus-4-20250514")
        # Expected: $15 input + $75 output = $90
        assert cost == pytest.approx(90.0, rel=0.01)

    def test_calculate_cost_small_usage(self) -> None:
        """Cost calculated correctly for small token usage."""
        # 10K input, 5K output tokens with Sonnet
        cost = calculate_cost(10_000, 5_000, "claude-sonnet-4-20250514")
        # Expected: $0.03 input + $0.075 output = $0.105
        assert cost == pytest.approx(0.105, rel=0.01)

    def test_calculate_cost_zero_tokens(self) -> None:
        """Zero tokens results in zero cost."""
        cost = calculate_cost(0, 0, "claude-sonnet-4-20250514")
        assert cost == 0.0

    def test_calculate_cost_input_only(self) -> None:
        """Cost with only input tokens."""
        cost = calculate_cost(1_000_000, 0, "claude-sonnet-4-20250514")
        assert cost == pytest.approx(3.0, rel=0.01)

    def test_calculate_cost_output_only(self) -> None:
        """Cost with only output tokens."""
        cost = calculate_cost(0, 1_000_000, "claude-sonnet-4-20250514")
        assert cost == pytest.approx(15.0, rel=0.01)

    def test_calculate_cost_unknown_model(self) -> None:
        """Unknown model uses default pricing."""
        cost = calculate_cost(1_000_000, 1_000_000, "unknown-model")
        # Uses default (Sonnet-like) pricing
        assert cost == pytest.approx(18.0, rel=0.01)


class TestPhaseTools:
    """Tests for phase-specific tool allocation."""

    def test_discovery_phase_tools(self) -> None:
        """Discovery phase has correct tools."""
        tools = get_tools_for_phase(Phase.DISCOVERY)
        assert "Read" in tools
        assert "Glob" in tools
        assert "WebSearch" in tools
        assert "AskUserQuestion" in tools
        # Building-only tools not present
        assert "Edit" not in tools
        assert "BashOutput" not in tools

    def test_planning_phase_tools(self) -> None:
        """Planning phase has correct tools."""
        tools = get_tools_for_phase(Phase.PLANNING)
        assert "Read" in tools
        assert "Write" in tools
        assert "ExitPlanMode" in tools
        # Building-only tools not present
        assert "Edit" not in tools

    def test_building_phase_tools(self) -> None:
        """Building phase has full tool access."""
        tools = get_tools_for_phase(Phase.BUILDING)
        assert "Read" in tools
        assert "Write" in tools
        assert "Edit" in tools
        assert "Bash" in tools
        assert "BashOutput" in tools
        assert "KillBash" in tools
        assert "TodoWrite" in tools

    def test_validation_phase_tools(self) -> None:
        """Validation phase has correct tools."""
        tools = get_tools_for_phase(Phase.VALIDATION)
        assert "Read" in tools
        assert "Bash" in tools
        assert "Task" in tools
        # Write/Edit not in validation
        assert "Write" not in tools
        assert "Edit" not in tools

    def test_all_phases_have_read(self) -> None:
        """All phases have Read tool."""
        for phase in Phase:
            tools = get_tools_for_phase(phase)
            assert "Read" in tools, f"Read missing from {phase}"

    def test_phase_tools_constant_has_all_phases(self) -> None:
        """PHASE_TOOLS constant has all phases defined."""
        for phase in Phase:
            assert phase in PHASE_TOOLS


class TestCalculateMaxTurns:
    """Tests for turn limit calculation."""

    def test_discovery_turns(self) -> None:
        """Discovery has moderate turns for interaction."""
        assert calculate_max_turns(Phase.DISCOVERY) == 50

    def test_planning_turns(self) -> None:
        """Planning has moderate turns."""
        assert calculate_max_turns(Phase.PLANNING) == 30

    def test_building_turns(self) -> None:
        """Building has highest turns for implementation."""
        assert calculate_max_turns(Phase.BUILDING) == 100

    def test_validation_turns(self) -> None:
        """Validation has fewer turns."""
        assert calculate_max_turns(Phase.VALIDATION) == 20


class TestGetModelForPhase:
    """Tests for model selection per phase."""

    def test_default_planning_model(self) -> None:
        """Planning phase uses Opus by default."""
        model = get_model_for_phase(Phase.PLANNING)
        assert "opus" in model

    def test_default_building_model(self) -> None:
        """Building phase uses Sonnet by default."""
        model = get_model_for_phase(Phase.BUILDING)
        assert "sonnet" in model

    def test_default_discovery_model(self) -> None:
        """Discovery phase uses Sonnet by default."""
        model = get_model_for_phase(Phase.DISCOVERY)
        assert "sonnet" in model

    def test_default_validation_model(self) -> None:
        """Validation phase uses Sonnet by default."""
        model = get_model_for_phase(Phase.VALIDATION)
        assert "sonnet" in model

    def test_config_override_planning_model(self) -> None:
        """Config can override planning model."""
        config = create_mock_config()
        config.planning_model = "custom-planning-model"
        model = get_model_for_phase(Phase.PLANNING, config)
        assert model == "custom-planning-model"

    def test_config_override_primary_model(self) -> None:
        """Config can override primary model."""
        config = create_mock_config()
        config.primary_model = "custom-primary-model"
        model = get_model_for_phase(Phase.BUILDING, config)
        assert model == "custom-primary-model"


class TestRalphSDKClient:
    """Tests for RalphSDKClient class."""

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_init_with_auto_configure(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """Auto-configuration initializes hooks and MCP server."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = MagicMock()

        state = create_mock_state()
        client = RalphSDKClient(state=state, auto_configure=True)

        mock_hooks.assert_called_once()
        mock_mcp.assert_called_once()
        assert client.hooks is not None
        assert client.mcp_servers is not None

    def test_init_without_auto_configure(self) -> None:
        """Without auto-configure, hooks and MCP are not created."""
        state = create_mock_state()
        client = RalphSDKClient(state=state, auto_configure=False)
        assert client.hooks is None
        assert client.mcp_servers == {}

    def test_init_with_custom_hooks(self) -> None:
        """Custom hooks are used when provided."""
        state = create_mock_state()
        custom_hooks = create_mock_hooks()
        client = RalphSDKClient(state=state, hooks=custom_hooks, auto_configure=False)
        assert client.hooks == custom_hooks

    def test_init_with_custom_mcp_servers(self) -> None:
        """Custom MCP servers are used when provided."""
        state = create_mock_state()
        custom_servers = {"custom": MagicMock()}
        client = RalphSDKClient(
            state=state, mcp_servers=custom_servers, auto_configure=False
        )
        assert client.mcp_servers == custom_servers

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_session_id_initially_none(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """Session ID is None initially."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = MagicMock()

        state = create_mock_state()
        client = RalphSDKClient(state=state)
        assert client.session_id is None

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_reset_session(self, mock_mcp: MagicMock, mock_hooks: MagicMock) -> None:
        """Reset session clears session ID."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = MagicMock()

        state = create_mock_state()
        client = RalphSDKClient(state=state)
        client._session_id = "test-session"
        assert client.session_id == "test-session"

        client.reset_session()
        assert client.session_id is None

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_build_options_includes_allowed_tools(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """Built options include phase-appropriate tools."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        state = create_mock_state(phase=Phase.BUILDING)
        client = RalphSDKClient(state=state)
        client.mcp_servers = {}  # No MCP servers for this test

        options = client._build_options()

        # Check that building tools are included
        assert "Edit" in options.allowed_tools
        assert "Bash" in options.allowed_tools

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_build_options_respects_phase_override(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """Phase override is respected in options."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        state = create_mock_state(phase=Phase.BUILDING)
        client = RalphSDKClient(state=state)
        client.mcp_servers = {}

        options = client._build_options(phase=Phase.VALIDATION)

        # Should have validation tools, not building tools
        assert "Edit" not in options.allowed_tools
        assert "Read" in options.allowed_tools

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_build_options_sets_cwd(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """Built options set cwd from state."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        state = create_mock_state(project_root=Path("/test/project"))
        client = RalphSDKClient(state=state)
        client.mcp_servers = {}

        options = client._build_options()

        assert options.cwd == "/test/project"

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_build_options_sets_max_turns(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """Built options set max turns based on phase."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        state = create_mock_state(phase=Phase.BUILDING)
        client = RalphSDKClient(state=state)
        client.mcp_servers = {}

        options = client._build_options()

        assert options.max_turns == calculate_max_turns(Phase.BUILDING)

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_build_options_respects_max_turns_override(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """Max turns override is respected."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        state = create_mock_state(phase=Phase.BUILDING)
        client = RalphSDKClient(state=state)
        client.mcp_servers = {}

        options = client._build_options(max_turns=10)

        assert options.max_turns == 10

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_build_options_sets_budget_from_config(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """Built options set budget from config."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        state = create_mock_state()
        config = create_mock_config()
        config.cost_limits.per_iteration = 5.0
        client = RalphSDKClient(state=state, config=config)
        client.mcp_servers = {}

        options = client._build_options()

        assert options.max_budget_usd == 5.0


class TestCreateRalphClient:
    """Tests for create_ralph_client factory function."""

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_creates_client(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """Factory creates a RalphSDKClient."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = MagicMock()

        state = create_mock_state()
        client = create_ralph_client(state)

        assert isinstance(client, RalphSDKClient)
        assert client.state is state

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_passes_config(self, mock_mcp: MagicMock, mock_hooks: MagicMock) -> None:
        """Factory passes config to client."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = MagicMock()

        state = create_mock_state()
        config = create_mock_config()
        client = create_ralph_client(state, config=config)

        assert client.config is config

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_passes_custom_hooks(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """Factory passes custom hooks to client."""
        mock_mcp.return_value = MagicMock()

        state = create_mock_state()
        custom_hooks = create_mock_hooks()
        client = create_ralph_client(state, hooks=custom_hooks)

        assert client.hooks == custom_hooks

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_passes_custom_mcp_servers(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """Factory passes custom MCP servers to client."""
        mock_hooks.return_value = {"PreToolUse": []}

        state = create_mock_state()
        custom_servers = {"custom": MagicMock()}
        client = create_ralph_client(state, mcp_servers=custom_servers)

        assert client.mcp_servers == custom_servers


class TestRunIterationErrorHandling:
    """Tests for error handling in run_iteration."""

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @pytest.mark.asyncio
    async def test_handles_connection_error(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """Connection errors are handled gracefully."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        state = create_mock_state()
        client = RalphSDKClient(state=state)
        client.mcp_servers = {}

        with patch(
            "ralph.sdk_client.ClaudeSDKClient",
            side_effect=ConnectionError("Network error"),
        ):
            result = await client.run_iteration("test prompt")

        assert result.success is False
        assert "Connection error" in result.error

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @pytest.mark.asyncio
    async def test_handles_timeout_error(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """Timeout errors are handled gracefully."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        state = create_mock_state()
        client = RalphSDKClient(state=state)
        client.mcp_servers = {}

        with patch(
            "ralph.sdk_client.ClaudeSDKClient",
            side_effect=TimeoutError("Request timed out"),
        ):
            result = await client.run_iteration("test prompt")

        assert result.success is False
        assert "Timeout" in result.error

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @pytest.mark.asyncio
    async def test_handles_permission_error(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """Permission errors are handled gracefully."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        state = create_mock_state()
        client = RalphSDKClient(state=state)
        client.mcp_servers = {}

        with patch(
            "ralph.sdk_client.ClaudeSDKClient",
            side_effect=PermissionError("Access denied"),
        ):
            result = await client.run_iteration("test prompt")

        assert result.success is False
        assert "Permission" in result.error or "authentication" in result.error

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @pytest.mark.asyncio
    async def test_detects_rate_limit_in_exception(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """Rate limit errors are detected from exception message."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        state = create_mock_state()
        client = RalphSDKClient(state=state)
        client.mcp_servers = {}

        with patch(
            "ralph.sdk_client.ClaudeSDKClient",
            side_effect=Exception("Rate limit exceeded for API"),
        ):
            result = await client.run_iteration("test prompt")

        assert result.success is False
        assert "Rate limit" in result.error

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @pytest.mark.asyncio
    async def test_detects_auth_error_in_exception(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """Auth errors are detected from exception message."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        state = create_mock_state()
        client = RalphSDKClient(state=state)
        client.mcp_servers = {}

        with patch(
            "ralph.sdk_client.ClaudeSDKClient",
            side_effect=Exception("Invalid API key provided"),
        ):
            result = await client.run_iteration("test prompt")

        assert result.success is False
        assert "Authentication" in result.error
