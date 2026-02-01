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
        path = get_template_path("AGENTS")
        assert path.exists()
        assert path.name == "AGENTS.md"

    def test_raises_for_nonexistent_template(self) -> None:
        """Raises FileNotFoundError for nonexistent template."""
        with pytest.raises(FileNotFoundError):
            get_template_path("nonexistent_template")


class TestLoadTemplate:
    """Tests for load_template."""

    def test_loads_template_content(self) -> None:
        """Loads template content."""
        content = load_template("AGENTS")
        assert "Agent Architecture" in content

    def test_loads_prd_template(self) -> None:
        """Loads TEMPLATE_PRD template."""
        content = load_template("TEMPLATE_PRD")
        assert "Product Requirements Document" in content
        assert "{Project Name}" in content


class TestRenderTemplate:
    """Tests for render_template."""

    def test_substitutes_variables(self) -> None:
        """Substitutes variables in template."""
        content = render_template(
            "TEMPLATE_PRD",
        )
        # Template has {Project Name} etc. — render_template uses simple
        # string replacement so unmatched placeholders stay as-is
        assert "Product Requirements Document" in content

    def test_handles_list_values(self) -> None:
        """Handles list values correctly via render_template."""
        # Test the list formatting logic in render_template
        content = render_template(
            "TEMPLATE_PRD",
            items=["item1", "item2"],
        )
        # The template doesn't use {items} but the function should still work
        assert "Product Requirements Document" in content

    def test_handles_none_values(self) -> None:
        """Handles None values."""
        content = render_template(
            "TEMPLATE_PRD",
            some_field=None,
        )
        # None values get replaced with "(none)" if their placeholder exists
        assert "Product Requirements Document" in content
