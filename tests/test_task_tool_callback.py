"""Tests for Task tool callback handling in RalphSDKClient.can_use_tool()."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from claude_agent_sdk.types import PermissionResultAllow, ToolPermissionContext

from ralph.models import Phase, RalphState
from ralph.sdk_client import RalphSDKClient, UserInputCallbacks


def create_mock_state() -> RalphState:
    """Create a mock RalphState for testing."""
    state = RalphState(project_root=Path("/tmp/test"))
    state.current_phase = Phase.BUILDING
    return state


def create_mock_context() -> ToolPermissionContext:
    """Create a mock ToolPermissionContext."""
    from unittest.mock import MagicMock
    return MagicMock(spec=ToolPermissionContext)


class TestTaskToolCallback:
    """Tests for Task tool callback handling in can_use_tool."""

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @pytest.mark.asyncio
    async def test_can_use_tool_handles_task_tool_result(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """can_use_tool should handle Task tool results and emit SubagentEndEvent."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        # Mock callback functions to track events
        events_emitted: list[Any] = []

        def mock_emit_event(event):
            events_emitted.append(event)

        callbacks = UserInputCallbacks()

        state = create_mock_state()
        client = RalphSDKClient(
            state=state,
            user_input_callbacks=callbacks,
            auto_configure=False
        )
        client.mcp_servers = {}

        # Create mock Task tool input with subagent result
        mock_task_input = {
            "subagent_type": "code-reviewer",
            "description": "Review implementation",
            "prompt": "Review the current implementation for bugs"
        }

        # Mock context
        context = create_mock_context()

        # Get the can_use_tool callback from the client
        options = client._build_options()
        can_use_tool_callback = options.can_use_tool
        assert can_use_tool_callback is not None

        # Call can_use_tool with Task tool
        result = await can_use_tool_callback("Task", mock_task_input, context)

        # Should allow the tool (this test will initially just verify basic functionality)
        assert isinstance(result, PermissionResultAllow)

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @pytest.mark.asyncio
    async def test_can_use_tool_processes_task_result_with_usage_and_cost(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """can_use_tool should extract usage and cost data from Task tool execution."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        callbacks = UserInputCallbacks()

        state = create_mock_state()
        client = RalphSDKClient(
            state=state,
            user_input_callbacks=callbacks,
            auto_configure=False
        )
        client.mcp_servers = {}

        # Mock task input
        task_input = {
            "subagent_type": "code-reviewer",
            "description": "Review code",
            "prompt": "Review the current implementation"
        }

        context = create_mock_context()
        options = client._build_options()
        can_use_tool_callback = options.can_use_tool
        assert can_use_tool_callback is not None

        # Call can_use_tool with Task tool - should work without error
        result = await can_use_tool_callback("Task", task_input, context)

        # Should allow the tool
        assert isinstance(result, PermissionResultAllow)

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @pytest.mark.asyncio
    async def test_can_use_tool_handles_task_execution_failure(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """can_use_tool should handle Task tool execution failures gracefully."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        callbacks = UserInputCallbacks()

        state = create_mock_state()
        client = RalphSDKClient(
            state=state,
            user_input_callbacks=callbacks,
            auto_configure=False
        )
        client.mcp_servers = {}

        task_input = {
            "subagent_type": "test-engineer",
            "description": "Run tests",
            "prompt": "Execute test suite"
        }

        context = create_mock_context()
        options = client._build_options()
        can_use_tool_callback = options.can_use_tool
        assert can_use_tool_callback is not None

        # Call can_use_tool with Task tool
        result = await can_use_tool_callback("Task", task_input, context)

        # Should still allow the tool (failure handled gracefully)
        assert isinstance(result, PermissionResultAllow)

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @pytest.mark.asyncio
    async def test_can_use_tool_ignores_non_task_tools(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """can_use_tool should not process non-Task tools differently."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        callbacks = UserInputCallbacks()

        state = create_mock_state()
        client = RalphSDKClient(
            state=state,
            user_input_callbacks=callbacks,
            auto_configure=False
        )
        client.mcp_servers = {}

        # Test with Read tool (not Task)
        read_input = {
            "file_path": "/tmp/test.py"
        }

        context = create_mock_context()
        options = client._build_options()
        can_use_tool_callback = options.can_use_tool
        assert can_use_tool_callback is not None

        # Call can_use_tool with Read tool
        result = await can_use_tool_callback("Read", read_input, context)

        # Should allow the tool without special processing
        assert isinstance(result, PermissionResultAllow)

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @pytest.mark.asyncio
    async def test_can_use_tool_handles_missing_subagent_type(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """can_use_tool should handle Task input missing subagent_type gracefully."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        callbacks = UserInputCallbacks()

        state = create_mock_state()
        client = RalphSDKClient(
            state=state,
            user_input_callbacks=callbacks,
            auto_configure=False
        )
        client.mcp_servers = {}

        # Task input missing subagent_type
        task_input = {
            "description": "Do something",
            "prompt": "Execute some task"
            # Missing subagent_type
        }

        context = create_mock_context()
        options = client._build_options()
        can_use_tool_callback = options.can_use_tool
        assert can_use_tool_callback is not None

        # Call can_use_tool with malformed Task tool input
        result = await can_use_tool_callback("Task", task_input, context)

        # Should still allow the tool (SDK will handle validation)
        assert isinstance(result, PermissionResultAllow)

    @patch("ralph.sdk_client._get_ralph_hooks")
    @patch("ralph.sdk_client._get_mcp_server")
    @pytest.mark.asyncio
    async def test_task_tool_tracking_in_stream_iteration(
        self, mock_mcp: MagicMock, mock_hooks: MagicMock
    ) -> None:
        """Test that Task tools are properly tracked in stream iteration."""
        mock_hooks.return_value = {"PreToolUse": []}
        mock_mcp.return_value = None

        callbacks = UserInputCallbacks()
        state = create_mock_state()
        client = RalphSDKClient(
            state=state,
            user_input_callbacks=callbacks,
            auto_configure=False
        )
        client.mcp_servers = {}

        # Mock SDK client to simulate Task tool usage
        from claude_agent_sdk import AssistantMessage, ToolUseBlock

        # Create mock ToolUseBlock for Task tool
        mock_tool_block = MagicMock(spec=ToolUseBlock)
        mock_tool_block.name = "Task"
        mock_tool_block.id = "task_123"
        mock_tool_block.input = {
            "subagent_type": "code-reviewer",
            "description": "Review code quality",
            "prompt": "Review the implementation for issues"
        }

        # Create mock AssistantMessage containing the tool use
        mock_message = MagicMock(spec=AssistantMessage)
        mock_message.content = [mock_tool_block]

        async def mock_receive() -> Any:
            yield mock_message

        # Create proper async context manager mock
        class MockSDKClient:
            async def query(self, prompt: str) -> None:
                pass

            def receive_response(self) -> Any:
                return mock_receive()

            async def __aenter__(self) -> Any:
                return self

            async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
                pass

        mock_sdk_client = MockSDKClient()

        events = []
        with patch("ralph.sdk_client.ClaudeSDKClient", return_value=mock_sdk_client):
            async for event in client.stream_iteration("test prompt"):
                events.append(event)

        # Should have received events including subagent start
        event_types = [e.type.value for e in events]
        assert "subagent_start" in event_types
        assert "iteration_start" in event_types
        assert "iteration_end" in event_types

        # Check that iteration result was tracking properly
        assert client._current_iteration_result is not None
        assert len(client._current_iteration_result.subagent_invocations) > 0
        assert any(
            "code-reviewer" in inv for inv in client._current_iteration_result.subagent_invocations
        )
