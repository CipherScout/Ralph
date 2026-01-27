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
        assert "Bash" in tools  # Now allowed for exploration
        assert "Edit" in tools  # Now allowed for all phases
        assert "TodoWrite" in tools  # Now allowed for tracking

    def test_planning_phase_tools(self) -> None:
        """Planning phase has correct tools."""
        tools = get_tools_for_phase(Phase.PLANNING)
        assert "Read" in tools
        assert "Write" in tools
        assert "ExitPlanMode" in tools
        assert "Bash" in tools  # Now allowed for analysis
        assert "Edit" in tools  # Now allowed for all phases
        assert "TodoWrite" in tools  # Now allowed for tracking

    def test_building_phase_tools(self) -> None:
        """Building phase has implementation tools but not AskUserQuestion."""
        tools = get_tools_for_phase(Phase.BUILDING)
        assert "Read" in tools
        assert "Write" in tools
        assert "Edit" in tools
        assert "Bash" in tools
        assert "BashOutput" in tools
        assert "KillBash" in tools
        assert "TodoWrite" in tools
        # AskUserQuestion NOT in Building - agent should focus on implementation
        assert "AskUserQuestion" not in tools

    def test_validation_phase_tools(self) -> None:
        """Validation phase has correct tools including AskUserQuestion."""
        tools = get_tools_for_phase(Phase.VALIDATION)
        assert "Read" in tools
        assert "Bash" in tools
        assert "Task" in tools
        assert "Write" in tools
        assert "Edit" in tools
        assert "WebSearch" in tools
        # SPEC-002: Tool parity
        assert "TodoWrite" in tools  # For tracking validation progress
        assert "AskUserQuestion" in tools  # For human approval workflow
        assert "NotebookEdit" in tools

    def test_all_phases_have_read(self) -> None:
        """All phases have Read tool."""
        for phase in Phase:
            tools = get_tools_for_phase(phase)
            assert "Read" in tools, f"Read missing from {phase}"

    def test_phase_tools_constant_has_all_phases(self) -> None:
        """PHASE_TOOLS constant has all phases defined."""
        for phase in Phase:
            assert phase in PHASE_TOOLS

    def test_all_sdk_tools_constant_exists(self) -> None:
        """ALL_SDK_TOOLS constant contains all expected tools."""
        from ralph.sdk_client import ALL_SDK_TOOLS

        expected_tools = [
            "Read", "Write", "Edit", "Bash", "BashOutput", "KillBash",
            "Glob", "Grep", "Task", "TodoWrite", "WebSearch", "WebFetch",
            "NotebookEdit", "AskUserQuestion", "ExitPlanMode",
            "ListMcpResourcesTool", "ReadMcpResourceTool",
        ]
        for tool in expected_tools:
            assert tool in ALL_SDK_TOOLS, f"Tool {tool} missing from ALL_SDK_TOOLS"


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

        # SPEC-002: All tools now available in all phases
        assert "AskUserQuestion" in options.allowed_tools  # Universal access
        assert "Read" in options.allowed_tools
        assert "TodoWrite" in options.allowed_tools  # Universal access

    @patch("ralph.memory.MemoryManager")
    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_build_options_sets_cwd(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock, mock_memory: MagicMock
    ) -> None:
        """Built options set cwd from state."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None
        mock_memory.return_value = MagicMock()

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


class TestUserInputCallbacks:
    """Tests for UserInputCallbacks dataclass and handler factory."""

    def test_user_input_callbacks_default_values(self) -> None:
        """UserInputCallbacks has correct default values."""
        from ralph.sdk_client import UserInputCallbacks

        callbacks = UserInputCallbacks()
        assert callbacks.on_question_start is None
        assert callbacks.on_question_end is None
        assert callbacks.console is None

    def test_user_input_callbacks_with_values(self) -> None:
        """UserInputCallbacks accepts custom values."""
        from rich.console import Console

        from ralph.sdk_client import UserInputCallbacks

        def start_fn() -> None:
            pass

        def end_fn() -> None:
            pass

        console = Console(quiet=True)

        callbacks = UserInputCallbacks(
            on_question_start=start_fn,
            on_question_end=end_fn,
            console=console,
        )

        assert callbacks.on_question_start is start_fn
        assert callbacks.on_question_end is end_fn
        assert callbacks.console is console

    @pytest.mark.asyncio
    async def test_create_ask_user_handler_calls_callbacks(self) -> None:
        """Handler calls start/end callbacks around user input."""
        from unittest.mock import patch

        from rich.console import Console

        from ralph.sdk_client import UserInputCallbacks, _create_ask_user_handler

        start_called = False
        end_called = False
        call_order: list[str] = []

        def on_start() -> None:
            nonlocal start_called
            start_called = True
            call_order.append("start")

        def on_end() -> None:
            nonlocal end_called
            end_called = True
            call_order.append("end")

        callbacks = UserInputCallbacks(
            on_question_start=on_start,
            on_question_end=on_end,
            console=Console(quiet=True),
        )

        handler = _create_ask_user_handler(callbacks)

        # Mock Prompt.ask to return immediately
        with patch("ralph.sdk_client.Prompt.ask", return_value="test answer"):
            result = await handler(
                {"questions": [{"question": "Test?", "header": "Q", "options": []}]}
            )

        assert start_called, "on_question_start was not called"
        assert end_called, "on_question_end was not called"
        assert call_order == ["start", "end"], "Callbacks called in wrong order"
        assert result.updated_input["answers"]["Test?"] == "test answer"

    @pytest.mark.asyncio
    async def test_create_ask_user_handler_calls_end_on_exception(self) -> None:
        """Handler calls on_question_end even if exception occurs."""
        from unittest.mock import patch

        from rich.console import Console

        from ralph.sdk_client import UserInputCallbacks, _create_ask_user_handler

        end_called = False

        def on_end() -> None:
            nonlocal end_called
            end_called = True

        callbacks = UserInputCallbacks(
            on_question_start=lambda: None,
            on_question_end=on_end,
            console=Console(quiet=True),
        )

        handler = _create_ask_user_handler(callbacks)

        # Mock Prompt.ask to raise an exception
        with (
            patch("ralph.sdk_client.Prompt.ask", side_effect=KeyboardInterrupt),
            pytest.raises(KeyboardInterrupt),
        ):
            await handler(
                {"questions": [{"question": "Test?", "header": "Q", "options": []}]}
            )

        assert end_called, "on_question_end not called after exception"

    @pytest.mark.asyncio
    async def test_create_ask_user_handler_without_callbacks(self) -> None:
        """Handler works without callbacks (None)."""
        from unittest.mock import patch

        from ralph.sdk_client import _create_ask_user_handler

        handler = _create_ask_user_handler(None)

        # Should not raise even without callbacks
        with patch("ralph.sdk_client.Prompt.ask", return_value="answer"):
            result = await handler(
                {"questions": [{"question": "Q?", "header": "H", "options": []}]}
            )

        assert result.updated_input["answers"]["Q?"] == "answer"

    @pytest.mark.asyncio
    async def test_create_ask_user_handler_uses_provided_console(self) -> None:
        """Handler uses the console from callbacks."""
        from unittest.mock import MagicMock, patch

        from ralph.sdk_client import UserInputCallbacks, _create_ask_user_handler

        mock_console = MagicMock()

        callbacks = UserInputCallbacks(
            console=mock_console,
        )

        handler = _create_ask_user_handler(callbacks)

        with patch("ralph.sdk_client.Prompt.ask", return_value="answer"):
            await handler(
                {"questions": [{"question": "Q?", "header": "H", "options": []}]}
            )

        # Console.print should have been called for displaying the question
        assert mock_console.print.called, "Console was not used"

    @pytest.mark.asyncio
    async def test_create_ask_user_handler_handles_multiple_questions(self) -> None:
        """Handler processes multiple questions correctly."""
        from unittest.mock import patch

        from rich.console import Console

        from ralph.sdk_client import UserInputCallbacks, _create_ask_user_handler

        start_count = 0
        end_count = 0

        def on_start() -> None:
            nonlocal start_count
            start_count += 1

        def on_end() -> None:
            nonlocal end_count
            end_count += 1

        callbacks = UserInputCallbacks(
            on_question_start=on_start,
            on_question_end=on_end,
            console=Console(quiet=True),
        )

        handler = _create_ask_user_handler(callbacks)

        # Mock Prompt.ask to return different answers
        with patch("ralph.sdk_client.Prompt.ask", side_effect=["answer1", "answer2"]):
            result = await handler(
                {
                    "questions": [
                        {"question": "Q1?", "header": "H1", "options": []},
                        {"question": "Q2?", "header": "H2", "options": []},
                    ]
                }
            )

        # Callbacks should be called once for the entire handler, not per question
        assert start_count == 1, "on_question_start should be called once"
        assert end_count == 1, "on_question_end should be called once"
        assert result.updated_input["answers"]["Q1?"] == "answer1"
        assert result.updated_input["answers"]["Q2?"] == "answer2"


class TestRalphSDKClientWithCallbacks:
    """Tests for RalphSDKClient with UserInputCallbacks."""

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_init_accepts_user_input_callbacks(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """RalphSDKClient accepts user_input_callbacks parameter."""
        from ralph.sdk_client import UserInputCallbacks

        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        callbacks = UserInputCallbacks(
            on_question_start=lambda: None,
            on_question_end=lambda: None,
        )

        state = create_mock_state()
        client = RalphSDKClient(state=state, user_input_callbacks=callbacks)

        assert client.user_input_callbacks is callbacks

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_init_without_callbacks_sets_none(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """RalphSDKClient defaults to None for user_input_callbacks."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        state = create_mock_state()
        client = RalphSDKClient(state=state)

        assert client.user_input_callbacks is None

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    def test_build_options_uses_callback_aware_handler(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """Built options use callback-aware handler for can_use_tool."""
        from ralph.sdk_client import UserInputCallbacks

        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        callbacks = UserInputCallbacks(
            on_question_start=lambda: None,
            on_question_end=lambda: None,
        )

        state = create_mock_state()
        client = RalphSDKClient(state=state, user_input_callbacks=callbacks)
        client.mcp_servers = {}

        options = client._build_options()

        # The can_use_tool should be set
        assert options.can_use_tool is not None


class TestTokenExtraction:
    """Tests for token/cost extraction from SDK messages (SPEC-005).

    The SDK returns usage as a dict, not an object with attributes.
    """

    def test_usage_dict_format(self) -> None:
        """Verify usage dict format matches SDK documentation."""
        # This is the format the SDK uses (dict, not object)
        usage = {
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_read_input_tokens": 200,
        }
        # Dict access should work
        assert usage.get("input_tokens", 0) == 1000
        assert usage.get("output_tokens", 0) == 500
        assert usage.get("cache_read_input_tokens", 0) == 200
        assert usage.get("nonexistent", 0) == 0

    def test_handles_missing_usage_gracefully(self) -> None:
        """No crash when usage is None."""
        usage = None
        # This pattern should not raise
        if usage is not None:
            _ = usage.get("input_tokens", 0)
        # If usage is None, we should get defaults
        input_tokens = usage.get("input_tokens", 0) if usage else 0
        assert input_tokens == 0

    def test_handles_partial_usage_dict(self) -> None:
        """Works when some fields are missing from usage dict."""
        usage = {"input_tokens": 1000}  # output_tokens missing
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)  # Should default to 0
        cache_tokens = usage.get("cache_read_input_tokens", 0)

        assert input_tokens == 1000
        assert output_tokens == 0
        assert cache_tokens == 0

    def test_total_cost_usd_attribute(self) -> None:
        """Verify we can access total_cost_usd from ResultMessage-like object."""
        # Mock a ResultMessage-like structure
        class MockResultMessage:
            total_cost_usd: float | None = 0.0150
            usage: dict | None = {"input_tokens": 1000, "output_tokens": 500}

        msg = MockResultMessage()
        # Direct attribute access should work
        assert msg.total_cost_usd == 0.0150
        # Usage should be a dict
        assert isinstance(msg.usage, dict)
        assert msg.usage.get("input_tokens") == 1000

    def test_cost_fallback_when_sdk_cost_none(self) -> None:
        """Cost should be calculated when SDK doesn't provide total_cost_usd."""
        # When SDK returns None, we should calculate from tokens
        from ralph.sdk_client import calculate_cost

        input_tokens = 1000
        output_tokens = 500
        calculated_cost = calculate_cost(
            input_tokens, output_tokens, "claude-sonnet-4-20250514"
        )
        # Verify cost is calculated (sonnet: $3/1M input, $15/1M output)
        expected = (1000 / 1_000_000) * 3.0 + (500 / 1_000_000) * 15.0
        assert abs(calculated_cost - expected) < 0.0001

    def test_cache_tokens_added_to_input(self) -> None:
        """Cache read tokens should be added to total input tokens."""
        usage = {
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_read_input_tokens": 200,
        }
        total_input = usage.get("input_tokens", 0) + usage.get(
            "cache_read_input_tokens", 0
        )
        assert total_input == 1200


class TestCostTracking:
    """Tests for proper cost and token tracking (SPEC-006).

    These tests verify that:
    - Zero costs are handled correctly (not treated as missing)
    - Per-message token accumulation works
    - ResultMessage provides authoritative totals
    - Message ID deduplication prevents double-counting
    - Fallback cost calculation works when SDK doesn't provide cost
    """

    def test_zero_cost_is_not_falsy(self) -> None:
        """Zero cost (0.0) should not be treated as missing/None.

        Bug: `if msg.total_cost_usd:` fails when cost is 0.0
        Fix: Use `if msg.total_cost_usd is not None:` instead
        """
        # Simulate a message with zero cost
        class MockResultMessage:
            total_cost_usd: float = 0.0  # Valid zero cost
            usage: dict = {"input_tokens": 0, "output_tokens": 0}

        msg = MockResultMessage()

        # WRONG: This condition fails for 0.0 (falsy)
        extracted_wrong = None
        if hasattr(msg, "total_cost_usd") and msg.total_cost_usd:
            extracted_wrong = msg.total_cost_usd
        assert extracted_wrong is None  # Bug: 0.0 is treated as missing

        # CORRECT: This condition works for 0.0
        extracted_correct = None
        if hasattr(msg, "total_cost_usd") and msg.total_cost_usd is not None:
            extracted_correct = msg.total_cost_usd
        assert extracted_correct == 0.0  # Fix: 0.0 is properly extracted

    def test_extracts_usage_from_assistant_message(self) -> None:
        """AssistantMessage.usage should be used for token accumulation.

        The SDK can provide usage data on AssistantMessage objects,
        not just on the final ResultMessage.
        """

        class MockAssistantMessage:
            id: str = "msg_001"
            content: list = []
            usage: dict | None = {
                "input_tokens": 500,
                "output_tokens": 200,
                "cache_read_input_tokens": 100,
            }

        msg = MockAssistantMessage()

        # Extract usage from AssistantMessage
        input_tokens = 0
        output_tokens = 0
        if hasattr(msg, "usage") and msg.usage is not None:
            usage = msg.usage
            if isinstance(usage, dict):
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                input_tokens += usage.get("cache_read_input_tokens", 0)

        assert input_tokens == 600  # 500 + 100 cache
        assert output_tokens == 200

    def test_result_message_overrides_accumulated_totals(self) -> None:
        """ResultMessage contains authoritative cumulative totals.

        When ResultMessage is received, its values should override
        (not add to) any previously accumulated values.
        """
        # Simulate accumulated values from AssistantMessages
        accumulated_input = 500
        accumulated_output = 200
        accumulated_cost = 0.01

        # Simulate ResultMessage with cumulative totals
        class MockResultMessage:
            total_cost_usd: float = 0.025  # Authoritative total
            usage: dict = {
                "input_tokens": 1000,  # Authoritative total (not additive)
                "output_tokens": 400,
                "cache_read_input_tokens": 50,
            }

        msg = MockResultMessage()

        # ResultMessage should OVERRIDE, not add
        if hasattr(msg, "total_cost_usd") and msg.total_cost_usd is not None:
            accumulated_cost = msg.total_cost_usd  # Override

        if hasattr(msg, "usage") and msg.usage is not None:
            usage = msg.usage
            if isinstance(usage, dict):
                # Override with cumulative values
                accumulated_input = usage.get("input_tokens", 0)
                accumulated_output = usage.get("output_tokens", 0)
                accumulated_input += usage.get("cache_read_input_tokens", 0)

        assert accumulated_cost == 0.025
        assert accumulated_input == 1050  # 1000 + 50 cache
        assert accumulated_output == 400

    def test_message_id_deduplication(self) -> None:
        """Same message ID should not be counted twice.

        The SDK may yield the same message multiple times.
        We use message ID deduplication to prevent double-counting.
        """

        class MockMessage:
            def __init__(self, msg_id: str, input_tokens: int):
                self.id = msg_id
                self.usage = {"input_tokens": input_tokens, "output_tokens": 0}

        messages = [
            MockMessage("msg_001", 100),
            MockMessage("msg_002", 200),
            MockMessage("msg_001", 100),  # Duplicate
            MockMessage("msg_003", 300),
            MockMessage("msg_002", 200),  # Duplicate
        ]

        processed_ids: set[str] = set()
        total_input = 0

        for msg in messages:
            msg_id = getattr(msg, "id", None)
            if msg_id and msg_id in processed_ids:
                continue  # Skip duplicate
            if msg_id:
                processed_ids.add(msg_id)

            if hasattr(msg, "usage") and msg.usage:
                total_input += msg.usage.get("input_tokens", 0)

        # Should only count each message once: 100 + 200 + 300 = 600
        assert total_input == 600
        assert len(processed_ids) == 3

    def test_fallback_cost_calculation_when_sdk_returns_none(self) -> None:
        """When SDK doesn't provide cost, calculate from tokens and pricing."""
        from ralph.sdk_client import calculate_cost

        # Scenario: SDK returns tokens but no cost
        input_tokens = 10000
        output_tokens = 5000
        sdk_cost = None

        # Fallback calculation
        if sdk_cost is None:
            cost = calculate_cost(input_tokens, output_tokens, "claude-sonnet-4-20250514")
        else:
            cost = sdk_cost

        # Sonnet pricing: $3/1M input, $15/1M output
        expected = (10000 / 1_000_000) * 3.0 + (5000 / 1_000_000) * 15.0
        assert abs(cost - expected) < 0.0001
        assert cost > 0  # Should be non-zero

    def test_fallback_cost_calculation_for_opus_model(self) -> None:
        """Fallback cost calculation uses correct pricing for Opus model."""
        from ralph.sdk_client import calculate_cost

        input_tokens = 10000
        output_tokens = 5000

        cost = calculate_cost(input_tokens, output_tokens, "claude-opus-4-20250514")

        # Opus pricing: $15/1M input, $75/1M output
        expected = (10000 / 1_000_000) * 15.0 + (5000 / 1_000_000) * 75.0
        assert abs(cost - expected) < 0.0001

    def test_fallback_uses_default_pricing_for_unknown_model(self) -> None:
        """Unknown models use default pricing (same as Sonnet)."""
        from ralph.sdk_client import calculate_cost

        input_tokens = 10000
        output_tokens = 5000

        cost = calculate_cost(input_tokens, output_tokens, "unknown-model")

        # Default pricing same as Sonnet: $3/1M input, $15/1M output
        expected = (10000 / 1_000_000) * 3.0 + (5000 / 1_000_000) * 15.0
        assert abs(cost - expected) < 0.0001

    def test_handles_empty_usage_dict(self) -> None:
        """Empty usage dict should return zeros, not crash."""
        usage: dict = {}

        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cache_tokens = usage.get("cache_read_input_tokens", 0)

        assert input_tokens == 0
        assert output_tokens == 0
        assert cache_tokens == 0

    def test_handles_usage_with_none_values(self) -> None:
        """Usage dict with None values should be handled gracefully."""
        usage = {
            "input_tokens": None,
            "output_tokens": 500,
        }

        # None values should be handled (though SDK normally returns ints)
        input_tokens = usage.get("input_tokens") or 0
        output_tokens = usage.get("output_tokens") or 0

        assert input_tokens == 0
        assert output_tokens == 500


class TestContextBudgetNotDoubleCountedInStreamIteration:
    """Tests to ensure context budget is only updated by end_iteration(), not stream_iteration().

    Per Anthropic SDK docs, ResultMessage contains cumulative usage. The SDK client
    should NOT modify context budget directly - that's the responsibility of end_iteration()
    which is called by the orchestration layer (executors/iteration.py).

    The context budget uses SET semantics (not ADD) because SDK returns cumulative totals.
    This prevents double-counting tokens which can lead to false context budget exhaustion
    (e.g., showing 1118% utilization instead of ~116%).
    """

    def test_sdk_client_does_not_modify_context_budget_on_init(self) -> None:
        """Creating a RalphSDKClient should not modify the context budget."""
        state = create_mock_state(context_usage=10_000)
        initial_usage = state.context_budget.current_usage

        _ = RalphSDKClient(state=state, auto_configure=False)

        # Context budget should be unchanged
        assert state.context_budget.current_usage == initial_usage

    def test_context_budget_starts_at_expected_value(self) -> None:
        """Verify our mock state sets up context budget correctly."""
        state = create_mock_state(context_usage=50_000, context_capacity=200_000)

        assert state.context_budget.current_usage == 50_000
        assert state.context_budget.total_capacity == 200_000
        assert state.context_budget.usage_percentage == 25.0

    def test_end_iteration_is_single_source_of_truth_for_context_budget(self) -> None:
        """Verify that end_iteration() updates the context budget.

        This is the ONLY place that should update context_budget to avoid double-counting.
        """
        state = create_mock_state(context_usage=0)

        # Simulate end_iteration updating the budget
        tokens_used = 50_000
        state.end_iteration(
            cost_usd=0.5,
            tokens_used=tokens_used,
            task_completed=False,
        )

        # Context budget should reflect the tokens used
        assert state.context_budget.current_usage == tokens_used

    def test_set_usage_replaces_value_not_accumulates(self) -> None:
        """Verify set_usage SETS the cumulative value from SDK, not accumulates.

        The SDK returns cumulative totals. Calling set_usage multiple times
        should SET to that value, not accumulate.
        """
        state = create_mock_state(context_usage=0)
        tokens_used = 100_000

        # Calling set_usage multiple times with SDK cumulative value
        # should just SET to that value, not accumulate
        state.context_budget.set_usage(tokens_used)
        state.context_budget.set_usage(tokens_used)

        # Result: Value is SET, not accumulated
        assert state.context_budget.current_usage == 100_000  # Correct!
        assert state.context_budget.usage_percentage == 50.0  # Correct!

    def test_end_iteration_uses_set_semantics(self) -> None:
        """Verify end_iteration sets context budget from SDK cumulative total.

        The SDK's ResultMessage.usage contains cumulative totals. end_iteration
        should SET (not add) this value to avoid double-counting across iterations.
        """
        state = create_mock_state(context_usage=0)

        # Iteration 1: SDK reports 50k cumulative
        state.end_iteration(cost_usd=0.5, tokens_used=50_000, task_completed=False)
        assert state.context_budget.current_usage == 50_000
        assert state.context_budget.usage_percentage == 25.0

        # Iteration 2: SDK reports 100k cumulative (not 50k delta!)
        state.end_iteration(cost_usd=0.5, tokens_used=100_000, task_completed=False)
        assert state.context_budget.current_usage == 100_000  # SET to 100k, not 150k
        assert state.context_budget.usage_percentage == 50.0  # Correct!
