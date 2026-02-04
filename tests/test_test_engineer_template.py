"""Tests for test engineer subagent template and factory function."""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    from jinja2 import Environment, FileSystemLoader
    HAS_JINJA2 = True
except ImportError:
    HAS_JINJA2 = False

from ralph.subagents import create_test_engineer_agent, get_test_engineer_prompt


class TestTestEngineerTemplate:
    """Test test engineer template structure and content."""

    def test_test_engineer_template_exists(self):
        """Test that test_engineer.jinja template exists."""
        templates_dir = Path(__file__).parent.parent / "src" / "ralph" / "templates"
        template_file = templates_dir / "subagents" / "test_engineer.jinja"

        assert template_file.exists(), "test_engineer.jinja template should exist"
        assert template_file.is_file(), "test_engineer.jinja should be a file"

    def test_test_engineer_template_structure(self):
        """Test that test engineer template contains all required sections."""
        templates_dir = Path(__file__).parent.parent / "src" / "ralph" / "templates"
        template_file = templates_dir / "subagents" / "test_engineer.jinja"

        # Read template content
        content = template_file.read_text()

        # Check for required sections
        required_sections = [
            "## Your Mission",  # Mission statement
            "## Available Tools",  # Available tools section
            "### Test Strategy Overview",  # Test strategy section
            "### Coverage Analysis",  # Coverage analysis section
            "### Test Recommendations",  # Test recommendations section
            "### Quality Assessment",  # Quality assessment section
            "## Important Constraints",  # Constraints section
        ]

        for section in required_sections:
            assert section in content, f"Template should contain '{section}' section"

    @pytest.mark.skipif(not HAS_JINJA2, reason="jinja2 not installed")
    def test_test_engineer_template_renders(self):
        """Test that the template can be successfully rendered with configuration."""
        templates_dir = Path(__file__).parent.parent / "src" / "ralph" / "templates"
        subagents_dir = templates_dir / "subagents"

        # Create Jinja2 environment
        env = Environment(loader=FileSystemLoader(str(subagents_dir)))
        template = env.get_template("test_engineer.jinja")

        # Test data for rendering
        test_config = {
            "role_name": "Test Engineer",
            "mission_statement": "Develop comprehensive test strategies and ensure quality",
            "allowed_tools": ["Read", "Grep", "Glob"],
            "tool_descriptions": {
                "Read": "Read file contents",
                "Grep": "Search file contents with regex",
                "Glob": "Find files by pattern"
            },
            "focus_areas": ["test strategy", "coverage analysis", "quality validation"],
            "time_limit_minutes": 10
        }

        # Should render without error
        rendered = template.render(**test_config)

        # Basic sanity checks
        assert "Test Engineer" in rendered
        assert "Develop comprehensive test strategies" in rendered
        assert "Test Strategy Overview" in rendered
        assert "Coverage Analysis" in rendered
        assert "Test Recommendations" in rendered
        assert "Quality Assessment" in rendered


class TestTestEngineerFactoryFunction:
    """Test test engineer factory function."""

    def test_get_test_engineer_prompt_function_exists(self):
        """Test that get_test_engineer_prompt function exists and is callable."""
        # Should be able to import and call the function
        prompt = get_test_engineer_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_create_test_engineer_agent_function_exists(self):
        """Test that create_test_engineer_agent function exists and returns AgentDefinition."""
        from claude_agent_sdk import AgentDefinition

        # Should be able to import and call the function
        agent = create_test_engineer_agent()
        assert isinstance(agent, AgentDefinition)
        assert agent.description is not None
        assert agent.prompt is not None
        assert agent.tools is not None

    def test_test_engineer_agent_has_correct_tools(self):
        """Test that test engineer agent has the expected read-only tools."""
        agent = create_test_engineer_agent()

        # Should have read-only tools only
        expected_tools = ["Read", "Grep", "Glob"]
        assert agent.tools == expected_tools

    def test_test_engineer_agent_description(self):
        """Test that test engineer agent has appropriate description."""
        agent = create_test_engineer_agent()

        # Description should mention testing and strategy
        description = agent.description.lower()
        assert "test" in description
        assert any(word in description for word in ["engineer", "strategy", "quality"])
