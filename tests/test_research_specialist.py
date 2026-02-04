"""Tests for the research specialist subagent factory functions."""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from ralph.config import RalphConfig
from ralph.subagents import create_research_specialist_agent, get_research_specialist_prompt


class TestResearchSpecialistAgent:
    """Test research specialist agent creation."""

    def test_create_research_specialist_agent_returns_agent_definition(self):
        """Test that create_research_specialist_agent returns proper AgentDefinition."""
        config = RalphConfig()
        result = create_research_specialist_agent(config)

        assert isinstance(result, AgentDefinition)

    def test_research_specialist_has_required_tools(self):
        """Test that research specialist has the correct allowed tools."""
        config = RalphConfig()
        agent = create_research_specialist_agent(config)

        expected_tools = ["Read", "Grep", "Glob", "WebSearch", "WebFetch"]
        assert agent.tools == expected_tools

    def test_research_specialist_has_description(self):
        """Test that research specialist has a description."""
        config = RalphConfig()
        agent = create_research_specialist_agent(config)

        assert agent.description is not None
        assert len(agent.description) > 0
        assert isinstance(agent.description, str)

    def test_research_specialist_has_prompt(self):
        """Test that research specialist has a prompt."""
        config = RalphConfig()
        agent = create_research_specialist_agent(config)

        assert agent.prompt is not None
        assert len(agent.prompt) > 0
        assert isinstance(agent.prompt, str)

    def test_research_specialist_uses_model_mapping_from_config(self):
        """Test that research specialist uses model mapping from config."""
        config = RalphConfig()
        config.subagents.model_mapping["research-specialist"] = "haiku"
        agent = create_research_specialist_agent(config)

        # Should map to SDK literal type
        assert agent.model == "haiku"

    def test_research_specialist_uses_default_model_when_config_none(self):
        """Test that research specialist uses default model when config is None."""
        agent = create_research_specialist_agent(None)

        # Should use a reasonable default
        assert agent.model is not None
        assert len(agent.model) > 0


class TestGetResearchSpecialistPrompt:
    """Test research specialist prompt generation."""

    def test_get_research_specialist_prompt_returns_string(self):
        """Test that get_research_specialist_prompt returns a string."""
        config = RalphConfig()
        prompt = get_research_specialist_prompt(config)

        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_prompt_contains_expected_sections(self):
        """Test that prompt contains expected template sections."""
        config = RalphConfig()
        prompt = get_research_specialist_prompt(config)

        # Check for key sections from template
        assert "Your Mission" in prompt
        assert "Available Tools" in prompt
        assert "Report Format" in prompt
        assert "Important Constraints" in prompt

    def test_prompt_includes_all_allowed_tools(self):
        """Test that prompt lists all allowed tools."""
        config = RalphConfig()
        prompt = get_research_specialist_prompt(config)

        expected_tools = ["Read", "Grep", "Glob", "WebSearch", "WebFetch"]
        for tool in expected_tools:
            assert tool in prompt

    def test_prompt_renders_with_default_config_when_none(self):
        """Test that prompt renders properly when config is None."""
        prompt = get_research_specialist_prompt(None)

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "Your Mission" in prompt
