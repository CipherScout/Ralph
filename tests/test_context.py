"""Tests for context management and hand-off protocol."""

from datetime import datetime
from pathlib import Path

import pytest

from ralph.context import (
    ContextInjection,
    IterationContext,
    add_injection,
    archive_session,
    build_iteration_context,
    clear_injections,
    execute_context_handoff,
    generate_memory_content,
    load_injections,
    load_memory_file,
    load_progress_file,
    load_session_history,
    should_trigger_handoff,
    write_memory_file,
)
from ralph.models import ImplementationPlan, Phase, RalphState, Task, TaskStatus
from ralph.persistence import initialize_plan, initialize_state, save_plan


@pytest.fixture
def project_path(tmp_path: Path) -> Path:
    """Create an initialized project directory."""
    initialize_state(tmp_path)
    initialize_plan(tmp_path)
    return tmp_path


@pytest.fixture
def state(project_path: Path) -> RalphState:
    """Create a test state."""
    return RalphState(
        project_root=project_path,
        iteration_count=5,
        session_id="test-session",
        session_cost_usd=0.50,
        session_tokens_used=25000,
        tasks_completed_this_session=2,
    )


@pytest.fixture
def plan_with_tasks(project_path: Path) -> ImplementationPlan:
    """Create a plan with tasks."""
    plan = ImplementationPlan(
        tasks=[
            Task(
                id="task-1",
                description="Completed task",
                priority=1,
                status=TaskStatus.COMPLETE,
                completed_at=datetime.now(),
            ),
            Task(
                id="task-2",
                description="In progress task",
                priority=2,
                status=TaskStatus.IN_PROGRESS,
            ),
            Task(
                id="task-3",
                description="Pending task",
                priority=3,
                status=TaskStatus.PENDING,
            ),
        ]
    )
    save_plan(plan, project_path)
    return plan


class TestLoadMemoryFile:
    """Tests for load_memory_file."""

    def test_returns_none_when_missing(self, project_path: Path) -> None:
        """Returns None when MEMORY.md doesn't exist."""
        result = load_memory_file(project_path)
        assert result is None

    def test_loads_existing_memory(self, project_path: Path) -> None:
        """Loads existing .ralph/MEMORY.md content."""
        ralph_dir = project_path / ".ralph"
        ralph_dir.mkdir(parents=True, exist_ok=True)
        memory_path = ralph_dir / "MEMORY.md"
        memory_path.write_text("# Session Memory\n\nTest content")

        result = load_memory_file(project_path)
        assert result is not None
        assert "Test content" in result


class TestLoadProgressFile:
    """Tests for load_progress_file."""

    def test_returns_empty_when_missing(self, project_path: Path) -> None:
        """Returns empty list when progress.txt doesn't exist."""
        result = load_progress_file(project_path)
        assert result == []

    def test_loads_progress_entries(self, project_path: Path) -> None:
        """Loads progress entries."""
        progress_path = project_path / "progress.txt"
        progress_path.write_text(
            "[2025-01-15] PATTERN: Test pattern\n"
            "[2025-01-15] DEBUG: Test debug\n"
        )

        result = load_progress_file(project_path)
        assert len(result) == 2
        assert "PATTERN" in result[0]

    def test_limits_entries(self, project_path: Path) -> None:
        """Limits entries to max_entries."""
        progress_path = project_path / "progress.txt"
        lines = [f"[2025-01-15] Entry {i}" for i in range(30)]
        progress_path.write_text("\n".join(lines))

        result = load_progress_file(project_path, max_entries=10)
        assert len(result) == 10
        # Should be most recent entries
        assert "Entry 29" in result[-1]


class TestInjections:
    """Tests for context injections."""

    def test_add_and_load_injection(self, project_path: Path) -> None:
        """Can add and load injections."""
        add_injection(project_path, "Focus on task A", source="user")

        injections = load_injections(project_path)
        assert len(injections) == 1
        assert injections[0].content == "Focus on task A"
        assert injections[0].source == "user"

    def test_multiple_injections(self, project_path: Path) -> None:
        """Multiple injections are preserved."""
        add_injection(project_path, "First injection", source="user")
        add_injection(project_path, "Second injection", source="system")

        injections = load_injections(project_path)
        assert len(injections) == 2

    def test_injections_sorted_by_priority(self, project_path: Path) -> None:
        """Injections are sorted by priority."""
        add_injection(project_path, "Low priority", source="user", priority=0)
        add_injection(project_path, "High priority", source="system", priority=10)

        injections = load_injections(project_path)
        assert injections[0].content == "High priority"
        assert injections[1].content == "Low priority"

    def test_clear_injections(self, project_path: Path) -> None:
        """Clear removes all injections."""
        add_injection(project_path, "Test injection", source="user")
        clear_injections(project_path)

        injections = load_injections(project_path)
        assert len(injections) == 0

    def test_load_empty_returns_empty(self, project_path: Path) -> None:
        """Loading when no injections returns empty list."""
        injections = load_injections(project_path)
        assert injections == []


class TestBuildIterationContext:
    """Tests for build_iteration_context."""

    def test_builds_complete_context(
        self, state: RalphState, plan_with_tasks: ImplementationPlan, project_path: Path
    ) -> None:
        """Builds complete iteration context."""
        context = build_iteration_context(state, plan_with_tasks, project_path)

        assert context.iteration == 5
        assert context.phase == Phase.BUILDING
        assert context.session_id == "test-session"
        assert context.completed_tasks_this_session == 2

    def test_includes_current_task(
        self, state: RalphState, plan_with_tasks: ImplementationPlan, project_path: Path
    ) -> None:
        """Includes current/next task information."""
        context = build_iteration_context(state, plan_with_tasks, project_path)

        # Should have the pending task as next
        assert context.current_task is not None
        assert context.current_task["id"] == "task-3"

    def test_calculates_usage_percentage(
        self, state: RalphState, plan_with_tasks: ImplementationPlan, project_path: Path
    ) -> None:
        """Calculates context usage percentage."""
        state.context_budget.add_usage(100_000)
        context = build_iteration_context(state, plan_with_tasks, project_path)

        assert context.usage_percentage == 50.0  # 100k / 200k

    def test_includes_injections(
        self, state: RalphState, plan_with_tasks: ImplementationPlan, project_path: Path
    ) -> None:
        """Includes pending injections."""
        add_injection(project_path, "Test injection", source="user")

        context = build_iteration_context(state, plan_with_tasks, project_path)
        assert len(context.injections) == 1
        assert context.injections[0].content == "Test injection"


class TestGenerateMemoryContent:
    """Tests for generate_memory_content."""

    def test_generates_valid_markdown(
        self, state: RalphState, plan_with_tasks: ImplementationPlan, project_path: Path
    ) -> None:
        """Generates valid markdown content."""
        content = generate_memory_content(state, plan_with_tasks, project_path)

        assert "# Session Memory" in content
        assert "## Completed This Session" in content
        assert "## Current Task In Progress" in content
        assert "## Session Metadata" in content

    def test_includes_completed_tasks(
        self, state: RalphState, plan_with_tasks: ImplementationPlan, project_path: Path
    ) -> None:
        """Includes completed tasks."""
        content = generate_memory_content(state, plan_with_tasks, project_path)
        assert "Completed task" in content

    def test_includes_in_progress_task(
        self, state: RalphState, plan_with_tasks: ImplementationPlan, project_path: Path
    ) -> None:
        """Includes in-progress task."""
        content = generate_memory_content(state, plan_with_tasks, project_path)
        assert "In progress task" in content

    def test_includes_session_metadata(
        self, state: RalphState, plan_with_tasks: ImplementationPlan, project_path: Path
    ) -> None:
        """Includes session metadata."""
        content = generate_memory_content(state, plan_with_tasks, project_path)
        assert "Phase: building" in content
        assert "Iteration: 5" in content
        assert "$0.5000" in content

    def test_includes_custom_sections(
        self, state: RalphState, plan_with_tasks: ImplementationPlan, project_path: Path
    ) -> None:
        """Includes custom sections when provided."""
        content = generate_memory_content(
            state,
            plan_with_tasks,
            project_path,
            files_modified=["src/main.py", "tests/test_main.py"],
            architectural_decisions=["Using JWT for auth"],
            blockers=["Missing API key"],
            notes_for_next=["Add rate limiting"],
        )

        assert "src/main.py" in content
        assert "Using JWT for auth" in content
        assert "Missing API key" in content
        assert "Add rate limiting" in content

    def test_includes_llm_summary(
        self, state: RalphState, plan_with_tasks: ImplementationPlan, project_path: Path
    ) -> None:
        """Includes LLM summary when provided."""
        content = generate_memory_content(
            state,
            plan_with_tasks,
            project_path,
            session_summary="Made great progress on authentication.",
        )

        assert "LLM Session Summary" in content
        assert "Made great progress" in content


class TestWriteMemoryFile:
    """Tests for write_memory_file."""

    def test_writes_memory_file(self, project_path: Path) -> None:
        """Writes MEMORY.md file."""
        content = "# Test Memory\n\nTest content"
        path = write_memory_file(content, project_path)

        assert path.exists()
        assert path.name == "MEMORY.md"
        assert path.read_text() == content


class TestArchiveSession:
    """Tests for archive_session."""

    def test_archives_session(self, state: RalphState, project_path: Path) -> None:
        """Archives session to history."""
        path = archive_session(state, "context_budget", project_path)

        assert path.exists()
        assert "sessions.jsonl" in str(path)

    def test_appends_to_history(self, state: RalphState, project_path: Path) -> None:
        """Archives append to history file."""
        archive_session(state, "reason1", project_path)
        archive_session(state, "reason2", project_path)

        history_file = project_path / ".ralph" / "session_history" / "sessions.jsonl"
        lines = history_file.read_text().strip().split("\n")
        assert len(lines) == 2


class TestLoadSessionHistory:
    """Tests for load_session_history."""

    def test_loads_session_history(self, state: RalphState, project_path: Path) -> None:
        """Loads session history."""
        archive_session(state, "test_reason", project_path)

        history = load_session_history(project_path)
        assert len(history) == 1
        assert history[0].handoff_reason == "test_reason"

    def test_returns_most_recent_first(self, state: RalphState, project_path: Path) -> None:
        """Returns sessions in reverse chronological order."""
        state.iteration_count = 1
        archive_session(state, "first", project_path)
        state.iteration_count = 2
        archive_session(state, "second", project_path)

        history = load_session_history(project_path)
        assert history[0].handoff_reason == "second"
        assert history[1].handoff_reason == "first"

    def test_respects_limit(self, state: RalphState, project_path: Path) -> None:
        """Respects limit parameter."""
        for i in range(5):
            state.iteration_count = i
            archive_session(state, f"reason-{i}", project_path)

        history = load_session_history(project_path, limit=3)
        assert len(history) == 3

    def test_empty_when_no_history(self, project_path: Path) -> None:
        """Returns empty list when no history."""
        history = load_session_history(project_path)
        assert history == []


class TestExecuteContextHandoff:
    """Tests for execute_context_handoff."""

    def test_successful_handoff(
        self, state: RalphState, plan_with_tasks: ImplementationPlan, project_path: Path
    ) -> None:
        """Executes successful handoff."""
        result = execute_context_handoff(
            state, plan_with_tasks, project_path, "context_budget"
        )

        assert result.success is True
        assert result.memory_path is not None
        assert result.memory_path.exists()
        assert result.archive_path is not None
        assert result.next_session_id is not None

    def test_clears_injections_after_handoff(
        self, state: RalphState, plan_with_tasks: ImplementationPlan, project_path: Path
    ) -> None:
        """Clears injections after handoff."""
        add_injection(project_path, "Test injection", source="user")

        execute_context_handoff(state, plan_with_tasks, project_path, "test")

        injections = load_injections(project_path)
        assert len(injections) == 0

    def test_includes_custom_content(
        self, state: RalphState, plan_with_tasks: ImplementationPlan, project_path: Path
    ) -> None:
        """Includes custom content in memory."""
        result = execute_context_handoff(
            state,
            plan_with_tasks,
            project_path,
            "test",
            session_summary="Great session!",
            files_modified=["file1.py"],
        )

        assert result.success is True
        memory_content = result.memory_path.read_text()
        assert "Great session!" in memory_content
        assert "file1.py" in memory_content


class TestShouldTriggerHandoff:
    """Tests for should_trigger_handoff."""

    def test_triggers_at_threshold(self, project_path: Path) -> None:
        """Triggers at context budget threshold (80% per SPEC-005)."""
        state = RalphState(project_root=project_path)
        state.context_budget.add_usage(160_001)  # > 80% (SPEC-005 threshold)

        should_trigger, reason = should_trigger_handoff(state)
        assert should_trigger is True
        assert reason == "context_budget_threshold"

    def test_triggers_at_warning_level(self, project_path: Path) -> None:
        """Triggers at warning level (75%)."""
        state = RalphState(project_root=project_path)
        state.context_budget.add_usage(150_001)  # > 75%

        should_trigger, reason = should_trigger_handoff(state)
        assert should_trigger is True
        # Either threshold or warning is valid
        assert reason in ["context_budget_threshold", "context_budget_warning"]

    def test_no_trigger_below_threshold(self, project_path: Path) -> None:
        """No trigger below threshold."""
        state = RalphState(project_root=project_path)
        state.context_budget.add_usage(100_000)  # 50%

        should_trigger, reason = should_trigger_handoff(state)
        assert should_trigger is False
        assert reason is None


class TestContextInjection:
    """Tests for ContextInjection dataclass."""

    def test_default_values(self) -> None:
        """Has correct default values."""
        injection = ContextInjection(
            timestamp=datetime.now(),
            content="Test",
            source="user",
        )
        assert injection.priority == 0


class TestIterationContext:
    """Tests for IterationContext dataclass."""

    def test_contains_all_fields(self) -> None:
        """Contains all necessary fields."""
        context = IterationContext(
            iteration=1,
            phase=Phase.BUILDING,
            session_id="test",
            current_task=None,
            completed_tasks_this_session=0,
            total_completed_tasks=0,
            total_pending_tasks=5,
            memory_content=None,
            progress_learnings=[],
            injections=[],
            remaining_tokens=100_000,
            usage_percentage=50.0,
        )

        assert context.iteration == 1
        assert context.phase == Phase.BUILDING
        assert context.remaining_tokens == 100_000
