"""Tests for MCP tools integration."""

from unittest.mock import MagicMock, patch

import pytest

from ralph.mcp_tools import (
    MAX_DESCRIPTION_LENGTH,
    MAX_LEARNING_LENGTH,
    MAX_MEMORY_CONTENT_LENGTH,
    MAX_TASK_ID_LENGTH,
    RALPH_MCP_TOOLS,
    VALID_CATEGORIES,
    VALID_MEMORY_MODES,
    ValidationError,
    _format_result,
    _validate_category,
    _validate_dependencies,
    _validate_priority,
    _validate_task_id,
    _validate_tokens_used,
    _validate_verification_criteria,
    get_ralph_tool_names,
    ralph_add_task,
    ralph_append_learning,
    ralph_get_next_task,
    ralph_get_plan_summary,
    ralph_get_state_summary,
    ralph_increment_retry,
    ralph_mark_task_blocked,
    ralph_mark_task_complete,
    ralph_mark_task_in_progress,
    ralph_update_memory,
)
from ralph.tools import ToolResult


class TestValidateTaskId:
    """Tests for task ID validation."""

    def test_valid_task_id(self) -> None:
        """Valid task IDs are accepted."""
        assert _validate_task_id("task-001") == "task-001"
        assert _validate_task_id("task_001") == "task_001"
        assert _validate_task_id("TASK001") == "TASK001"
        assert _validate_task_id("t1") == "t1"

    def test_strips_whitespace(self) -> None:
        """Whitespace is stripped from task IDs."""
        assert _validate_task_id("  task-001  ") == "task-001"

    def test_rejects_non_string(self) -> None:
        """Non-string values are rejected."""
        with pytest.raises(ValidationError, match="must be a string"):
            _validate_task_id(123)
        with pytest.raises(ValidationError, match="must be a string"):
            _validate_task_id(None)
        with pytest.raises(ValidationError, match="must be a string"):
            _validate_task_id(["task"])

    def test_rejects_empty_string(self) -> None:
        """Empty strings are rejected."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            _validate_task_id("")
        with pytest.raises(ValidationError, match="cannot be empty"):
            _validate_task_id("   ")

    def test_rejects_too_long(self) -> None:
        """Too-long task IDs are rejected."""
        long_id = "a" * (MAX_TASK_ID_LENGTH + 1)
        with pytest.raises(ValidationError, match="too long"):
            _validate_task_id(long_id)

    def test_accepts_max_length(self) -> None:
        """Max length task IDs are accepted."""
        max_id = "a" * MAX_TASK_ID_LENGTH
        assert _validate_task_id(max_id) == max_id

    def test_rejects_invalid_characters(self) -> None:
        """Task IDs with invalid characters are rejected."""
        with pytest.raises(ValidationError, match="alphanumeric"):
            _validate_task_id("task.001")
        with pytest.raises(ValidationError, match="alphanumeric"):
            _validate_task_id("task 001")
        with pytest.raises(ValidationError, match="alphanumeric"):
            _validate_task_id("task/001")
        with pytest.raises(ValidationError, match="alphanumeric"):
            _validate_task_id("task@001")


class TestValidateTokensUsed:
    """Tests for tokens_used validation."""

    def test_valid_integer(self) -> None:
        """Valid integers are accepted."""
        assert _validate_tokens_used(1000) == 1000
        assert _validate_tokens_used(0) == 0

    def test_none_returns_none(self) -> None:
        """None value returns None."""
        assert _validate_tokens_used(None) is None

    def test_converts_string_to_int(self) -> None:
        """String integers are converted."""
        assert _validate_tokens_used("1000") == 1000

    def test_rejects_negative(self) -> None:
        """Negative values are rejected."""
        with pytest.raises(ValidationError, match="cannot be negative"):
            _validate_tokens_used(-1)

    def test_rejects_unreasonably_large(self) -> None:
        """Unreasonably large values are rejected."""
        with pytest.raises(ValidationError, match="unreasonably large"):
            _validate_tokens_used(100_000_000)

    def test_accepts_reasonable_large(self) -> None:
        """Reasonable large values are accepted."""
        assert _validate_tokens_used(1_000_000) == 1_000_000

    def test_rejects_invalid_string(self) -> None:
        """Invalid strings are rejected."""
        with pytest.raises(ValidationError, match="must be an integer"):
            _validate_tokens_used("not-a-number")


class TestValidatePriority:
    """Tests for priority validation."""

    def test_valid_priority(self) -> None:
        """Valid priorities are accepted."""
        assert _validate_priority(1) == 1
        assert _validate_priority(100) == 100
        assert _validate_priority(1000) == 1000

    def test_converts_string_to_int(self) -> None:
        """String integers are converted."""
        assert _validate_priority("5") == 5

    def test_rejects_zero(self) -> None:
        """Zero priority is rejected."""
        with pytest.raises(ValidationError, match="at least 1"):
            _validate_priority(0)

    def test_rejects_negative(self) -> None:
        """Negative priorities are rejected."""
        with pytest.raises(ValidationError, match="at least 1"):
            _validate_priority(-1)

    def test_rejects_too_high(self) -> None:
        """Too-high priorities are rejected."""
        with pytest.raises(ValidationError, match="too high"):
            _validate_priority(1001)

    def test_rejects_invalid_string(self) -> None:
        """Invalid strings are rejected."""
        with pytest.raises(ValidationError, match="must be an integer"):
            _validate_priority("high")


class TestValidateCategory:
    """Tests for category validation."""

    def test_valid_categories(self) -> None:
        """Valid categories are accepted."""
        for category in VALID_CATEGORIES:
            assert _validate_category(category) == category

    def test_case_insensitive(self) -> None:
        """Categories are case insensitive."""
        assert _validate_category("PATTERN") == "pattern"
        assert _validate_category("Pattern") == "pattern"

    def test_strips_whitespace(self) -> None:
        """Whitespace is stripped."""
        assert _validate_category("  pattern  ") == "pattern"

    def test_rejects_invalid_category(self) -> None:
        """Invalid categories are rejected."""
        with pytest.raises(ValidationError, match="must be one of"):
            _validate_category("invalid")

    def test_rejects_non_string(self) -> None:
        """Non-string values are rejected."""
        with pytest.raises(ValidationError, match="must be a string"):
            _validate_category(123)


class TestValidateDependencies:
    """Tests for dependencies validation."""

    def test_none_returns_none(self) -> None:
        """None value returns None."""
        assert _validate_dependencies(None) is None

    def test_empty_string_returns_none(self) -> None:
        """Empty string returns None."""
        assert _validate_dependencies("") is None
        assert _validate_dependencies("   ") is None

    def test_single_string_converted_to_list(self) -> None:
        """Single string is wrapped in list."""
        result = _validate_dependencies("task-001")
        assert result == ["task-001"]

    def test_comma_separated_string_split(self) -> None:
        """Comma-separated string is split into list."""
        result = _validate_dependencies("task-001, task-002, task-003")
        assert result == ["task-001", "task-002", "task-003"]

    def test_list_preserved(self) -> None:
        """List input is validated and preserved."""
        result = _validate_dependencies(["task-001", "task-002"])
        assert result == ["task-001", "task-002"]

    def test_strips_whitespace(self) -> None:
        """Whitespace is stripped from dependencies."""
        result = _validate_dependencies("  task-001  ,  task-002  ")
        assert result == ["task-001", "task-002"]

    def test_validates_each_dependency(self) -> None:
        """Each dependency is validated as task ID."""
        with pytest.raises(ValidationError, match="alphanumeric"):
            _validate_dependencies(["task.invalid"])

    def test_rejects_invalid_type(self) -> None:
        """Invalid types are rejected."""
        with pytest.raises(ValidationError, match="must be a list or comma-separated string"):
            _validate_dependencies(123)


class TestValidateVerificationCriteria:
    """Tests for verification criteria validation."""

    def test_none_returns_none(self) -> None:
        """None value returns None."""
        assert _validate_verification_criteria(None) is None

    def test_empty_string_returns_none(self) -> None:
        """Empty string returns None."""
        assert _validate_verification_criteria("") is None
        assert _validate_verification_criteria("   ") is None

    def test_single_string_converted_to_list(self) -> None:
        """Single string is wrapped in list."""
        result = _validate_verification_criteria("All tests pass")
        assert result == ["All tests pass"]

    def test_list_preserved(self) -> None:
        """List input is preserved."""
        result = _validate_verification_criteria(["Test 1", "Test 2"])
        assert result == ["Test 1", "Test 2"]

    def test_strips_whitespace(self) -> None:
        """Whitespace is stripped from criteria."""
        result = _validate_verification_criteria("  All tests pass  ")
        assert result == ["All tests pass"]

    def test_rejects_non_string_items(self) -> None:
        """Non-string list items are rejected."""
        with pytest.raises(ValidationError, match="must be a string"):
            _validate_verification_criteria([123])

    def test_rejects_invalid_type(self) -> None:
        """Invalid types are rejected."""
        with pytest.raises(ValidationError, match="must be a list or string"):
            _validate_verification_criteria(123)


class TestFormatResult:
    """Tests for result formatting."""

    def test_success_result(self) -> None:
        """Successful result is formatted correctly."""
        result = ToolResult(success=True, content="Task completed")
        formatted = _format_result(result)
        assert "content" in formatted
        assert formatted["content"][0]["type"] == "text"
        assert "Task completed" in formatted["content"][0]["text"]

    def test_success_with_data(self) -> None:
        """Successful result with data includes JSON."""
        result = ToolResult(
            success=True, content="Task info", data={"id": "task-1", "status": "done"}
        )
        formatted = _format_result(result)
        assert "task-1" in formatted["content"][0]["text"]

    def test_error_result(self) -> None:
        """Error result is formatted correctly."""
        result = ToolResult(success=False, content="Task not found")
        formatted = _format_result(result)
        assert "is_error" in formatted
        assert formatted["is_error"] is True
        assert "Error:" in formatted["content"][0]["text"]

    def test_error_with_details(self) -> None:
        """Error result with details includes them."""
        result = ToolResult(
            success=False, content="Task not found", error="ID does not exist"
        )
        formatted = _format_result(result)
        assert "Details:" in formatted["content"][0]["text"]


class TestRalphGetNextTask:
    """Tests for ralph_get_next_task tool."""

    @pytest.mark.asyncio
    async def test_returns_next_task(self) -> None:
        """Returns next task when available."""
        mock_tools = MagicMock()
        mock_tools.get_next_task.return_value = ToolResult(
            success=True,
            content="Next task",
            data={"id": "task-1", "description": "Do something"},
        )

        with patch("ralph.mcp_tools._ralph_tools", mock_tools):
            result = await ralph_get_next_task.handler({})

        assert "content" in result
        mock_tools.get_next_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_no_tasks(self) -> None:
        """Handles when no tasks are available."""
        mock_tools = MagicMock()
        mock_tools.get_next_task.return_value = ToolResult(
            success=False, content="No tasks available"
        )

        with patch("ralph.mcp_tools._ralph_tools", mock_tools):
            result = await ralph_get_next_task.handler({})

        assert "is_error" in result


class TestRalphMarkTaskComplete:
    """Tests for ralph_mark_task_complete tool."""

    @pytest.mark.asyncio
    async def test_marks_task_complete(self) -> None:
        """Marks task as complete successfully."""
        mock_tools = MagicMock()
        mock_tools.mark_task_complete.return_value = ToolResult(
            success=True, content="Task marked complete"
        )

        with patch("ralph.mcp_tools._ralph_tools", mock_tools):
            result = await ralph_mark_task_complete.handler(
                {"task_id": "task-1", "verification_notes": "All tests pass"}
            )

        assert "content" in result
        mock_tools.mark_task_complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_validates_task_id(self) -> None:
        """Validates task ID before calling tool."""
        result = await ralph_mark_task_complete.handler({"task_id": ""})
        assert "is_error" in result
        assert "Validation error" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_validates_tokens_used(self) -> None:
        """Validates tokens_used if provided."""
        result = await ralph_mark_task_complete.handler(
            {"task_id": "task-1", "tokens_used": -100}
        )
        assert "is_error" in result


class TestRalphMarkTaskBlocked:
    """Tests for ralph_mark_task_blocked tool."""

    @pytest.mark.asyncio
    async def test_marks_task_blocked(self) -> None:
        """Marks task as blocked successfully."""
        mock_tools = MagicMock()
        mock_tools.mark_task_blocked.return_value = ToolResult(
            success=True, content="Task marked blocked"
        )

        with patch("ralph.mcp_tools._ralph_tools", mock_tools):
            result = await ralph_mark_task_blocked.handler(
                {"task_id": "task-1", "reason": "Missing dependency"}
            )

        assert "content" in result
        mock_tools.mark_task_blocked.assert_called_once()

    @pytest.mark.asyncio
    async def test_validates_task_id(self) -> None:
        """Validates task ID."""
        result = await ralph_mark_task_blocked.handler({"task_id": "invalid id!", "reason": "test"})
        assert "is_error" in result

    @pytest.mark.asyncio
    async def test_requires_reason(self) -> None:
        """Requires a reason."""
        result = await ralph_mark_task_blocked.handler({"task_id": "task-1", "reason": ""})
        assert "is_error" in result
        assert "reason" in result["content"][0]["text"].lower()


class TestRalphMarkTaskInProgress:
    """Tests for ralph_mark_task_in_progress tool."""

    @pytest.mark.asyncio
    async def test_marks_task_in_progress(self) -> None:
        """Marks task as in progress successfully."""
        mock_tools = MagicMock()
        mock_tools.mark_task_in_progress.return_value = ToolResult(
            success=True, content="Task marked in progress"
        )

        with patch("ralph.mcp_tools._ralph_tools", mock_tools):
            result = await ralph_mark_task_in_progress.handler({"task_id": "task-1"})

        assert "content" in result
        mock_tools.mark_task_in_progress.assert_called_once()

    @pytest.mark.asyncio
    async def test_validates_task_id(self) -> None:
        """Validates task ID."""
        result = await ralph_mark_task_in_progress.handler({"task_id": 123})
        assert "is_error" in result


class TestRalphAppendLearning:
    """Tests for ralph_append_learning tool."""

    @pytest.mark.asyncio
    async def test_appends_learning(self) -> None:
        """Appends learning successfully."""
        mock_tools = MagicMock()
        mock_tools.append_learning.return_value = ToolResult(
            success=True, content="Learning recorded"
        )

        with patch("ralph.mcp_tools._ralph_tools", mock_tools):
            result = await ralph_append_learning.handler(
                {"learning": "Use async/await for IO", "category": "pattern"}
            )

        assert "content" in result
        mock_tools.append_learning.assert_called_once()

    @pytest.mark.asyncio
    async def test_validates_learning_content(self) -> None:
        """Validates learning content."""
        result = await ralph_append_learning.handler({"learning": "", "category": "pattern"})
        assert "is_error" in result

    @pytest.mark.asyncio
    async def test_validates_category(self) -> None:
        """Validates category."""
        result = await ralph_append_learning.handler(
            {"learning": "Some learning", "category": "invalid"}
        )
        assert "is_error" in result

    @pytest.mark.asyncio
    async def test_rejects_too_long_learning(self) -> None:
        """Rejects too-long learning content."""
        long_learning = "a" * (MAX_LEARNING_LENGTH + 1)
        result = await ralph_append_learning.handler(
            {"learning": long_learning, "category": "pattern"}
        )
        assert "is_error" in result


class TestRalphGetPlanSummary:
    """Tests for ralph_get_plan_summary tool."""

    @pytest.mark.asyncio
    async def test_returns_summary(self) -> None:
        """Returns plan summary."""
        mock_tools = MagicMock()
        mock_tools.get_plan_summary.return_value = ToolResult(
            success=True,
            content="Plan summary",
            data={"total_tasks": 10, "completed": 3},
        )

        with patch("ralph.mcp_tools._ralph_tools", mock_tools):
            result = await ralph_get_plan_summary.handler({})

        assert "content" in result
        mock_tools.get_plan_summary.assert_called_once()


class TestRalphGetStateSummary:
    """Tests for ralph_get_state_summary tool."""

    @pytest.mark.asyncio
    async def test_returns_summary(self) -> None:
        """Returns state summary."""
        mock_tools = MagicMock()
        mock_tools.get_state_summary.return_value = ToolResult(
            success=True,
            content="State summary",
            data={"phase": "building", "iteration": 5},
        )

        with patch("ralph.mcp_tools._ralph_tools", mock_tools):
            result = await ralph_get_state_summary.handler({})

        assert "content" in result
        mock_tools.get_state_summary.assert_called_once()


class TestRalphAddTask:
    """Tests for ralph_add_task tool."""

    @pytest.mark.asyncio
    async def test_adds_task(self) -> None:
        """Adds task successfully."""
        mock_tools = MagicMock()
        mock_tools.add_task.return_value = ToolResult(
            success=True, content="Task added"
        )

        with patch("ralph.mcp_tools._ralph_tools", mock_tools):
            result = await ralph_add_task.handler(
                {
                    "task_id": "task-new",
                    "description": "New task description",
                    "priority": 2,
                }
            )

        assert "content" in result
        mock_tools.add_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_validates_task_id(self) -> None:
        """Validates task ID."""
        result = await ralph_add_task.handler(
            {"task_id": "", "description": "Test", "priority": 1}
        )
        assert "is_error" in result

    @pytest.mark.asyncio
    async def test_validates_description(self) -> None:
        """Validates description."""
        result = await ralph_add_task.handler(
            {"task_id": "task-1", "description": "", "priority": 1}
        )
        assert "is_error" in result

    @pytest.mark.asyncio
    async def test_validates_priority(self) -> None:
        """Validates priority."""
        result = await ralph_add_task.handler(
            {"task_id": "task-1", "description": "Test", "priority": 0}
        )
        assert "is_error" in result

    @pytest.mark.asyncio
    async def test_rejects_too_long_description(self) -> None:
        """Rejects too-long descriptions."""
        long_desc = "a" * (MAX_DESCRIPTION_LENGTH + 1)
        result = await ralph_add_task.handler(
            {"task_id": "task-1", "description": long_desc, "priority": 1}
        )
        assert "is_error" in result


class TestRalphIncrementRetry:
    """Tests for ralph_increment_retry tool."""

    @pytest.mark.asyncio
    async def test_increments_retry(self) -> None:
        """Increments retry count successfully."""
        mock_tools = MagicMock()
        mock_tools.increment_retry.return_value = ToolResult(
            success=True, content="Retry count incremented"
        )

        with patch("ralph.mcp_tools._ralph_tools", mock_tools):
            result = await ralph_increment_retry.handler({"task_id": "task-1"})

        assert "content" in result
        mock_tools.increment_retry.assert_called_once()

    @pytest.mark.asyncio
    async def test_validates_task_id(self) -> None:
        """Validates task ID."""
        result = await ralph_increment_retry.handler({"task_id": ""})
        assert "is_error" in result


class TestGetRalphToolNames:
    """Tests for get_ralph_tool_names function."""

    def test_returns_qualified_names(self) -> None:
        """Returns fully qualified tool names."""
        names = get_ralph_tool_names()
        for name in names:
            assert name.startswith("mcp__ralph__")

    def test_includes_all_tools(self) -> None:
        """Includes all Ralph tools."""
        names = get_ralph_tool_names()
        assert "mcp__ralph__ralph_get_next_task" in names
        assert "mcp__ralph__ralph_mark_task_complete" in names
        assert "mcp__ralph__ralph_mark_task_blocked" in names
        assert "mcp__ralph__ralph_mark_task_in_progress" in names
        assert "mcp__ralph__ralph_append_learning" in names
        assert "mcp__ralph__ralph_get_plan_summary" in names
        assert "mcp__ralph__ralph_get_state_summary" in names
        assert "mcp__ralph__ralph_add_task" in names
        assert "mcp__ralph__ralph_increment_retry" in names
        assert "mcp__ralph__ralph_update_memory" in names

    def test_respects_custom_server_name(self) -> None:
        """Respects custom server name."""
        names = get_ralph_tool_names("custom")
        for name in names:
            assert name.startswith("mcp__custom__")


class TestRalphMcpToolsConstant:
    """Tests for RALPH_MCP_TOOLS constant."""

    def test_has_expected_count(self) -> None:
        """Has expected number of tools."""
        # 9 original tools + 4 phase completion signal tools + 1 memory tool
        assert len(RALPH_MCP_TOOLS) == 14

    def test_all_have_handler(self) -> None:
        """All tools have callable handler."""
        for tool in RALPH_MCP_TOOLS:
            assert hasattr(tool, "handler")
            assert callable(tool.handler)


class TestValidationConstants:
    """Tests for validation constants."""

    def test_task_id_max_length_reasonable(self) -> None:
        """Task ID max length is reasonable."""
        assert MAX_TASK_ID_LENGTH >= 10
        assert MAX_TASK_ID_LENGTH <= 1000

    def test_description_max_length_reasonable(self) -> None:
        """Description max length is reasonable."""
        assert MAX_DESCRIPTION_LENGTH >= 100
        assert MAX_DESCRIPTION_LENGTH <= 100_000

    def test_learning_max_length_reasonable(self) -> None:
        """Learning max length is reasonable."""
        assert MAX_LEARNING_LENGTH >= 100
        assert MAX_LEARNING_LENGTH <= 10_000

    def test_valid_categories_not_empty(self) -> None:
        """Valid categories set is not empty."""
        assert len(VALID_CATEGORIES) > 0

    def test_pattern_is_valid_category(self) -> None:
        """Pattern is a valid category."""
        assert "pattern" in VALID_CATEGORIES


class TestRalphUpdateMemory:
    """Tests for ralph_update_memory tool."""

    @pytest.mark.asyncio
    async def test_valid_replace_mode(self) -> None:
        """Replace mode updates memory successfully."""
        mock_tools = MagicMock()
        mock_tools.update_memory.return_value = ToolResult(
            success=True,
            content="Memory update queued (replace mode, 100 chars)",
            data={"mode": "replace", "length": 100, "queued": True},
        )

        with patch("ralph.mcp_tools._ralph_tools", mock_tools):
            result = await ralph_update_memory.handler(
                {"content": "New memory content", "mode": "replace"}
            )

        assert "content" in result
        assert "is_error" not in result
        mock_tools.update_memory.assert_called_once_with(
            content="New memory content", mode="replace"
        )

    @pytest.mark.asyncio
    async def test_valid_append_mode(self) -> None:
        """Append mode updates memory successfully."""
        mock_tools = MagicMock()
        mock_tools.update_memory.return_value = ToolResult(
            success=True,
            content="Memory update queued (append mode, 50 chars)",
            data={"mode": "append", "length": 50, "queued": True},
        )

        with patch("ralph.mcp_tools._ralph_tools", mock_tools):
            result = await ralph_update_memory.handler(
                {"content": "Additional memory", "mode": "append"}
            )

        assert "content" in result
        assert "is_error" not in result
        mock_tools.update_memory.assert_called_once_with(
            content="Additional memory", mode="append"
        )

    @pytest.mark.asyncio
    async def test_content_length_limit(self) -> None:
        """Content exceeding limit is rejected."""
        long_content = "a" * (MAX_MEMORY_CONTENT_LENGTH + 1)
        result = await ralph_update_memory.handler(
            {"content": long_content, "mode": "replace"}
        )
        assert "is_error" in result
        assert "too long" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_invalid_mode_rejected(self) -> None:
        """Invalid mode values are rejected."""
        result = await ralph_update_memory.handler(
            {"content": "Some content", "mode": "invalid"}
        )
        assert "is_error" in result
        assert "must be one of" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_empty_content_rejected(self) -> None:
        """Empty content is rejected."""
        result = await ralph_update_memory.handler(
            {"content": "", "mode": "append"}
        )
        assert "is_error" in result
        assert "cannot be empty" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_whitespace_only_content_rejected(self) -> None:
        """Whitespace-only content is rejected."""
        result = await ralph_update_memory.handler(
            {"content": "   ", "mode": "append"}
        )
        assert "is_error" in result
        assert "cannot be empty" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_non_string_content_rejected(self) -> None:
        """Non-string content is rejected."""
        result = await ralph_update_memory.handler(
            {"content": 123, "mode": "append"}
        )
        assert "is_error" in result
        assert "must be a string" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_max_length_content_accepted(self) -> None:
        """Content at max length is accepted."""
        mock_tools = MagicMock()
        mock_tools.update_memory.return_value = ToolResult(
            success=True,
            content=f"Memory update queued (replace mode, {MAX_MEMORY_CONTENT_LENGTH} chars)",
            data={"mode": "replace", "length": MAX_MEMORY_CONTENT_LENGTH, "queued": True},
        )

        max_content = "a" * MAX_MEMORY_CONTENT_LENGTH
        with patch("ralph.mcp_tools._ralph_tools", mock_tools):
            result = await ralph_update_memory.handler(
                {"content": max_content, "mode": "replace"}
            )

        assert "content" in result
        assert "is_error" not in result


class TestMemoryConstants:
    """Tests for memory-related constants."""

    def test_memory_content_max_length_reasonable(self) -> None:
        """Memory content max length is reasonable."""
        assert MAX_MEMORY_CONTENT_LENGTH >= 1000
        assert MAX_MEMORY_CONTENT_LENGTH <= 100_000

    def test_valid_memory_modes_not_empty(self) -> None:
        """Valid memory modes set is not empty."""
        assert len(VALID_MEMORY_MODES) > 0

    def test_append_is_valid_mode(self) -> None:
        """Append is a valid memory mode."""
        assert "append" in VALID_MEMORY_MODES

    def test_replace_is_valid_mode(self) -> None:
        """Replace is a valid memory mode."""
        assert "replace" in VALID_MEMORY_MODES
