"""Tests for template loading and rendering."""

import pytest

from ralph.templates import (
    get_template_path,
    load_template,
    render_template,
)


class TestGetTemplatePath:
    """Tests for get_template_path."""

    def test_returns_path_for_existing_template(self) -> None:
        """Returns path for existing template."""
        path = get_template_path("PROMPT_build")
        assert path.exists()
        assert path.name == "PROMPT_build.md"

    def test_raises_for_nonexistent_template(self) -> None:
        """Raises FileNotFoundError for nonexistent template."""
        with pytest.raises(FileNotFoundError):
            get_template_path("nonexistent_template")


class TestLoadTemplate:
    """Tests for load_template."""

    def test_loads_template_content(self) -> None:
        """Loads template content."""
        content = load_template("PROMPT_build")
        assert "Ralph Build Phase" in content
        assert "{project_root}" in content

    def test_loads_agents_template(self) -> None:
        """Loads AGENTS template."""
        content = load_template("AGENTS")
        assert "Agent Architecture" in content


class TestRenderTemplate:
    """Tests for render_template."""

    def test_substitutes_variables(self) -> None:
        """Substitutes variables in template."""
        content = render_template(
            "PROMPT_build",
            project_root="/test/path",
            project_name="test-project",
            iteration=5,
            session_id="abc123",
            usage_percentage="50.0",
            task_id="task-1",
            task_description="Test task",
            task_priority=1,
            retry_count=0,
            verification_criteria=["Test passes"],
            dependencies=["task-0"],
            backpressure_commands=["uv run pytest"],
        )

        assert "/test/path" in content
        assert "test-project" in content
        assert "task-1" in content
        assert "Test task" in content

    def test_handles_list_values(self) -> None:
        """Handles list values correctly."""
        content = render_template(
            "PROMPT_build",
            project_root="/test/path",
            project_name="test",
            iteration=1,
            session_id="test",
            usage_percentage="50.0",
            task_id="task-1",
            task_description="Test",
            task_priority=1,
            retry_count=0,
            verification_criteria=["Criterion 1", "Criterion 2"],
            dependencies=[],
            backpressure_commands=["cmd1", "cmd2"],
        )

        assert "Criterion 1" in content
        assert "Criterion 2" in content
        assert "cmd1" in content

    def test_handles_none_values(self) -> None:
        """Handles None values."""
        content = render_template(
            "PROMPT_build",
            project_root="/test",
            project_name="test",
            iteration=1,
            session_id=None,
            usage_percentage="50.0",
            task_id="task-1",
            task_description="Test",
            task_priority=1,
            retry_count=0,
            verification_criteria=[],
            dependencies=[],
            backpressure_commands=[],
        )

        assert "(none)" in content
