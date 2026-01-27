"""Tests for memory persistence and management."""

from __future__ import annotations

from pathlib import Path

from ralph.models import RalphState
from ralph.persistence import (
    load_memory,
    load_state,
    memory_exists,
    save_memory,
    save_state,
)


class TestMemoryPersistence:
    """Tests for memory file persistence."""

    def test_load_memory_returns_none_if_missing(self, tmp_path: Path) -> None:
        """load_memory returns None if file doesn't exist."""
        result = load_memory(tmp_path)
        assert result is None

    def test_save_and_load_memory_roundtrip(self, tmp_path: Path) -> None:
        """Memory is preserved through save/load cycle."""
        content = "## Session Memory\n\nSome important context from previous session."

        save_memory(content, tmp_path)
        loaded = load_memory(tmp_path)

        assert loaded == content

    def test_save_memory_creates_ralph_dir(self, tmp_path: Path) -> None:
        """save_memory creates .ralph directory if needed."""
        save_memory("Test content", tmp_path)

        ralph_dir = tmp_path / ".ralph"
        assert ralph_dir.exists()
        assert ralph_dir.is_dir()

    def test_memory_exists_returns_false_if_missing(self, tmp_path: Path) -> None:
        """memory_exists returns False if file doesn't exist."""
        assert memory_exists(tmp_path) is False

    def test_memory_exists_returns_true_if_exists(self, tmp_path: Path) -> None:
        """memory_exists returns True if file exists."""
        save_memory("Content", tmp_path)
        assert memory_exists(tmp_path) is True

    def test_save_memory_overwrites_existing(self, tmp_path: Path) -> None:
        """save_memory overwrites existing content."""
        save_memory("First content", tmp_path)
        save_memory("Second content", tmp_path)

        loaded = load_memory(tmp_path)
        assert loaded == "Second content"

    def test_memory_file_path_is_correct(self, tmp_path: Path) -> None:
        """Memory file is saved at .ralph/MEMORY.md."""
        save_memory("Test", tmp_path)

        memory_path = tmp_path / ".ralph" / "MEMORY.md"
        assert memory_path.exists()
        assert memory_path.read_text() == "Test"


class TestPendingMemoryUpdate:
    """Tests for pending memory update state."""

    def test_pending_memory_update_serialized(self, tmp_path: Path) -> None:
        """pending_memory_update is properly serialized and deserialized."""
        state = RalphState(project_root=tmp_path)
        state.pending_memory_update = {
            "content": "Memory content to save",
            "mode": "replace",
            "timestamp": "2025-01-27T12:00:00",
        }

        save_state(state, tmp_path)
        loaded = load_state(tmp_path)

        assert loaded.pending_memory_update is not None
        assert loaded.pending_memory_update["content"] == "Memory content to save"
        assert loaded.pending_memory_update["mode"] == "replace"

    def test_pending_memory_update_defaults_to_none(self, tmp_path: Path) -> None:
        """pending_memory_update defaults to None."""
        state = RalphState(project_root=tmp_path)
        save_state(state, tmp_path)
        loaded = load_state(tmp_path)

        assert loaded.pending_memory_update is None

    def test_pending_memory_update_cleared(self, tmp_path: Path) -> None:
        """pending_memory_update can be cleared."""
        state = RalphState(project_root=tmp_path)
        state.pending_memory_update = {"content": "Test", "mode": "append"}
        save_state(state, tmp_path)

        # Clear it
        state.pending_memory_update = None
        save_state(state, tmp_path)

        loaded = load_state(tmp_path)
        assert loaded.pending_memory_update is None


class TestMemoryFlush:
    """Tests for memory flush functionality in executors."""

    def test_flush_pending_memory_append(self, tmp_path: Path) -> None:
        """Pending memory in append mode adds to existing content."""
        # Set up existing memory
        existing_content = "## Existing Memory\n\nSome prior context."
        save_memory(existing_content, tmp_path)

        # Create state with pending update
        state = RalphState(project_root=tmp_path)
        state.pending_memory_update = {
            "content": "New information to add.",
            "mode": "append",
        }
        save_state(state, tmp_path)

        # Simulate flush operation
        update = state.pending_memory_update
        content = update["content"]
        mode = update["mode"]

        if mode == "append":
            existing = load_memory(tmp_path) or ""
            if existing:
                content = f"{existing}\n\n---\n\n{content}"

        save_memory(content, tmp_path)

        # Verify result
        final_content = load_memory(tmp_path)
        assert existing_content in final_content
        assert "New information to add." in final_content
        assert "---" in final_content

    def test_flush_pending_memory_replace(self, tmp_path: Path) -> None:
        """Pending memory in replace mode overwrites existing content."""
        # Set up existing memory
        save_memory("Old content that should be replaced.", tmp_path)

        # Create state with pending update
        state = RalphState(project_root=tmp_path)
        state.pending_memory_update = {
            "content": "Brand new content.",
            "mode": "replace",
        }
        save_state(state, tmp_path)

        # Simulate flush operation
        update = state.pending_memory_update
        content = update["content"]
        mode = update["mode"]

        if mode == "append":
            existing = load_memory(tmp_path) or ""
            if existing:
                content = f"{existing}\n\n---\n\n{content}"

        save_memory(content, tmp_path)

        # Verify result
        final_content = load_memory(tmp_path)
        assert final_content == "Brand new content."
        assert "Old content" not in final_content

    def test_flush_with_no_existing_memory(self, tmp_path: Path) -> None:
        """Append mode works when no existing memory exists."""
        state = RalphState(project_root=tmp_path)
        state.pending_memory_update = {
            "content": "First memory entry.",
            "mode": "append",
        }
        save_state(state, tmp_path)

        # Simulate flush
        update = state.pending_memory_update
        content = update["content"]
        mode = update["mode"]

        if mode == "append":
            existing = load_memory(tmp_path) or ""
            if existing:
                content = f"{existing}\n\n---\n\n{content}"

        save_memory(content, tmp_path)

        # Verify result
        final_content = load_memory(tmp_path)
        assert final_content == "First memory entry."
