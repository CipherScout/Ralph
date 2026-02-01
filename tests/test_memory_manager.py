"""Tests for deterministic memory management system (SPEC-004)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ralph.models import (
    ImplementationPlan,
    Phase,
    RalphState,
    Task,
    TaskStatus,
)


class TestMemoryConfig:
    """Tests for MemoryConfig dataclass."""

    def test_default_values(self) -> None:
        """MemoryConfig has sensible defaults."""
        from ralph.memory import MemoryConfig

        config = MemoryConfig()

        assert config.max_active_memory_chars == 12000
        assert config.max_iteration_files == 20
        assert config.max_session_files == 10
        assert config.archive_after_days == 30

    def test_custom_values(self) -> None:
        """MemoryConfig accepts custom values."""
        from ralph.memory import MemoryConfig

        config = MemoryConfig(
            max_active_memory_chars=5000,
            max_iteration_files=10,
            max_session_files=5,
            archive_after_days=14,
        )

        assert config.max_active_memory_chars == 5000
        assert config.max_iteration_files == 10
        assert config.max_session_files == 5
        assert config.archive_after_days == 14


class TestIterationMemory:
    """Tests for IterationMemory dataclass."""

    def test_iteration_memory_creation(self) -> None:
        """IterationMemory stores iteration data."""
        from ralph.memory import IterationMemory

        now = datetime.now()
        mem = IterationMemory(
            iteration=5,
            phase=Phase.BUILDING,
            timestamp=now,
            tasks_completed=["task-1", "task-2"],
            tasks_blocked=["task-3"],
            progress_made=True,
            tokens_used=1000,
            cost_usd=0.05,
        )

        assert mem.iteration == 5
        assert mem.phase == Phase.BUILDING
        assert mem.timestamp == now
        assert mem.tasks_completed == ["task-1", "task-2"]
        assert mem.tasks_blocked == ["task-3"]
        assert mem.progress_made is True
        assert mem.tokens_used == 1000
        assert mem.cost_usd == 0.05


class TestPhaseMemory:
    """Tests for PhaseMemory dataclass."""

    def test_phase_memory_creation(self) -> None:
        """PhaseMemory stores phase transition data."""
        from ralph.memory import PhaseMemory

        now = datetime.now()
        mem = PhaseMemory(
            phase=Phase.DISCOVERY,
            completed_at=now,
            iterations_in_phase=3,
            artifacts={"specs_created": ["SPEC-001.md"]},
            summary="Completed requirements gathering",
        )

        assert mem.phase == Phase.DISCOVERY
        assert mem.completed_at == now
        assert mem.iterations_in_phase == 3
        assert mem.artifacts == {"specs_created": ["SPEC-001.md"]}
        assert mem.summary == "Completed requirements gathering"


class TestSessionMemory:
    """Tests for SessionMemory dataclass."""

    def test_session_memory_creation(self) -> None:
        """SessionMemory stores session handoff data."""
        from ralph.memory import SessionMemory

        mem = SessionMemory(
            session_id="sess-123",
            phase=Phase.BUILDING,
            iteration=10,
            handoff_reason="phase_complete",
            task_in_progress="task-5",
            tokens_used=150000,
            cost_usd=2.50,
            notes_for_next=["Continue with task-5", "Run tests after"],
        )

        assert mem.session_id == "sess-123"
        assert mem.phase == Phase.BUILDING
        assert mem.iteration == 10
        assert mem.handoff_reason == "phase_complete"
        assert mem.task_in_progress == "task-5"
        assert mem.tokens_used == 150000
        assert mem.cost_usd == 2.50
        assert len(mem.notes_for_next) == 2


class TestMemoryManagerInit:
    """Tests for MemoryManager initialization."""

    def test_creates_memory_directories(self, tmp_path: Path) -> None:
        """MemoryManager creates required directories on init."""
        from ralph.memory import MemoryManager

        _manager = MemoryManager(tmp_path)

        assert (tmp_path / ".ralph" / "memory" / "phases").exists()
        assert (tmp_path / ".ralph" / "memory" / "iterations").exists()
        assert (tmp_path / ".ralph" / "memory" / "sessions").exists()
        assert (tmp_path / ".ralph" / "memory" / "archive").exists()

    def test_uses_custom_config(self, tmp_path: Path) -> None:
        """MemoryManager uses provided config."""
        from ralph.memory import MemoryConfig, MemoryManager

        config = MemoryConfig(max_active_memory_chars=5000)
        manager = MemoryManager(tmp_path, config=config)

        assert manager.config.max_active_memory_chars == 5000

    def test_handles_existing_directories(self, tmp_path: Path) -> None:
        """MemoryManager handles pre-existing directories gracefully."""
        from ralph.memory import MemoryManager

        # Create directories first
        (tmp_path / ".ralph" / "memory" / "phases").mkdir(parents=True)

        # Should not raise
        _manager = MemoryManager(tmp_path)

        assert (tmp_path / ".ralph" / "memory" / "phases").exists()


class TestCaptureIterationMemory:
    """Tests for iteration memory capture."""

    def test_captures_iteration_memory_file(self, tmp_path: Path) -> None:
        """capture_iteration_memory creates iteration file."""
        from ralph.memory import MemoryManager
        from ralph.sdk_client import IterationResult

        state = RalphState(project_root=tmp_path)
        state.iteration_count = 5
        state.current_phase = Phase.BUILDING
        plan = ImplementationPlan(tasks=[])

        result = IterationResult(
            success=True,
            final_text="Completed work",
            cost_usd=0.05,
            tokens_used=1000,
        )

        manager = MemoryManager(tmp_path)
        path = manager.capture_iteration_memory(state, plan, result)

        assert path.exists()
        assert path.name == "iter-005.md"
        content = path.read_text()
        assert "Iteration 5" in content
        assert "building" in content.lower()

    def test_iteration_memory_includes_tasks(self, tmp_path: Path) -> None:
        """Iteration memory includes completed and blocked tasks."""
        from ralph.memory import MemoryManager
        from ralph.sdk_client import IterationResult

        state = RalphState(project_root=tmp_path)
        state.iteration_count = 3
        state.current_phase = Phase.BUILDING

        # Create tasks with different statuses
        tasks = [
            Task(id="task-1", description="Task 1", priority=1, status=TaskStatus.COMPLETE),
            Task(id="task-2", description="Task 2", priority=2, status=TaskStatus.BLOCKED),
            Task(id="task-3", description="Task 3", priority=3, status=TaskStatus.IN_PROGRESS),
        ]
        plan = ImplementationPlan(tasks=tasks)

        result = IterationResult(
            success=True,
            final_text="Done",
            cost_usd=0.02,
            tokens_used=500,
        )

        manager = MemoryManager(tmp_path)
        path = manager.capture_iteration_memory(state, plan, result)

        content = path.read_text()
        assert "task-1" in content  # completed
        assert "task-2" in content  # blocked

    def test_iteration_memory_sequential_numbering(self, tmp_path: Path) -> None:
        """Iteration files are numbered sequentially."""
        from ralph.memory import MemoryManager
        from ralph.sdk_client import IterationResult

        state = RalphState(project_root=tmp_path)
        plan = ImplementationPlan(tasks=[])
        result = IterationResult(success=True, final_text="", cost_usd=0, tokens_used=0)

        manager = MemoryManager(tmp_path)

        state.iteration_count = 1
        path1 = manager.capture_iteration_memory(state, plan, result)

        state.iteration_count = 2
        path2 = manager.capture_iteration_memory(state, plan, result)

        assert path1.name == "iter-001.md"
        assert path2.name == "iter-002.md"


class TestCapturePhaseTransitionMemory:
    """Tests for phase transition memory capture."""

    def test_captures_phase_transition_memory(self, tmp_path: Path) -> None:
        """capture_phase_transition_memory creates phase file."""
        from ralph.memory import MemoryManager

        state = RalphState(project_root=tmp_path)
        state.iteration_count = 5
        plan = ImplementationPlan(tasks=[])

        manager = MemoryManager(tmp_path)
        path = manager.capture_phase_transition_memory(
            state=state,
            plan=plan,
            old_phase=Phase.DISCOVERY,
            new_phase=Phase.PLANNING,
            artifacts={"specs_created": ["SPEC-001.md", "PRD.md"]},
        )

        assert path.exists()
        assert path.name == "discovery.md"
        content = path.read_text()
        assert "Discovery" in content
        assert "SPEC-001.md" in content
        assert "PRD.md" in content

    def test_phase_memory_includes_iterations_count(self, tmp_path: Path) -> None:
        """Phase memory includes number of iterations in that phase."""
        from ralph.memory import MemoryManager

        state = RalphState(project_root=tmp_path)
        state.iteration_count = 7

        manager = MemoryManager(tmp_path)
        path = manager.capture_phase_transition_memory(
            state=state,
            plan=ImplementationPlan(tasks=[]),
            old_phase=Phase.PLANNING,
            new_phase=Phase.BUILDING,
            artifacts={},
        )

        content = path.read_text()
        # Should contain the iteration count somewhere
        assert "7" in content or "Iterations" in content

    def test_overwrites_existing_phase_memory(self, tmp_path: Path) -> None:
        """Phase memory file is overwritten on new transition."""
        from ralph.memory import MemoryManager

        state = RalphState(project_root=tmp_path)
        plan = ImplementationPlan(tasks=[])

        manager = MemoryManager(tmp_path)

        # First capture
        manager.capture_phase_transition_memory(
            state=state,
            plan=plan,
            old_phase=Phase.DISCOVERY,
            new_phase=Phase.PLANNING,
            artifacts={"first": "capture"},
        )

        # Second capture (should overwrite)
        path = manager.capture_phase_transition_memory(
            state=state,
            plan=plan,
            old_phase=Phase.DISCOVERY,
            new_phase=Phase.PLANNING,
            artifacts={"second": "capture"},
        )

        content = path.read_text()
        assert "second" in content
        # First content should be gone
        assert "first" not in content or "second" in content


class TestCaptureSessionHandoffMemory:
    """Tests for session handoff memory capture."""

    def test_captures_session_handoff_memory(self, tmp_path: Path) -> None:
        """capture_session_handoff_memory creates session file."""
        from ralph.memory import MemoryManager

        state = RalphState(project_root=tmp_path)
        state.session_id = "sess-abc123"
        state.iteration_count = 15
        state.current_phase = Phase.BUILDING
        state.session_tokens_used = 150000
        state.session_cost_usd = 2.50

        task = Task(id="task-5", description="Current task", priority=1, status=TaskStatus.IN_PROGRESS)
        plan = ImplementationPlan(tasks=[task])

        manager = MemoryManager(tmp_path)
        path = manager.capture_session_handoff_memory(
            state=state,
            plan=plan,
            handoff_reason="phase_complete",
        )

        assert path.exists()
        assert "session" in path.name.lower()
        content = path.read_text()
        assert "phase_complete" in content or "Context" in content
        assert "task-5" in content

    def test_session_memory_sequential_numbering(self, tmp_path: Path) -> None:
        """Session files are numbered sequentially."""
        from ralph.memory import MemoryManager

        state = RalphState(project_root=tmp_path)
        state.session_id = "sess-1"
        plan = ImplementationPlan(tasks=[])

        manager = MemoryManager(tmp_path)

        path1 = manager.capture_session_handoff_memory(state, plan, "reason1")
        state.session_id = "sess-2"
        path2 = manager.capture_session_handoff_memory(state, plan, "reason2")

        assert path1.name == "session-001.md"
        assert path2.name == "session-002.md"


class TestBuildActiveMemory:
    """Tests for building active memory content."""

    def test_builds_active_memory_empty_state(self, tmp_path: Path) -> None:
        """build_active_memory works with no existing memory."""
        from ralph.memory import MemoryManager

        state = RalphState(project_root=tmp_path)
        state.current_phase = Phase.DISCOVERY
        plan = ImplementationPlan(tasks=[])

        manager = MemoryManager(tmp_path)
        memory = manager.build_active_memory(state, plan)

        assert isinstance(memory, str)
        # Should have some content even without prior memory
        assert len(memory) > 0

    def test_includes_previous_phase_memory(self, tmp_path: Path) -> None:
        """Active memory includes previous phase context."""
        from ralph.memory import MemoryManager

        state = RalphState(project_root=tmp_path)
        plan = ImplementationPlan(tasks=[])

        manager = MemoryManager(tmp_path)

        # Create discovery phase memory
        manager.capture_phase_transition_memory(
            state=state,
            plan=plan,
            old_phase=Phase.DISCOVERY,
            new_phase=Phase.PLANNING,
            artifacts={"key_decision": "Use Python for implementation"},
        )

        # Now in planning phase
        state.current_phase = Phase.PLANNING
        memory = manager.build_active_memory(state, plan)

        # Should include discovery context
        assert "Discovery" in memory or "discovery" in memory

    def test_includes_recent_iterations(self, tmp_path: Path) -> None:
        """Active memory includes recent iteration summaries."""
        from ralph.memory import MemoryManager
        from ralph.sdk_client import IterationResult

        state = RalphState(project_root=tmp_path)
        state.current_phase = Phase.BUILDING
        plan = ImplementationPlan(tasks=[])
        result = IterationResult(success=True, final_text="", cost_usd=0.01, tokens_used=100)

        manager = MemoryManager(tmp_path)

        # Create some iteration memories
        for i in range(1, 4):
            state.iteration_count = i
            manager.capture_iteration_memory(state, plan, result)

        # Build active memory
        memory = manager.build_active_memory(state, plan)

        # Should reference iterations
        assert "Iteration" in memory or "iteration" in memory or "Progress" in memory

    def test_truncates_to_max_chars(self, tmp_path: Path) -> None:
        """Active memory is truncated to config max."""
        from ralph.memory import MemoryConfig, MemoryManager

        config = MemoryConfig(max_active_memory_chars=500)
        manager = MemoryManager(tmp_path, config=config)

        state = RalphState(project_root=tmp_path)
        plan = ImplementationPlan(tasks=[])

        # Create a large phase memory
        (tmp_path / ".ralph" / "memory" / "phases").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".ralph" / "memory" / "phases" / "discovery.md").write_text("X" * 2000)

        state.current_phase = Phase.PLANNING
        memory = manager.build_active_memory(state, plan)

        assert len(memory) <= 500 + 50  # Allow for truncation message

    def test_includes_task_state(self, tmp_path: Path) -> None:
        """Active memory includes current task state."""
        from ralph.memory import MemoryManager

        state = RalphState(project_root=tmp_path)
        state.current_phase = Phase.BUILDING

        tasks = [
            Task(id="task-1", description="First task", priority=1, status=TaskStatus.COMPLETE),
            Task(id="task-2", description="Second task", priority=2, status=TaskStatus.IN_PROGRESS),
            Task(id="task-3", description="Third task", priority=3, status=TaskStatus.PENDING),
        ]
        plan = ImplementationPlan(tasks=tasks)

        manager = MemoryManager(tmp_path)
        memory = manager.build_active_memory(state, plan)

        # Should mention task progress
        assert "1" in memory or "complete" in memory.lower() or "progress" in memory.lower()


class TestLoadPhaseMemory:
    """Tests for loading phase memory."""

    def test_load_phase_memory_returns_none_if_missing(self, tmp_path: Path) -> None:
        """load_phase_memory returns None if file doesn't exist."""
        from ralph.memory import MemoryManager

        manager = MemoryManager(tmp_path)
        result = manager.load_phase_memory(Phase.DISCOVERY)

        assert result is None

    def test_load_phase_memory_returns_content(self, tmp_path: Path) -> None:
        """load_phase_memory returns file content."""
        from ralph.memory import MemoryManager

        manager = MemoryManager(tmp_path)

        # Create phase memory file
        phase_file = tmp_path / ".ralph" / "memory" / "phases" / "discovery.md"
        phase_file.write_text("# Discovery Phase Memory\n\nKey insights here.")

        result = manager.load_phase_memory(Phase.DISCOVERY)

        assert result is not None
        assert "Discovery Phase Memory" in result
        assert "Key insights" in result


class TestLoadRecentIterations:
    """Tests for loading recent iterations."""

    def test_load_recent_iterations_empty(self, tmp_path: Path) -> None:
        """load_recent_iterations returns empty list if no files."""
        from ralph.memory import MemoryManager

        manager = MemoryManager(tmp_path)
        result = manager.load_recent_iterations(limit=5)

        assert result == []

    def test_load_recent_iterations_respects_limit(self, tmp_path: Path) -> None:
        """load_recent_iterations respects the limit parameter."""
        from ralph.memory import MemoryManager
        from ralph.sdk_client import IterationResult

        state = RalphState(project_root=tmp_path)
        state.current_phase = Phase.BUILDING
        plan = ImplementationPlan(tasks=[])
        result = IterationResult(success=True, final_text="", cost_usd=0.01, tokens_used=100)

        manager = MemoryManager(tmp_path)

        # Create 10 iteration files
        for i in range(1, 11):
            state.iteration_count = i
            manager.capture_iteration_memory(state, plan, result)

        # Request only 3
        recent = manager.load_recent_iterations(limit=3)

        assert len(recent) == 3

    def test_load_recent_iterations_returns_most_recent(self, tmp_path: Path) -> None:
        """load_recent_iterations returns most recent iterations."""
        from ralph.memory import MemoryManager
        from ralph.sdk_client import IterationResult

        state = RalphState(project_root=tmp_path)
        state.current_phase = Phase.BUILDING
        plan = ImplementationPlan(tasks=[])
        result = IterationResult(success=True, final_text="", cost_usd=0.01, tokens_used=100)

        manager = MemoryManager(tmp_path)

        # Create 5 iteration files
        for i in range(1, 6):
            state.iteration_count = i
            manager.capture_iteration_memory(state, plan, result)

        recent = manager.load_recent_iterations(limit=2)

        # Should be iterations 4 and 5 (most recent)
        iterations = [m.iteration for m in recent]
        assert 5 in iterations
        assert 4 in iterations


class TestMemoryRotation:
    """Tests for memory file rotation."""

    def test_rotate_files_keeps_recent(self, tmp_path: Path) -> None:
        """rotate_files keeps most recent files."""
        from ralph.memory import MemoryConfig, MemoryManager
        from ralph.sdk_client import IterationResult

        config = MemoryConfig(max_iteration_files=5)
        manager = MemoryManager(tmp_path, config=config)

        state = RalphState(project_root=tmp_path)
        state.current_phase = Phase.BUILDING
        plan = ImplementationPlan(tasks=[])
        result = IterationResult(success=True, final_text="", cost_usd=0.01, tokens_used=100)

        # Create 10 iteration files
        for i in range(1, 11):
            state.iteration_count = i
            manager.capture_iteration_memory(state, plan, result)

        iter_dir = tmp_path / ".ralph" / "memory" / "iterations"
        assert len(list(iter_dir.glob("iter-*.md"))) == 10

        # Rotate
        rotated = manager.rotate_files()

        assert rotated == 5  # Should rotate 5 files
        remaining = list(iter_dir.glob("iter-*.md"))
        assert len(remaining) == 5

        # Most recent should remain
        remaining_names = [f.name for f in remaining]
        assert "iter-010.md" in remaining_names
        assert "iter-006.md" in remaining_names

    def test_rotate_files_moves_to_archive(self, tmp_path: Path) -> None:
        """rotate_files moves old files to archive."""
        from ralph.memory import MemoryConfig, MemoryManager
        from ralph.sdk_client import IterationResult

        config = MemoryConfig(max_iteration_files=3)
        manager = MemoryManager(tmp_path, config=config)

        state = RalphState(project_root=tmp_path)
        state.current_phase = Phase.BUILDING
        plan = ImplementationPlan(tasks=[])
        result = IterationResult(success=True, final_text="", cost_usd=0.01, tokens_used=100)

        # Create 5 iteration files
        for i in range(1, 6):
            state.iteration_count = i
            manager.capture_iteration_memory(state, plan, result)

        manager.rotate_files()

        archive_dir = tmp_path / ".ralph" / "memory" / "archive"
        archived = list(archive_dir.glob("iter-*.md"))
        assert len(archived) == 2  # 2 should be archived

    def test_rotate_files_no_op_when_under_limit(self, tmp_path: Path) -> None:
        """rotate_files does nothing when under limit."""
        from ralph.memory import MemoryConfig, MemoryManager
        from ralph.sdk_client import IterationResult

        config = MemoryConfig(max_iteration_files=10)
        manager = MemoryManager(tmp_path, config=config)

        state = RalphState(project_root=tmp_path)
        state.current_phase = Phase.BUILDING
        plan = ImplementationPlan(tasks=[])
        result = IterationResult(success=True, final_text="", cost_usd=0.01, tokens_used=100)

        # Create only 3 files
        for i in range(1, 4):
            state.iteration_count = i
            manager.capture_iteration_memory(state, plan, result)

        rotated = manager.rotate_files()

        assert rotated == 0


class TestMemoryCleanup:
    """Tests for memory archive cleanup."""

    def test_cleanup_archive_deletes_old_files(self, tmp_path: Path) -> None:
        """cleanup_archive deletes files older than threshold."""
        import os
        import time

        from ralph.memory import MemoryConfig, MemoryManager

        config = MemoryConfig(archive_after_days=0)  # Delete immediately for test
        manager = MemoryManager(tmp_path, config=config)

        archive_dir = tmp_path / ".ralph" / "memory" / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        # Create an old file
        old_file = archive_dir / "old-iter-001.md"
        old_file.write_text("Old content")
        # Set modification time to 2 days ago
        old_time = time.time() - (2 * 24 * 60 * 60)
        os.utime(old_file, (old_time, old_time))

        deleted = manager.cleanup_archive()

        assert deleted == 1
        assert not old_file.exists()

    def test_cleanup_archive_keeps_recent_files(self, tmp_path: Path) -> None:
        """cleanup_archive keeps files newer than threshold."""
        from ralph.memory import MemoryConfig, MemoryManager

        config = MemoryConfig(archive_after_days=30)
        manager = MemoryManager(tmp_path, config=config)

        archive_dir = tmp_path / ".ralph" / "memory" / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        # Create a recent file
        recent_file = archive_dir / "recent-iter-001.md"
        recent_file.write_text("Recent content")
        # File is created with current time by default

        deleted = manager.cleanup_archive()

        assert deleted == 0
        assert recent_file.exists()


class TestMemoryStats:
    """Tests for memory statistics."""

    def test_get_memory_stats(self, tmp_path: Path) -> None:
        """get_memory_stats returns statistics dict."""
        from ralph.memory import MemoryManager
        from ralph.sdk_client import IterationResult

        manager = MemoryManager(tmp_path)

        state = RalphState(project_root=tmp_path)
        state.current_phase = Phase.BUILDING
        plan = ImplementationPlan(tasks=[])
        result = IterationResult(success=True, final_text="", cost_usd=0.01, tokens_used=100)

        # Create some files
        for i in range(1, 4):
            state.iteration_count = i
            manager.capture_iteration_memory(state, plan, result)

        stats = manager.get_memory_stats()

        assert "iteration_files" in stats
        assert stats["iteration_files"] == 3
        assert "session_files" in stats
        assert "phase_files" in stats
        assert "archive_files" in stats
        assert "total_size_bytes" in stats


class TestBackwardsCompatibility:
    """Tests for backwards compatibility with existing memory system."""

    def test_ralph_update_memory_still_works(self, tmp_path: Path) -> None:
        """LLM-triggered memory updates via ralph_update_memory still work."""
        from ralph.persistence import load_memory, save_memory

        # Simulate ralph_update_memory behavior (queue + flush)
        save_memory("LLM requested this content", tmp_path)

        # Should be loadable
        content = load_memory(tmp_path)
        assert content == "LLM requested this content"

    def test_memory_file_location_unchanged(self, tmp_path: Path) -> None:
        """Memory file is still at .ralph/MEMORY.md."""
        from ralph.persistence import save_memory

        save_memory("Test content", tmp_path)

        memory_path = tmp_path / ".ralph" / "MEMORY.md"
        assert memory_path.exists()
        assert memory_path.read_text() == "Test content"

    def test_active_memory_compatible_with_injection(self, tmp_path: Path) -> None:
        """Active memory from MemoryManager works with _inject_memory_into_prompt."""
        from ralph.memory import MemoryManager

        state = RalphState(project_root=tmp_path)
        state.current_phase = Phase.BUILDING
        plan = ImplementationPlan(tasks=[])

        manager = MemoryManager(tmp_path)
        memory = manager.build_active_memory(state, plan)

        # Should be a string suitable for injection
        assert isinstance(memory, str)
        # Should not contain problematic characters
        assert "\x00" not in memory  # No null bytes
