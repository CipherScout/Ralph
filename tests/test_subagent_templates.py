"""Tests for subagent prompt templates."""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    from jinja2 import Environment, FileSystemLoader
    HAS_JINJA2 = True
except ImportError:
    HAS_JINJA2 = False


class TestSubagentTemplates:
    """Test subagent template structure and content."""

    def test_subagent_directory_exists(self):
        """Test that the subagents template directory exists."""
        templates_dir = Path(__file__).parent.parent / "src" / "ralph" / "templates"
        subagents_dir = templates_dir / "subagents"

        assert subagents_dir.exists(), "src/ralph/templates/subagents/ directory should exist"
        assert subagents_dir.is_dir(), "subagents should be a directory"

    def test_research_specialist_template_exists(self):
        """Test that research_specialist.jinja template exists."""
        templates_dir = Path(__file__).parent.parent / "src" / "ralph" / "templates"
        template_file = templates_dir / "subagents" / "research_specialist.jinja"

        assert template_file.exists(), "research_specialist.jinja template should exist"
        assert template_file.is_file(), "research_specialist.jinja should be a file"

    def test_research_specialist_template_structure(self):
        """Test that research specialist template contains all required sections."""
        templates_dir = Path(__file__).parent.parent / "src" / "ralph" / "templates"
        template_file = templates_dir / "subagents" / "research_specialist.jinja"

        # Read template content
        content = template_file.read_text()

        # Check for required sections
        required_sections = [
            "## Your Mission",  # Mission statement
            "## Available Tools",  # Available tools section
            "### Executive Summary",  # Report format - Executive Summary
            "### Detailed Analysis",  # Report format - Detailed Analysis
            "### Recommendations",  # Report format - Recommendations
            "### Confidence Assessment",  # Report format - Confidence Assessment
            "## Important Constraints",  # Constraints section
        ]

        for section in required_sections:
            assert section in content, f"Template should contain '{section}' section"

    def test_research_specialist_template_jinja_syntax(self):
        """Test that research specialist template uses Jinja2 syntax for customization."""
        templates_dir = Path(__file__).parent.parent / "src" / "ralph" / "templates"
        template_file = templates_dir / "subagents" / "research_specialist.jinja"

        # Read template content
        content = template_file.read_text()

        # Check for Jinja2 variables and control structures
        jinja_elements = [
            "{{",  # Variable start
            "}}",  # Variable end
            "{%",  # Control structure start
            "%}",  # Control structure end
        ]

        for element in jinja_elements:
            assert element in content, f"Template should contain Jinja2 syntax: '{element}'"

    @pytest.mark.skipif(not HAS_JINJA2, reason="jinja2 not installed")
    def test_research_specialist_template_renders(self):
        """Test that the template can be successfully rendered with configuration."""
        templates_dir = Path(__file__).parent.parent / "src" / "ralph" / "templates"
        subagents_dir = templates_dir / "subagents"

        # Create Jinja2 environment
        env = Environment(loader=FileSystemLoader(str(subagents_dir)))
        template = env.get_template("research_specialist.jinja")

        # Test data for rendering
        test_config = {
            "role_name": "Research Specialist",
            "mission_statement": "Conduct deep technical analysis and research",
            "allowed_tools": ["Read", "Grep", "Glob", "WebSearch", "WebFetch"],
            "tool_descriptions": {
                "Read": "Read file contents",
                "Grep": "Search file contents with regex",
                "Glob": "Find files by pattern",
                "WebSearch": "Search the web for information",
                "WebFetch": "Fetch content from URLs"
            },
            "focus_areas": ["technology evaluation", "pattern research", "best practices"],
            "time_limit_minutes": 5
        }

        # Should render without error
        rendered = template.render(**test_config)

        # Basic sanity checks
        assert "Research Specialist" in rendered
        assert "Conduct deep technical analysis" in rendered
        assert "Executive Summary" in rendered
        assert "Detailed Analysis" in rendered
        assert "Recommendations" in rendered
        assert "Confidence Assessment" in rendered

    @pytest.mark.skipif(not HAS_JINJA2, reason="jinja2 not installed")
    def test_research_specialist_template_tools_section(self):
        """Test that the tools section properly iterates through available tools."""
        templates_dir = Path(__file__).parent.parent / "src" / "ralph" / "templates"
        subagents_dir = templates_dir / "subagents"

        env = Environment(loader=FileSystemLoader(str(subagents_dir)))
        template = env.get_template("research_specialist.jinja")

        test_config = {
            "role_name": "Research Specialist",
            "mission_statement": "Test mission",
            "allowed_tools": ["Read", "WebSearch"],
            "tool_descriptions": {
                "Read": "Read files",
                "WebSearch": "Search web"
            },
            "focus_areas": ["testing"],
            "time_limit_minutes": 5
        }

        rendered = template.render(**test_config)

        # Should contain both tools with proper formatting
        assert "**Read**: Read files" in rendered
        assert "**WebSearch**: Search web" in rendered

    @pytest.mark.skipif(not HAS_JINJA2, reason="jinja2 not installed")
    def test_research_specialist_template_focus_areas(self):
        """Test that focus areas are properly joined in the constraints section."""
        templates_dir = Path(__file__).parent.parent / "src" / "ralph" / "templates"
        subagents_dir = templates_dir / "subagents"

        env = Environment(loader=FileSystemLoader(str(subagents_dir)))
        template = env.get_template("research_specialist.jinja")

        test_config = {
            "role_name": "Research Specialist",
            "mission_statement": "Test mission",
            "allowed_tools": ["Read"],
            "tool_descriptions": {"Read": "Read files"},
            "focus_areas": ["area1", "area2", "area3"],
            "time_limit_minutes": 5
        }

        rendered = template.render(**test_config)

        # Should contain joined focus areas
        assert "area1, area2, area3" in rendered

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
            "### Test Strategy Overview",  # Test strategy framework
            "### Coverage Analysis",  # Coverage analysis section
            "### Test Recommendations",  # Test prioritization patterns
            "### Quality Assessment",  # Quality assessment
            "## Important Constraints",  # Constraints section
        ]

        for section in required_sections:
            assert section in content, f"Template should contain '{section}' section"

        # Check for test engineer specific content
        test_specific_content = [
            "edge case", "boundary condition", "test prioritization",
            "coverage analysis", "quality intelligence"
        ]

        content_lower = content.lower()
        for term in test_specific_content:
            assert term in content_lower, f"Template should contain test engineering term: '{term}'"

    @pytest.mark.skipif(not HAS_JINJA2, reason="jinja2 not installed")
    def test_test_engineer_template_renders(self):
        """Test that the test engineer template can be successfully rendered with configuration."""
        templates_dir = Path(__file__).parent.parent / "src" / "ralph" / "templates"
        subagents_dir = templates_dir / "subagents"

        # Create Jinja2 environment
        env = Environment(loader=FileSystemLoader(str(subagents_dir)))
        template = env.get_template("test_engineer.jinja")

        # Test data for rendering
        test_config = {
            "role_name": "Test Engineer",
            "mission_statement": (
                "Develop comprehensive test strategies"
                " and ensure quality coverage"
            ),
            "allowed_tools": ["Read", "Grep", "Glob"],
            "tool_descriptions": {
                "Read": "Read file contents for test strategy development",
                "Grep": "Search for existing tests and patterns",
                "Glob": "Find test files and testing configuration",
            },
            "focus_areas": [
                "test strategy development",
                "coverage analysis",
                "edge case identification",
            ],
            "time_limit_minutes": 10
        }

        # Should render without error
        rendered = template.render(**test_config)

        # Basic sanity checks
        assert "Test Engineer" in rendered
        assert "test strategies" in rendered
        assert "Test Strategy Overview" in rendered
        assert "Coverage Analysis" in rendered
        assert "Test Recommendations" in rendered
        assert "Quality Assessment" in rendered
