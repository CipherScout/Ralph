"""Tests for state cleanup module."""

from __future__ import annotations

from pathlib import Path

import pytest

from ralph.cleanup import (
    CleanupResult,
    cleanup_state_files,
    get_cleanup_targets,
)
from ralph.persistence import initialize_plan, initialize_state


class TestCleanupResult:
    """Tests for CleanupResult dataclass."""

    def test_success_with_no_errors(self) -> None:
        """Success is True when no errors."""
        result = CleanupResult(files_deleted=["a.json"])
        assert result.success is True

    def test_success_false_with_errors(self) -> None:
        """Success is False when errors present."""
        result = CleanupResult(errors=["Permission denied"])
        assert result.success is False

    def test_any_cleaned_true_when_files_deleted(self) -> None:
        """any_cleaned is True when files deleted."""
        result = CleanupResult(files_deleted=["state.json"])
        assert result.any_cleaned is True

    def test_any_cleaned_false_when_empty(self) -> None:
        """any_cleaned is False when no files deleted."""
        result = CleanupResult()
        assert result.any_cleaned is False

    def test_default_values(self) -> None:
        """Default values are empty lists."""
        result = CleanupResult()
        assert result.files_deleted == []
        assert result.files_skipped == []
        assert result.errors == []


class TestGetCleanupTargets:
    """Tests for get_cleanup_targets function."""

    def test_includes_core_state_files(self, tmp_path: Path) -> None:
        """Core state files always included."""
        targets = get_cleanup_targets(tmp_path, include_memory=False)
        target_strs = [str(t) for t in targets]

        assert any("state.json" in t for t in target_strs)
        assert any("implementation_plan.json" in t for t in target_strs)
        assert any("injections.json" in t for t in target_strs)

    def test_excludes_memory_by_default(self, tmp_path: Path) -> None:
        """Memory files excluded by default."""
        targets = get_cleanup_targets(tmp_path, include_memory=False)
        target_strs = [str(t) for t in targets]

        assert not any("MEMORY.md" in t for t in target_strs)
        # Check for memory directory (ends with /memory or \\memory)
        assert not any(t.endswith("memory") for t in target_strs)

    def test_includes_memory_when_requested(self, tmp_path: Path) -> None:
        """Memory files included when requested."""
        targets = get_cleanup_targets(tmp_path, include_memory=True)
        target_strs = [str(t) for t in targets]

        assert any("MEMORY.md" in t for t in target_strs)
        # Check for memory directory
        assert any(t.endswith("memory") for t in target_strs)

    def test_does_not_include_config(self, tmp_path: Path) -> None:
        """Config file never included in cleanup targets."""
        targets = get_cleanup_targets(tmp_path, include_memory=True)
        target_strs = [str(t) for t in targets]

        assert not any("config.yaml" in t for t in target_strs)


class TestCleanupStateFiles:
    """Tests for cleanup_state_files function."""

    def test_deletes_existing_state_file(self, tmp_path: Path) -> None:
        """Deletes state.json when it exists."""
        initialize_state(tmp_path)
        assert (tmp_path / ".ralph" / "state.json").exists()

        result = cleanup_state_files(tmp_path)

        assert not (tmp_path / ".ralph" / "state.json").exists()
        assert any("state.json" in f for f in result.files_deleted)

    def test_deletes_existing_plan_file(self, tmp_path: Path) -> None:
        """Deletes implementation_plan.json when it exists."""
        initialize_plan(tmp_path)
        assert (tmp_path / ".ralph" / "implementation_plan.json").exists()

        result = cleanup_state_files(tmp_path)

        assert not (tmp_path / ".ralph" / "implementation_plan.json").exists()
        assert any("implementation_plan.json" in f for f in result.files_deleted)

    def test_skips_nonexistent_files(self, tmp_path: Path) -> None:
        """Skips files that don't exist without error."""
        (tmp_path / ".ralph").mkdir(parents=True, exist_ok=True)

        result = cleanup_state_files(tmp_path)

        assert result.success is True
        assert len(result.errors) == 0

    def test_preserves_config_file(self, tmp_path: Path) -> None:
        """Does not delete config.yaml."""
        ralph_dir = tmp_path / ".ralph"
        ralph_dir.mkdir(parents=True, exist_ok=True)
        config_path = ralph_dir / "config.yaml"
        config_path.write_text("project:\n  name: test")

        result = cleanup_state_files(tmp_path)

        assert config_path.exists()
        assert "config.yaml" not in str(result.files_deleted)

    def test_deletes_memory_when_requested(self, tmp_path: Path) -> None:
        """Deletes MEMORY.md when include_memory=True."""
        ralph_dir = tmp_path / ".ralph"
        ralph_dir.mkdir(parents=True, exist_ok=True)
        memory_path = ralph_dir / "MEMORY.md"
        memory_path.write_text("# Memory\nSome content")

        result = cleanup_state_files(tmp_path, include_memory=True)

        assert not memory_path.exists()
        assert any("MEMORY.md" in f for f in result.files_deleted)

    def test_preserves_memory_by_default(self, tmp_path: Path) -> None:
        """Preserves MEMORY.md by default."""
        ralph_dir = tmp_path / ".ralph"
        ralph_dir.mkdir(parents=True, exist_ok=True)
        memory_path = ralph_dir / "MEMORY.md"
        memory_path.write_text("# Memory\nSome content")

        result = cleanup_state_files(tmp_path, include_memory=False)

        assert memory_path.exists()
        assert not any("MEMORY.md" in f for f in result.files_deleted)

    def test_deletes_memory_directory(self, tmp_path: Path) -> None:
        """Deletes memory/ directory when include_memory=True."""
        memory_dir = tmp_path / ".ralph" / "memory" / "iterations"
        memory_dir.mkdir(parents=True, exist_ok=True)
        (memory_dir / "iter-001.md").write_text("# Iteration 1")

        result = cleanup_state_files(tmp_path, include_memory=True)

        assert not (tmp_path / ".ralph" / "memory").exists()
        assert any("memory" in f for f in result.files_deleted)

    def test_deletes_injections_file(self, tmp_path: Path) -> None:
        """Deletes injections.json when it exists."""
        ralph_dir = tmp_path / ".ralph"
        ralph_dir.mkdir(parents=True, exist_ok=True)
        injections_path = ralph_dir / "injections.json"
        injections_path.write_text('{"content": "test"}')

        result = cleanup_state_files(tmp_path)

        assert not injections_path.exists()
        assert any("injections.json" in f for f in result.files_deleted)

    def test_skipped_files_tracked(self, tmp_path: Path) -> None:
        """Files that don't exist are tracked in files_skipped."""
        (tmp_path / ".ralph").mkdir(parents=True, exist_ok=True)

        result = cleanup_state_files(tmp_path)

        # All targets should be in skipped since none exist
        assert len(result.files_skipped) > 0


class TestCleanupIntegration:
    """Integration tests for full cleanup flow."""

    def test_full_cleanup_workflow(self, tmp_path: Path) -> None:
        """Test complete cleanup of typical Ralph state."""
        # Setup typical Ralph state
        initialize_state(tmp_path)
        initialize_plan(tmp_path)

        ralph_dir = tmp_path / ".ralph"
        (ralph_dir / "MEMORY.md").write_text("# Memory")
        (ralph_dir / "injections.json").write_text("{}")
        (ralph_dir / "config.yaml").write_text("project:\n  name: test")

        memory_dir = ralph_dir / "memory" / "iterations"
        memory_dir.mkdir(parents=True, exist_ok=True)
        (memory_dir / "iter-001.md").write_text("# Iteration")

        (tmp_path / "progress.txt").write_text("Learnings")

        # Execute cleanup with memory
        result = cleanup_state_files(tmp_path, include_memory=True)

        # Verify cleanup
        assert result.success
        assert not (ralph_dir / "state.json").exists()
        assert not (ralph_dir / "implementation_plan.json").exists()
        assert not (ralph_dir / "MEMORY.md").exists()
        assert not (ralph_dir / "injections.json").exists()
        assert not (ralph_dir / "memory").exists()

        # Config preserved
        assert (ralph_dir / "config.yaml").exists()

    def test_cleanup_without_memory_preserves_memory(self, tmp_path: Path) -> None:
        """Test cleanup without memory flag preserves memory files."""
        # Setup
        initialize_state(tmp_path)
        ralph_dir = tmp_path / ".ralph"
        (ralph_dir / "MEMORY.md").write_text("# Memory")

        memory_dir = ralph_dir / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        (memory_dir / "test.md").write_text("# Test")

        # Execute cleanup without memory
        result = cleanup_state_files(tmp_path, include_memory=False)

        # Verify state cleaned but memory preserved
        assert result.success
        assert not (ralph_dir / "state.json").exists()
        assert (ralph_dir / "MEMORY.md").exists()
        assert (ralph_dir / "memory").exists()

    def test_cleanup_idempotent(self, tmp_path: Path) -> None:
        """Running cleanup twice should not error."""
        initialize_state(tmp_path)

        # First cleanup
        result1 = cleanup_state_files(tmp_path)
        assert result1.success
        assert result1.any_cleaned

        # Second cleanup - should succeed with nothing to clean
        result2 = cleanup_state_files(tmp_path)
        assert result2.success
        assert not result2.any_cleaned

    def test_ralph_dir_preserved(self, tmp_path: Path) -> None:
        """The .ralph directory itself should be preserved after cleanup."""
        initialize_state(tmp_path)
        ralph_dir = tmp_path / ".ralph"

        result = cleanup_state_files(tmp_path)

        assert result.success
        assert ralph_dir.exists()
