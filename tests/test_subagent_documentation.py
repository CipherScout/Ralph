"""Tests to verify subagent documentation completeness.

This module tests that the subagent documentation is comprehensive,
up-to-date, and includes all required sections and examples.
"""

from __future__ import annotations

from pathlib import Path

from ralph.models import Phase
from ralph.subagents import SUBAGENT_SECURITY_CONSTRAINTS


class TestSubagentDocumentation:
    """Test that subagent documentation is comprehensive and up-to-date."""

    def test_readme_includes_subagent_section(self) -> None:
        """Test that README.md includes a subagent section."""
        readme_path = Path(__file__).parent.parent / "README.md"
        readme_content = readme_path.read_text()

        # Should include subagent section
        assert "## Subagents" in readme_content or "## Subagent" in readme_content
        assert "subagent" in readme_content.lower()

    def test_subagents_doc_exists_and_comprehensive(self) -> None:
        """Test that docs/subagents.md exists and is comprehensive."""
        docs_path = Path(__file__).parent.parent / "docs" / "subagents.md"
        assert docs_path.exists(), "docs/subagents.md should exist"

        content = docs_path.read_text()

        # Should include all main sections
        assert "# Subagents" in content or "# Ralph Subagents" in content
        assert "## Overview" in content
        assert "## Available Subagents" in content
        assert "## Phase-Specific Availability" in content
        assert "## Security Model" in content
        assert "## Usage Examples" in content
        assert "## Troubleshooting" in content

        # Should include examples
        assert "```" in content  # Code examples should be present
        assert "Task" in content  # Should mention Task tool for invocation

    def test_docs_readme_includes_subagents_link(self) -> None:
        """Test that docs/README.md includes link to subagents documentation."""
        docs_readme_path = Path(__file__).parent.parent / "docs" / "README.md"
        docs_readme_content = docs_readme_path.read_text()

        # Should include reference to subagents documentation
        assert "subagents.md" in docs_readme_content or "subagent" in docs_readme_content.lower()

    def test_all_subagent_types_documented(self) -> None:
        """Test that all configured subagent types are documented."""
        docs_path = Path(__file__).parent.parent / "docs" / "subagents.md"

        if docs_path.exists():  # Only run if docs exist
            content = docs_path.read_text()

            # Get all subagent types from security constraints
            tool_permissions = SUBAGENT_SECURITY_CONSTRAINTS["tool_permissions"]
            assert isinstance(tool_permissions, dict)

            for subagent_type in tool_permissions:
                # Each subagent should be documented
                assert subagent_type in content, (
                    f"Subagent type {subagent_type} "
                    "should be documented"
                )

    def test_all_phases_documented(self) -> None:
        """Test that phase-specific subagent availability is documented."""
        docs_path = Path(__file__).parent.parent / "docs" / "subagents.md"

        if docs_path.exists():  # Only run if docs exist
            content = docs_path.read_text()

            # Each phase should be mentioned
            for phase in Phase:
                assert phase.value in content, f"Phase {phase.value} should be documented"

    def test_security_constraints_documented(self) -> None:
        """Test that security constraints are documented."""
        docs_path = Path(__file__).parent.parent / "docs" / "subagents.md"

        if docs_path.exists():  # Only run if docs exist
            content = docs_path.read_text()

            # Security constraints should be documented
            forbidden_tools = SUBAGENT_SECURITY_CONSTRAINTS["forbidden_tools"]
            assert isinstance(forbidden_tools, list)

            for tool in forbidden_tools:
                assert tool in content, (
                    f"Forbidden tool {tool} should be "
                    "documented in security section"
                )

    def test_invocation_examples_present(self) -> None:
        """Test that subagent invocation examples are present."""
        docs_path = Path(__file__).parent.parent / "docs" / "subagents.md"

        if docs_path.exists():  # Only run if docs exist
            content = docs_path.read_text()

            # Should include Task tool invocation examples
            assert "Task" in content
            assert "research-specialist" in content  # Example subagent name
            assert "code-reviewer" in content  # Another example subagent name

    def test_troubleshooting_section_present(self) -> None:
        """Test that troubleshooting section exists and is helpful."""
        docs_path = Path(__file__).parent.parent / "docs" / "subagents.md"

        if docs_path.exists():  # Only run if docs exist
            content = docs_path.read_text()

            # Should include troubleshooting information
            assert "troubleshooting" in content.lower() or "common issues" in content.lower()
            assert "error" in content.lower()  # Should discuss error scenarios
