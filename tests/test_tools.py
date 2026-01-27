"""Tests for custom MCP tools."""

from pathlib import Path

import pytest

from ralph.models import ImplementationPlan, Task, TaskStatus
from ralph.persistence import (
    initialize_plan,
    initialize_state,
    load_plan,
    save_plan,
)
from ralph.tools import (
    TOOL_DEFINITIONS,
    RalphTools,
    ToolResult,
    create_tools,
)


@pytest.fixture
def project_path(tmp_path: Path) -> Path:
    """Create an initialized project directory."""
    initialize_state(tmp_path)
    initialize_plan(tmp_path)
    return tmp_path


@pytest.fixture
def tools(project_path: Path) -> RalphTools:
    """Create tools for the project."""
    return create_tools(project_path)


@pytest.fixture
def populated_plan(project_path: Path) -> ImplementationPlan:
    """Create a plan with tasks."""
    plan = load_plan(project_path)
    plan.tasks = [
        Task(
            id="task-1",
            description="First task",
            priority=1,
            verification_criteria=["Tests pass"],
        ),
        Task(
            id="task-2",
            description="Second task",
            priority=2,
            dependencies=["task-1"],
        ),
        Task(
            id="task-3",
            description="Third task",
            priority=3,
            dependencies=["task-1", "task-2"],
        ),
    ]
    save_plan(plan, project_path)
    return plan


class TestToolResult:
    """Tests for ToolResult."""

    def test_success_result(self) -> None:
        """Success result has correct attributes."""
        result = ToolResult(success=True, content="Done", data={"key": "value"})
        assert result.success is True
        assert result.content == "Done"
        assert result.data == {"key": "value"}
        assert result.error is None

    def test_failure_result(self) -> None:
        """Failure result has error."""
        result = ToolResult(success=False, content="Failed", error="Something broke")
        assert result.success is False
        assert result.error == "Something broke"


class TestGetNextTask:
    """Tests for get_next_task tool."""

    def test_empty_plan_returns_no_task(self, tools: RalphTools) -> None:
        """Empty plan has no next task."""
        result = tools.get_next_task()
        assert result.success is True
        assert result.data["task"] is None
        assert "No tasks available" in result.content

    def test_returns_highest_priority_task(
        self, tools: RalphTools, populated_plan: ImplementationPlan
    ) -> None:
        """Returns highest priority available task."""
        result = tools.get_next_task()
        assert result.success is True
        assert result.data["task"]["id"] == "task-1"
        assert result.data["task"]["priority"] == 1

    def test_respects_dependencies(
        self, tools: RalphTools, project_path: Path, populated_plan: ImplementationPlan
    ) -> None:
        """Only returns tasks with met dependencies."""
        # Complete task-1
        plan = load_plan(project_path)
        plan.mark_task_complete("task-1")
        save_plan(plan, project_path)

        result = tools.get_next_task()
        assert result.success is True
        assert result.data["task"]["id"] == "task-2"

    def test_returns_remaining_count(
        self, tools: RalphTools, populated_plan: ImplementationPlan
    ) -> None:
        """Result includes remaining task count."""
        result = tools.get_next_task()
        assert result.data["remaining_count"] == 3


class TestMarkTaskComplete:
    """Tests for mark_task_complete tool."""

    def test_completes_existing_task(
        self, tools: RalphTools, populated_plan: ImplementationPlan, project_path: Path
    ) -> None:
        """Can complete an existing task."""
        result = tools.mark_task_complete("task-1", "All tests pass", 25000)

        assert result.success is True
        assert "task-1" in result.content
        assert result.data["task_id"] == "task-1"

        # Verify state
        plan = load_plan(project_path)
        task = plan.get_task_by_id("task-1")
        assert task.status == TaskStatus.COMPLETE
        assert task.completion_notes == "All tests pass"
        assert task.actual_tokens_used == 25000

    def test_fails_for_nonexistent_task(self, tools: RalphTools) -> None:
        """Fails for nonexistent task."""
        result = tools.mark_task_complete("nonexistent")
        assert result.success is False
        assert "not found" in result.content.lower()

    def test_handles_already_complete(
        self, tools: RalphTools, populated_plan: ImplementationPlan, project_path: Path
    ) -> None:
        """Handles already complete task."""
        plan = load_plan(project_path)
        plan.mark_task_complete("task-1")
        save_plan(plan, project_path)

        result = tools.mark_task_complete("task-1")
        assert result.success is True
        assert result.data["was_already_complete"] is True

    def test_returns_completion_percentage(
        self, tools: RalphTools, populated_plan: ImplementationPlan
    ) -> None:
        """Result includes completion percentage."""
        result = tools.mark_task_complete("task-1")
        assert "completion_percentage" in result.data
        assert result.data["completion_percentage"] > 0


class TestMarkTaskBlocked:
    """Tests for mark_task_blocked tool."""

    def test_blocks_existing_task(
        self, tools: RalphTools, populated_plan: ImplementationPlan, project_path: Path
    ) -> None:
        """Can block an existing task."""
        result = tools.mark_task_blocked("task-1", "Missing API key")

        assert result.success is True
        assert "blocked" in result.content.lower()

        plan = load_plan(project_path)
        task = plan.get_task_by_id("task-1")
        assert task.status == TaskStatus.BLOCKED
        assert "Missing API key" in task.completion_notes

    def test_fails_for_nonexistent_task(self, tools: RalphTools) -> None:
        """Fails for nonexistent task."""
        result = tools.mark_task_blocked("nonexistent", "reason")
        assert result.success is False

    def test_handles_already_blocked(
        self, tools: RalphTools, populated_plan: ImplementationPlan, project_path: Path
    ) -> None:
        """Handles already blocked task."""
        plan = load_plan(project_path)
        plan.mark_task_blocked("task-1", "original reason")
        save_plan(plan, project_path)

        result = tools.mark_task_blocked("task-1", "new reason")
        assert result.success is True
        assert result.data["was_already_blocked"] is True


class TestMarkTaskInProgress:
    """Tests for mark_task_in_progress tool."""

    def test_starts_pending_task(
        self, tools: RalphTools, populated_plan: ImplementationPlan, project_path: Path
    ) -> None:
        """Can start a pending task."""
        result = tools.mark_task_in_progress("task-1")

        assert result.success is True
        assert result.data["status"] == "in_progress"

        plan = load_plan(project_path)
        task = plan.get_task_by_id("task-1")
        assert task.status == TaskStatus.IN_PROGRESS

    def test_fails_for_complete_task(
        self, tools: RalphTools, populated_plan: ImplementationPlan, project_path: Path
    ) -> None:
        """Cannot start already complete task."""
        plan = load_plan(project_path)
        plan.mark_task_complete("task-1")
        save_plan(plan, project_path)

        result = tools.mark_task_in_progress("task-1")
        assert result.success is False
        assert "cannot be started" in result.content.lower()


class TestIncrementRetry:
    """Tests for increment_retry tool."""

    def test_increments_retry_count(
        self, tools: RalphTools, populated_plan: ImplementationPlan, project_path: Path
    ) -> None:
        """Increments retry count."""
        result = tools.increment_retry("task-1")
        assert result.success is True
        assert result.data["retry_count"] == 1

        result = tools.increment_retry("task-1")
        assert result.data["retry_count"] == 2

    def test_resets_status_to_pending(
        self, tools: RalphTools, populated_plan: ImplementationPlan, project_path: Path
    ) -> None:
        """Resets status to pending."""
        tools.mark_task_in_progress("task-1")
        tools.increment_retry("task-1")

        plan = load_plan(project_path)
        task = plan.get_task_by_id("task-1")
        assert task.status == TaskStatus.PENDING


class TestGetPlanSummary:
    """Tests for get_plan_summary tool."""

    def test_returns_plan_summary(
        self, tools: RalphTools, populated_plan: ImplementationPlan
    ) -> None:
        """Returns plan summary."""
        result = tools.get_plan_summary()

        assert result.success is True
        assert result.data["total_tasks"] == 3
        assert result.data["pending"] == 3
        assert result.data["complete"] == 0
        assert "next_task" in result.data

    def test_empty_plan_summary(self, tools: RalphTools) -> None:
        """Handles empty plan."""
        result = tools.get_plan_summary()

        assert result.success is True
        assert result.data["total_tasks"] == 0
        assert "next_task" not in result.data


class TestGetStateSummary:
    """Tests for get_state_summary tool."""

    def test_returns_state_summary(self, tools: RalphTools) -> None:
        """Returns state summary."""
        result = tools.get_state_summary()

        assert result.success is True
        assert "phase" in result.data
        assert "iteration" in result.data
        assert "circuit_breaker" in result.data
        assert result.data["should_halt"] is False


class TestAddTask:
    """Tests for add_task tool."""

    def test_adds_new_task(self, tools: RalphTools, project_path: Path) -> None:
        """Can add a new task."""
        result = tools.add_task(
            task_id="new-task",
            description="New task description",
            priority=1,
            verification_criteria=["Test passes"],
        )

        assert result.success is True
        assert result.data["task_id"] == "new-task"

        plan = load_plan(project_path)
        task = plan.get_task_by_id("new-task")
        assert task is not None
        assert task.description == "New task description"
        assert task.priority == 1
        assert task.verification_criteria == ["Test passes"]

    def test_rejects_duplicate_id(
        self, tools: RalphTools, populated_plan: ImplementationPlan
    ) -> None:
        """Rejects duplicate task ID."""
        result = tools.add_task("task-1", "Duplicate", 1)

        assert result.success is False
        assert "already exists" in result.content.lower()

    def test_validates_dependencies(
        self, tools: RalphTools, populated_plan: ImplementationPlan
    ) -> None:
        """Validates that dependencies exist."""
        result = tools.add_task(
            task_id="new-task",
            description="New task",
            priority=1,
            dependencies=["nonexistent"],
        )

        assert result.success is False
        assert "not found" in result.content.lower()

    def test_adds_task_with_dependencies(
        self, tools: RalphTools, populated_plan: ImplementationPlan, project_path: Path
    ) -> None:
        """Can add task with valid dependencies."""
        result = tools.add_task(
            task_id="task-4",
            description="Fourth task",
            priority=4,
            dependencies=["task-1"],
        )

        assert result.success is True

        plan = load_plan(project_path)
        task = plan.get_task_by_id("task-4")
        assert task.dependencies == ["task-1"]


class TestToolDefinitions:
    """Tests for tool definitions."""

    def test_all_tools_defined(self) -> None:
        """All tools have definitions."""
        tool_names = [t["name"] for t in TOOL_DEFINITIONS]
        expected = [
            "ralph_get_next_task",
            "ralph_mark_task_complete",
            "ralph_mark_task_blocked",
            "ralph_get_plan_summary",
            "ralph_get_state_summary",
            "ralph_add_task",
        ]
        for name in expected:
            assert name in tool_names, f"Missing tool definition: {name}"

    def test_definitions_have_required_fields(self) -> None:
        """Tool definitions have required fields."""
        for tool in TOOL_DEFINITIONS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert "properties" in tool["input_schema"]
            assert "required" in tool["input_schema"]


class TestCreateTools:
    """Tests for create_tools factory."""

    def test_creates_tools_instance(self, project_path: Path) -> None:
        """Creates RalphTools instance."""
        tools = create_tools(project_path)
        assert isinstance(tools, RalphTools)
        assert tools.project_root == project_path


class TestSignalPhaseComplete:
    """Tests for signal_phase_complete method."""

    def test_signals_discovery_complete(self, tools: RalphTools, project_path: Path) -> None:
        """Can signal discovery phase is complete."""
        result = tools.signal_phase_complete(
            phase="discovery",
            summary="Requirements gathered",
            artifacts={"specs_created": ["spec1.md"]},
        )

        assert result.success is True
        assert "discovery" in result.content.lower()
        assert result.data["phase"] == "discovery"
        assert result.data["artifacts"] == {"specs_created": ["spec1.md"]}

    def test_signals_planning_complete(self, tools: RalphTools, project_path: Path) -> None:
        """Can signal planning phase is complete."""
        result = tools.signal_phase_complete(
            phase="planning",
            summary="Plan created with 5 tasks",
            artifacts={"task_count": 5},
        )

        assert result.success is True
        assert "planning" in result.content.lower()
        assert result.data["phase"] == "planning"

    def test_signals_building_complete(self, tools: RalphTools, project_path: Path) -> None:
        """Can signal building phase is complete."""
        result = tools.signal_phase_complete(
            phase="building",
            summary="All tasks implemented",
            artifacts={"tasks_completed": 5},
        )

        assert result.success is True
        assert "building" in result.content.lower()

    def test_signals_validation_complete(self, tools: RalphTools, project_path: Path) -> None:
        """Can signal validation phase is complete."""
        result = tools.signal_phase_complete(
            phase="validation",
            summary="All tests pass",
            artifacts={"passed": True, "issues": []},
        )

        assert result.success is True
        assert "validation" in result.content.lower()

    def test_rejects_invalid_phase(self, tools: RalphTools) -> None:
        """Rejects invalid phase names."""
        result = tools.signal_phase_complete(
            phase="invalid_phase",
            summary="Test",
        )

        assert result.success is False
        assert "invalid phase" in result.content.lower()

    def test_signal_phase_complete_is_class_method(self) -> None:
        """Verify signal_phase_complete is a method of RalphTools class."""
        assert hasattr(RalphTools, "signal_phase_complete")
        assert callable(RalphTools.signal_phase_complete)
