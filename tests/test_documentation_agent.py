"""Tests for the documentation agent subagent."""

from __future__ import annotations

from pathlib import Path

from ralph.config import RalphConfig
from ralph.subagents import (
    SUBAGENT_SECURITY_CONSTRAINTS,
    create_documentation_agent,
    get_documentation_agent_prompt,
)


class TestDocumentationAgent:
    """Test documentation agent subagent creation."""

    def test_get_documentation_agent_prompt_function_exists(self):
        """Test that get_documentation_agent_prompt function exists and is callable."""
        prompt = get_documentation_agent_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_create_documentation_agent_function_exists(self):
        """Test that create_documentation_agent function exists and is callable."""
        from claude_agent_sdk import AgentDefinition

        agent = create_documentation_agent()
        assert isinstance(agent, AgentDefinition)

    def test_create_documentation_agent_returns_agent_definition(self):
        """Test that create_documentation_agent returns a proper AgentDefinition."""
        from claude_agent_sdk import AgentDefinition

        agent = create_documentation_agent()

        assert isinstance(agent, AgentDefinition)
        assert hasattr(agent, 'description')
        assert hasattr(agent, 'prompt')
        assert hasattr(agent, 'tools')
        assert hasattr(agent, 'model')

    def test_documentation_agent_has_correct_tools(self):
        """Test that documentation agent has only allowed read-only tools."""
        agent = create_documentation_agent()

        # Should have only Read, Grep, Glob according to security constraints
        expected_tools = ["Read", "Grep", "Glob"]
        assert agent.tools == expected_tools

        # Should not have any forbidden tools
        forbidden = ["Write", "Edit", "NotebookEdit", "Bash", "Task"]
        for tool in forbidden:
            assert tool not in agent.tools

    def test_documentation_agent_model_defaults_to_haiku(self):
        """Test that documentation agent defaults to haiku model for cost efficiency."""
        agent = create_documentation_agent()

        # Should default to haiku for cost efficiency (as specified in requirements)
        assert agent.model == "haiku"

    def test_documentation_agent_with_config_uses_haiku_model(self):
        """Test that documentation agent uses haiku even with different config."""
        # Create config with sonnet model
        config = RalphConfig(primary_model="claude-sonnet-4-20250514")

        agent = create_documentation_agent(config)

        # Should still use haiku for cost efficiency
        assert agent.model == "haiku"

    def test_documentation_agent_description_is_documentation_focused(self):
        """Test that documentation agent description emphasizes documentation focus."""
        agent = create_documentation_agent()

        description = agent.description.lower()
        # Should mention documentation-related keywords
        assert any(keyword in description for keyword in [
            'documentation', 'api', 'technical', 'readme', 'docs'
        ])

    def test_documentation_agent_prompt_contains_documentation_sections(self):
        """Test that documentation agent prompt includes required documentation sections."""
        agent = create_documentation_agent()

        prompt = agent.prompt.lower()

        # Should include documentation standards
        assert any(keyword in prompt for keyword in [
            'documentation standards', 'technical writing', 'style guide'
        ])

        # Should include API documentation patterns
        assert any(keyword in prompt for keyword in [
            'api documentation', 'endpoint documentation', 'api reference'
        ])

        # Should include code example generation
        assert any(keyword in prompt for keyword in [
            'code example', 'usage example', 'code snippet'
        ])

    def test_documentation_agent_prompt_has_read_only_constraints(self):
        """Test that documentation agent prompt emphasizes read-only nature."""
        agent = create_documentation_agent()

        prompt = agent.prompt.lower()
        assert 'read-only' in prompt or 'read only' in prompt

    def test_documentation_agent_prompt_template_variables(self):
        """Test that documentation agent prompt includes proper template variables."""
        prompt = get_documentation_agent_prompt()

        # Should include role information
        assert "Documentation Agent" in prompt

        # Should include mission statement
        assert any(keyword in prompt.lower() for keyword in [
            'api documentation', 'technical documentation', 'readme'
        ])

        # Should include available tools section
        assert "Available Tools" in prompt

        # Should include constraints section
        assert "Important Constraints" in prompt or "Constraints" in prompt


class TestDocumentationAgentTemplate:
    """Test documentation agent Jinja2 template."""

    def test_documentation_agent_template_exists(self):
        """Test that documentation_agent.jinja template file exists."""
        # Get the templates directory
        current_file = Path(__file__)
        templates_dir = current_file.parent.parent / "src" / "ralph" / "templates" / "subagents"
        template_path = templates_dir / "documentation_agent.jinja"

        assert template_path.exists(), f"Template file should exist at {template_path}"

    def test_documentation_agent_template_is_readable(self):
        """Test that documentation_agent.jinja template can be read and parsed."""
        from jinja2 import Environment, FileSystemLoader

        # Get the templates directory
        current_file = Path(__file__)
        templates_dir = current_file.parent.parent / "src" / "ralph" / "templates" / "subagents"

        # Set up Jinja2 environment
        env = Environment(loader=FileSystemLoader(templates_dir))
        template = env.get_template("documentation_agent.jinja")

        # Should not raise any errors
        assert template is not None

    def test_documentation_agent_template_renders_with_variables(self):
        """Test that documentation_agent.jinja template renders correctly with variables."""
        from jinja2 import Environment, FileSystemLoader

        # Get the templates directory
        current_file = Path(__file__)
        templates_dir = current_file.parent.parent / "src" / "ralph" / "templates" / "subagents"

        # Set up Jinja2 environment
        env = Environment(loader=FileSystemLoader(templates_dir))
        template = env.get_template("documentation_agent.jinja")

        # Template variables
        template_vars = {
            "role_name": "Documentation Agent",
            "mission_statement": "Test mission",
            "allowed_tools": ["Read", "Grep", "Glob"],
            "tool_descriptions": {
                "Read": "Read file contents",
                "Grep": "Search patterns",
                "Glob": "Find files"
            },
            "focus_areas": ["api documentation", "technical docs"],
            "time_limit_minutes": 5
        }

        # Should render without errors
        rendered = template.render(**template_vars)
        assert isinstance(rendered, str)
        assert len(rendered) > 0

        # Should contain expected content
        assert "Documentation Agent" in rendered
        assert "Test mission" in rendered
        assert "Read" in rendered
        assert "api documentation" in rendered


class TestDocumentationAgentSecurity:
    """Test documentation agent security constraints."""

    def test_documentation_agent_tools_match_security_constraints(self):
        """Test that documentation agent tools match defined security constraints."""
        from typing import cast

        agent = create_documentation_agent()

        # Get expected tools from security constraints
        permissions = cast(dict[str, list[str]], SUBAGENT_SECURITY_CONSTRAINTS["tool_permissions"])
        expected_tools = permissions["documentation-agent"]

        assert agent.tools == expected_tools

    def test_documentation_agent_has_no_forbidden_tools(self):
        """Test that documentation agent doesn't have any forbidden tools."""
        from typing import cast

        agent = create_documentation_agent()

        # Get forbidden tools from security constraints
        forbidden = cast(list[str], SUBAGENT_SECURITY_CONSTRAINTS["forbidden_tools"])

        for tool in agent.tools:
            assert tool not in forbidden, f"Documentation agent has forbidden tool: {tool}"


class TestDocumentationAgentPromptContent:
    """Test documentation agent prompt content requirements."""

    def test_prompt_contains_api_documentation_patterns(self):
        """Test that prompt includes API documentation patterns."""
        prompt = get_documentation_agent_prompt()
        prompt_lower = prompt.lower()

        # Should include API documentation guidance
        assert any(keyword in prompt_lower for keyword in [
            'api endpoint', 'endpoint documentation', 'rest api', 'api reference'
        ])

        # Should include parameter documentation
        assert any(keyword in prompt_lower for keyword in [
            'parameter', 'request', 'response', 'schema'
        ])

    def test_prompt_contains_technical_documentation_guidance(self):
        """Test that prompt includes technical documentation guidance."""
        prompt = get_documentation_agent_prompt()
        prompt_lower = prompt.lower()

        # Should include technical writing standards
        assert any(keyword in prompt_lower for keyword in [
            'technical writing', 'documentation standard', 'style guide'
        ])

        # Should include completeness guidance
        assert any(keyword in prompt_lower for keyword in [
            'complete', 'comprehensive', 'thorough'
        ])

    def test_prompt_contains_readme_update_guidance(self):
        """Test that prompt includes README update guidance."""
        prompt = get_documentation_agent_prompt()
        prompt_lower = prompt.lower()

        # Should include README guidance
        assert any(keyword in prompt_lower for keyword in [
            'readme', 'installation', 'getting started', 'usage guide'
        ])

    def test_prompt_contains_code_example_generation(self):
        """Test that prompt includes code example generation guidance."""
        prompt = get_documentation_agent_prompt()
        prompt_lower = prompt.lower()

        # Should include code example guidance
        assert any(keyword in prompt_lower for keyword in [
            'code example', 'usage example', 'sample code', 'code snippet'
        ])

        # Should include practical examples
        assert any(keyword in prompt_lower for keyword in [
            'example', 'demonstration', 'tutorial'
        ])
