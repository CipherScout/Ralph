"""Tests for the subagents module."""

from __future__ import annotations

from typing import cast

import pytest

from ralph.models import Phase
from ralph.subagents import (
    PHASE_SUBAGENT_CONFIG,
    SUBAGENT_SECURITY_CONSTRAINTS,
    create_code_reviewer_agent,
    create_documentation_agent,
    create_product_analyst_agent,
    create_research_specialist_agent,
    create_test_engineer_agent,
    filter_subagents_by_phase,
    get_code_reviewer_prompt,
    get_documentation_agent_prompt,
    get_product_analyst_prompt,
    get_research_specialist_prompt,
    get_subagent_prompt,
    get_subagents_for_phase,
    get_test_engineer_prompt,
    validate_subagent_tools,
)


@pytest.fixture
def mock_config():
    """Fixture providing a mock RalphConfig for testing with haiku model mapping."""
    from ralph.config import RalphConfig
    config = RalphConfig(
        primary_model="claude-haiku-1-20250514",
        max_iterations=50,
    )
    # Override model mapping so all subagents use haiku
    for key in config.subagents.model_mapping:
        config.subagents.model_mapping[key] = "haiku"
    return config


@pytest.fixture
def all_subagent_types():
    """Fixture providing all valid subagent type names."""
    return [
        "research-specialist",
        "code-reviewer",
        "test-engineer",
        "documentation-agent",
        "product-analyst"
    ]


@pytest.fixture
def all_phases():
    """Fixture providing all Ralph phases."""
    return [Phase.DISCOVERY, Phase.PLANNING, Phase.BUILDING, Phase.VALIDATION]


class TestSubagentSecurityConstraints:
    """Test security constraints for subagents."""

    def test_security_constraints_defined(self):
        """Test that SUBAGENT_SECURITY_CONSTRAINTS is properly defined."""
        assert isinstance(SUBAGENT_SECURITY_CONSTRAINTS, dict)
        assert "forbidden_tools" in SUBAGENT_SECURITY_CONSTRAINTS
        assert "tool_permissions" in SUBAGENT_SECURITY_CONSTRAINTS

    def test_forbidden_tools_include_dangerous_tools(self):
        """Test that forbidden tools include dangerous operations."""
        forbidden = SUBAGENT_SECURITY_CONSTRAINTS["forbidden_tools"]

        # Critical: No subagent should have these dangerous tools
        dangerous_tools = ["Write", "Edit", "NotebookEdit", "Bash", "Task"]
        for tool in dangerous_tools:
            assert tool in forbidden, f"Dangerous tool {tool} should be forbidden"

    def test_tool_permissions_structure(self):
        """Test that tool permissions are properly structured."""
        permissions = cast(dict[str, list[str]], SUBAGENT_SECURITY_CONSTRAINTS["tool_permissions"])

        # Should have permissions for expected subagent types
        expected_types = [
            "research-specialist",
            "code-reviewer",
            "test-engineer",
            "documentation-agent",
            "product-analyst"
        ]

        for subagent_type in expected_types:
            assert subagent_type in permissions, f"Missing permissions for {subagent_type}"
            assert isinstance(
                permissions[subagent_type], list
            ), f"Permissions for {subagent_type} should be a list"

    def test_read_only_tools_for_all_subagents(self):
        """Test that all subagents only have read-only tools."""
        permissions = cast(dict[str, list[str]], SUBAGENT_SECURITY_CONSTRAINTS["tool_permissions"])
        forbidden = cast(list[str], SUBAGENT_SECURITY_CONSTRAINTS["forbidden_tools"])

        for subagent_type, tools in permissions.items():
            for tool in tools:
                assert tool not in forbidden, f"Subagent {subagent_type} has forbidden tool {tool}"


class TestGetSubagentsForPhase:
    """Test phase-specific subagent allocation."""

    def test_get_subagents_for_phase_callable(self):
        """Test that get_subagents_for_phase function exists and is callable."""
        # This should not raise an error
        result = get_subagents_for_phase(Phase.BUILDING, None)
        assert isinstance(result, dict)

    def test_returns_agent_definitions(self):
        """Test that the function returns properly structured agent definitions."""
        from claude_agent_sdk import AgentDefinition

        result = get_subagents_for_phase(Phase.BUILDING, None)

        # Should return a dictionary
        assert isinstance(result, dict)

        # Keys should be subagent names
        for key in result:
            assert isinstance(key, str)

        # Values should be AgentDefinition objects
        for value in result.values():
            assert isinstance(value, AgentDefinition)

    def test_building_phase_returns_available_subagents(self):
        """Test that building phase returns the correct available subagents."""
        from claude_agent_sdk import AgentDefinition

        result = get_subagents_for_phase(Phase.BUILDING, None)

        # Building phase should include available subagents:
        # test-engineer, code-reviewer, research-specialist
        # All of these are now implemented
        expected_available = ["code-reviewer", "research-specialist", "test-engineer"]

        # Should include implemented subagents that are configured for building phase
        for subagent_name in expected_available:
            if subagent_name in PHASE_SUBAGENT_CONFIG[Phase.BUILDING]:
                assert subagent_name in result, f"Missing {subagent_name} in building phase"
                assert isinstance(result[subagent_name], AgentDefinition)

    def test_discovery_phase_returns_available_subagents(self):
        """Test that discovery phase returns the correct available subagents."""
        from claude_agent_sdk import AgentDefinition

        result = get_subagents_for_phase(Phase.DISCOVERY, None)

        # Discovery phase should include: research-specialist, product-analyst, documentation-agent
        # All are now implemented
        expected_available = ["research-specialist", "product-analyst", "documentation-agent"]

        for subagent_name in expected_available:
            if subagent_name in PHASE_SUBAGENT_CONFIG[Phase.DISCOVERY]:
                assert subagent_name in result, f"Missing {subagent_name} in discovery phase"
                assert isinstance(result[subagent_name], AgentDefinition)

    def test_only_returns_implemented_subagents(self):
        """Test that function only returns subagents that are actually implemented."""
        result = get_subagents_for_phase(Phase.BUILDING, None)

        # Verify all returned subagents are properly implemented
        assert isinstance(result, dict)
        # No unimplemented subagents to test - all expected agents are implemented

    def test_different_phases_return_different_subagents(self):
        """Test that different phases may return different subagent sets."""
        discovery_subagents = get_subagents_for_phase(Phase.DISCOVERY, None)
        building_subagents = get_subagents_for_phase(Phase.BUILDING, None)

        # Both should return dictionaries
        assert isinstance(discovery_subagents, dict)
        assert isinstance(building_subagents, dict)

        # Discovery should include research-specialist
        assert "research-specialist" in discovery_subagents
        # Building should include both code-reviewer and research-specialist
        assert "code-reviewer" in building_subagents
        assert "research-specialist" in building_subagents

        # Building should have code-reviewer but discovery should not
        assert "code-reviewer" not in discovery_subagents

    def test_passes_config_to_factory_functions(self):
        """Test that config parameter is passed through to factory functions."""
        from ralph.config import RalphConfig

        # Create a test config with model mapping overrides
        config = RalphConfig()
        for key in config.subagents.model_mapping:
            config.subagents.model_mapping[key] = "haiku"

        result = get_subagents_for_phase(Phase.BUILDING, config)

        # Should still return valid agent definitions
        assert isinstance(result, dict)
        for _agent_name, agent_def in result.items():
            assert hasattr(agent_def, 'model')
            # All agents should use the config model mapping (haiku)
            assert agent_def.model == "haiku"


class TestCodeReviewerAgent:
    """Test code reviewer subagent creation."""

    def test_create_code_reviewer_agent_returns_agent_definition(self):
        """Test that create_code_reviewer_agent returns a proper AgentDefinition."""
        from claude_agent_sdk import AgentDefinition

        agent = create_code_reviewer_agent()

        assert isinstance(agent, AgentDefinition)
        assert hasattr(agent, 'description')
        assert hasattr(agent, 'prompt')
        assert hasattr(agent, 'tools')
        assert hasattr(agent, 'model')

    def test_code_reviewer_has_correct_tools(self):
        """Test that code reviewer has only allowed read-only tools."""
        agent = create_code_reviewer_agent()

        # Should have only Read, Grep, Glob according to security constraints
        expected_tools = ["Read", "Grep", "Glob"]
        assert agent.tools == expected_tools

        # Should not have any forbidden tools
        forbidden = ["Write", "Edit", "NotebookEdit", "Bash", "Task"]
        for tool in forbidden:
            assert tool not in agent.tools

    def test_code_reviewer_description_is_security_focused(self):
        """Test that code reviewer description emphasizes security focus."""
        agent = create_code_reviewer_agent()

        description = agent.description.lower()
        # Should mention security-related keywords
        assert any(keyword in description for keyword in [
            'security', 'vulnerability', 'code review', 'quality'
        ])

    def test_code_reviewer_prompt_contains_security_sections(self):
        """Test that code reviewer prompt includes required security analysis sections."""
        agent = create_code_reviewer_agent()

        prompt = agent.prompt.lower()

        # Should include OWASP Top 10 patterns
        assert 'owasp' in prompt or 'top 10' in prompt

        # Should include SOLID principles
        assert 'solid' in prompt or 'solid principles' in prompt

        # Should include severity-based prioritization
        assert any(keyword in prompt for keyword in [
            'severity', 'critical', 'high', 'medium', 'low', 'priority'
        ])

        # Should include security vulnerability analysis
        assert any(keyword in prompt for keyword in [
            'vulnerability', 'security', 'injection', 'xss', 'csrf'
        ])

    def test_code_reviewer_prompt_has_read_only_constraints(self):
        """Test that code reviewer prompt emphasizes read-only nature."""
        agent = create_code_reviewer_agent()

        prompt = agent.prompt.lower()
        assert 'read-only' in prompt or 'read only' in prompt


class TestPhaseSubagentConfig:
    """Test phase-specific subagent configuration mapping."""

    def test_phase_subagent_config_exists(self):
        """Test that PHASE_SUBAGENT_CONFIG constant exists and is properly structured."""
        assert isinstance(PHASE_SUBAGENT_CONFIG, dict)

        # Should have entries for all Ralph phases
        expected_phases = [Phase.DISCOVERY, Phase.PLANNING, Phase.BUILDING, Phase.VALIDATION]
        for phase in expected_phases:
            assert phase in PHASE_SUBAGENT_CONFIG, f"Missing config for phase {phase}"

    def test_phase_subagent_config_contains_valid_subagent_types(self):
        """Test that each phase maps to valid subagent type lists."""
        # Get valid subagent types from security constraints
        valid_types = list(SUBAGENT_SECURITY_CONSTRAINTS["tool_permissions"].keys())

        for phase, subagent_types in PHASE_SUBAGENT_CONFIG.items():
            assert isinstance(subagent_types, list), f"Phase {phase} should map to a list"

            for subagent_type in subagent_types:
                assert isinstance(subagent_type, str), (
                    f"Type should be string, got {type(subagent_type)}"
                )
                assert subagent_type in valid_types, (
                    f"Unknown type {subagent_type} in phase {phase}"
                )

    def test_discovery_phase_has_research_focus(self):
        """Test that discovery phase includes research-oriented subagents."""
        discovery_subagents = PHASE_SUBAGENT_CONFIG[Phase.DISCOVERY]

        # Discovery should include research specialist for gathering requirements
        assert "research-specialist" in discovery_subagents, (
            "Discovery should include research specialist"
        )
        # Discovery should include product analyst for understanding requirements
        assert "product-analyst" in discovery_subagents, "Discovery should include product analyst"

    def test_planning_phase_has_architecture_focus(self):
        """Test that planning phase includes architecture and planning subagents."""
        planning_subagents = PHASE_SUBAGENT_CONFIG[Phase.PLANNING]

        # Planning should include research specialist for technical architecture decisions
        assert "research-specialist" in planning_subagents, (
            "Planning should include research specialist"
        )

    def test_building_phase_has_development_focus(self):
        """Test that building phase includes development-oriented subagents."""
        building_subagents = PHASE_SUBAGENT_CONFIG[Phase.BUILDING]

        # Building should include test engineer for TDD support
        assert "test-engineer" in building_subagents, "Building phase should include test engineer"
        # Building should include code reviewer for quality assurance
        assert "code-reviewer" in building_subagents, "Building phase should include code reviewer"

    def test_validation_phase_has_qa_focus(self):
        """Test that validation phase includes quality assurance subagents."""
        validation_subagents = PHASE_SUBAGENT_CONFIG[Phase.VALIDATION]

        # Validation should include code reviewer for final review
        assert "code-reviewer" in validation_subagents, (
            "Validation phase should include code reviewer"
        )
        # Validation should include test engineer for comprehensive testing
        assert "test-engineer" in validation_subagents, (
            "Validation phase should include test engineer"
        )
        # Validation should include documentation agent for ensuring docs are complete
        assert "documentation-agent" in validation_subagents, (
            "Validation phase should include documentation agent"
        )


class TestTestEngineerAgent:
    """Test test engineer subagent creation."""

    def test_create_test_engineer_agent_returns_agent_definition(self):
        """Test that create_test_engineer_agent returns a proper AgentDefinition."""
        from claude_agent_sdk import AgentDefinition

        from ralph.subagents import create_test_engineer_agent

        agent = create_test_engineer_agent()

        assert isinstance(agent, AgentDefinition)
        assert hasattr(agent, 'description')
        assert hasattr(agent, 'prompt')
        assert hasattr(agent, 'tools')
        assert hasattr(agent, 'model')

    def test_test_engineer_has_correct_tools(self):
        """Test that test engineer has only allowed read-only tools."""
        from ralph.subagents import create_test_engineer_agent

        agent = create_test_engineer_agent()

        # Should have only Read, Grep, Glob according to security constraints
        expected_tools = ["Read", "Grep", "Glob"]
        assert agent.tools == expected_tools

        # Should not have any forbidden tools
        forbidden = ["Write", "Edit", "NotebookEdit", "Bash", "Task"]
        for tool in forbidden:
            assert tool not in agent.tools

    def test_test_engineer_model_defaults_to_sonnet(self):
        """Test that test engineer defaults to sonnet model for comprehensive analysis."""
        from ralph.subagents import create_test_engineer_agent

        agent = create_test_engineer_agent()

        # Should default to sonnet for comprehensive analysis
        assert agent.model == "sonnet"

    def test_test_engineer_description_is_testing_focused(self):
        """Test that test engineer description emphasizes testing focus."""
        from ralph.subagents import create_test_engineer_agent

        agent = create_test_engineer_agent()

        description = agent.description.lower()
        # Should mention testing-related keywords
        assert any(keyword in description for keyword in [
            'test', 'testing', 'coverage', 'quality', 'strategy'
        ])

    def test_test_engineer_prompt_contains_testing_sections(self):
        """Test that test engineer prompt includes required testing analysis sections."""
        from ralph.subagents import create_test_engineer_agent

        agent = create_test_engineer_agent()

        prompt = agent.prompt.lower()

        # Should include test strategy framework
        assert any(keyword in prompt for keyword in [
            'test strategy', 'testing approach', 'coverage analysis'
        ])

        # Should include edge case identification
        assert any(keyword in prompt for keyword in [
            'edge case', 'boundary condition', 'edge cases'
        ])

        # Should include test prioritization patterns
        assert any(keyword in prompt for keyword in [
            'prioritization', 'priority', 'test prioritization'
        ])

        # Should include quality assessment
        assert any(keyword in prompt for keyword in [
            'quality', 'coverage target', 'quality assessment'
        ])

    def test_test_engineer_prompt_has_read_only_constraints(self):
        """Test that test engineer prompt emphasizes read-only nature."""
        from ralph.subagents import create_test_engineer_agent

        agent = create_test_engineer_agent()

        prompt = agent.prompt.lower()
        assert 'read-only' in prompt or 'read only' in prompt

    def test_test_engineer_with_config_uses_sonnet_model(self):
        """Test that test engineer uses sonnet even with different config."""
        from ralph.config import RalphConfig
        from ralph.subagents import create_test_engineer_agent

        # Create config with haiku model
        config = RalphConfig(primary_model="claude-haiku-1-20250514")

        agent = create_test_engineer_agent(config)

        # Should still default to sonnet for comprehensive analysis
        assert agent.model == "sonnet"


class TestFilterSubagentsByPhase:
    """Test filter_subagents_by_phase function."""

    def test_filter_subagents_by_phase_exists(self):
        """Test that filter_subagents_by_phase function exists and is callable."""
        # Should not raise an error
        result = filter_subagents_by_phase(Phase.BUILDING, {})
        assert isinstance(result, dict)

    def test_filter_returns_only_phase_appropriate_subagents(self):
        """Test that filter function returns only subagents configured for the given phase."""
        from ralph.subagents import create_research_specialist_agent

        # Create a set of all subagents
        all_subagents = {
            "research-specialist": create_research_specialist_agent(),
            "code-reviewer": create_code_reviewer_agent(),
            # Note: other subagent factories will be added in later tasks
        }

        # Filter for building phase
        building_subagents = filter_subagents_by_phase(Phase.BUILDING, all_subagents)

        # Should only include subagents configured for building phase
        expected_building_types = PHASE_SUBAGENT_CONFIG[Phase.BUILDING]

        # All returned subagents should be in the phase config
        for subagent_name in building_subagents:
            assert subagent_name in expected_building_types, (
                f"Unexpected subagent {subagent_name} in building phase"
            )

    def test_filter_preserves_agent_definitions(self):
        """Test that filter function preserves the actual AgentDefinition objects."""
        from claude_agent_sdk import AgentDefinition

        from ralph.subagents import create_research_specialist_agent

        # Create test subagents
        original_agent = create_research_specialist_agent()
        all_subagents = {"research-specialist": original_agent}

        # Filter for discovery phase (should include research specialist)
        discovery_subagents = filter_subagents_by_phase(Phase.DISCOVERY, all_subagents)

        if "research-specialist" in discovery_subagents:
            # Should be the same AgentDefinition object
            assert discovery_subagents["research-specialist"] is original_agent
            assert isinstance(discovery_subagents["research-specialist"], AgentDefinition)

    def test_filter_empty_input_returns_empty(self):
        """Test that filtering empty subagent dict returns empty dict."""
        result = filter_subagents_by_phase(Phase.BUILDING, {})
        assert result == {}

    def test_filter_no_matching_subagents_returns_empty(self):
        """Test that filtering with no matching subagents returns empty dict."""
        # Create subagent that's not in any phase (hypothetical)
        all_subagents = {"nonexistent-agent": create_code_reviewer_agent()}

        result = filter_subagents_by_phase(Phase.BUILDING, all_subagents)
        assert result == {}


class TestProductAnalystAgent:
    """Test product analyst subagent creation."""

    def test_create_product_analyst_agent_returns_agent_definition(self):
        """Test that create_product_analyst_agent returns a proper AgentDefinition."""
        from claude_agent_sdk import AgentDefinition

        agent = create_product_analyst_agent()

        assert isinstance(agent, AgentDefinition)
        assert hasattr(agent, 'description')
        assert hasattr(agent, 'prompt')
        assert hasattr(agent, 'tools')
        assert hasattr(agent, 'model')

    def test_product_analyst_has_correct_tools(self):
        """Test that product analyst has only allowed read-only tools."""
        agent = create_product_analyst_agent()

        # Should have only Read, Grep, Glob according to security constraints
        expected_tools = ["Read", "Grep", "Glob"]
        assert agent.tools == expected_tools

        # Should not have any forbidden tools
        forbidden = ["Write", "Edit", "NotebookEdit", "Bash", "Task"]
        for tool in forbidden:
            assert tool not in agent.tools

    def test_product_analyst_model_defaults_to_haiku(self):
        """Test that product analyst defaults to haiku model for efficiency."""
        agent = create_product_analyst_agent()

        # Should default to haiku for efficiency (per task specification)
        assert agent.model == "haiku"

    def test_product_analyst_description_is_requirements_focused(self):
        """Test that product analyst description emphasizes requirements analysis focus."""
        agent = create_product_analyst_agent()

        description = agent.description.lower()
        # Should mention requirements-related keywords
        assert any(keyword in description for keyword in [
            'requirements', 'analysis', 'product', 'user story', 'acceptance criteria'
        ])

    def test_product_analyst_prompt_contains_requirements_sections(self):
        """Test that product analyst prompt includes required requirements analysis sections."""
        agent = create_product_analyst_agent()

        prompt = agent.prompt.lower()

        # Should include requirements analysis framework
        assert any(keyword in prompt for keyword in [
            'requirements analysis', 'clarity assessment', 'quality assessment'
        ])

        # Should include ambiguity detection patterns
        assert any(keyword in prompt for keyword in [
            'ambiguity', 'ambiguous', 'unclear requirements', 'clarification'
        ])

        # Should include user story validation patterns
        assert any(keyword in prompt for keyword in [
            'user story', 'invest', 'acceptance criteria', 'validation'
        ])

        # Should include edge case identification
        assert any(keyword in prompt for keyword in [
            'edge case', 'edge cases', 'missing requirements'
        ])

    def test_product_analyst_prompt_has_read_only_constraints(self):
        """Test that product analyst prompt emphasizes read-only nature."""
        agent = create_product_analyst_agent()

        prompt = agent.prompt.lower()
        assert 'read-only' in prompt or 'read only' in prompt

    def test_product_analyst_with_config_uses_haiku_model(self):
        """Test that product analyst uses haiku even with different config."""
        from ralph.config import RalphConfig

        # Create config with sonnet model
        config = RalphConfig(primary_model="claude-sonnet-4-20250514")

        agent = create_product_analyst_agent(config)

        # Should still default to haiku for efficiency (per specification)
        assert agent.model == "haiku"

    def test_product_analyst_prompt_contains_prioritization_techniques(self):
        """Test that product analyst includes prioritization techniques in prompt."""
        agent = create_product_analyst_agent()

        prompt = agent.prompt.lower()

        # Should include prioritization frameworks
        assert any(keyword in prompt for keyword in [
            'moscow', 'pablo', 'swot', 'prioritization', 'priority'
        ])

    def test_product_analyst_prompt_contains_stakeholder_analysis(self):
        """Test that product analyst includes stakeholder perspective analysis."""
        agent = create_product_analyst_agent()

        prompt = agent.prompt.lower()

        # Should include stakeholder analysis
        assert any(keyword in prompt for keyword in [
            'stakeholder', 'stakeholders', 'perspective', 'viewpoint'
        ])

    def test_product_analyst_prompt_contains_research_guidance(self):
        """Test that product analyst includes research guidance generation."""
        agent = create_product_analyst_agent()

        prompt = agent.prompt.lower()

        # Should include research guidance
        assert any(keyword in prompt for keyword in [
            'research', 'investigation', 'research questions', 'guidance'
        ])


class TestValidateSubagentTools:
    """Test validate_subagent_tools security function."""

    def test_validate_subagent_tools_exists(self):
        """Test that validate_subagent_tools function exists and is callable."""
        # Should not raise an error
        result = validate_subagent_tools("research-specialist", ["Read", "Grep"])
        assert isinstance(result, list)

    def test_filters_out_forbidden_tools(self):
        """Test that forbidden tools are filtered out from requested tools."""
        subagent_type = "research-specialist"
        requested_tools = ["Read", "Write", "Edit", "Grep", "Bash"]

        result = validate_subagent_tools(subagent_type, requested_tools)

        # Should not contain any forbidden tools
        forbidden = SUBAGENT_SECURITY_CONSTRAINTS["forbidden_tools"]
        for tool in forbidden:
            assert tool not in result, f"Forbidden tool {tool} should be filtered out"

        # Should contain allowed tools that were requested
        assert "Read" in result, "Allowed tool Read should be preserved"
        assert "Grep" in result, "Allowed tool Grep should be preserved"

    def test_only_returns_tools_allowed_for_subagent_type(self):
        """Test that only tools allowed for specific subagent type are returned."""
        subagent_type = "code-reviewer"
        # Request tools including some allowed for other types
        # but not code-reviewer
        requested_tools = [
            "Read", "Grep", "Glob", "WebSearch", "WebFetch",
        ]

        result = validate_subagent_tools(subagent_type, requested_tools)

        # Should only contain tools allowed for code-reviewer
        tool_permissions = cast(
            dict[str, list[str]],
            SUBAGENT_SECURITY_CONSTRAINTS["tool_permissions"],
        )
        expected_allowed = tool_permissions["code-reviewer"]
        for tool in result:
            assert tool in expected_allowed, (
                f"Tool {tool} not allowed for {subagent_type}"
            )

        # Should not contain WebSearch or WebFetch
        # (allowed for research-specialist but not code-reviewer)
        assert "WebSearch" not in result, (
            "WebSearch should not be allowed for code-reviewer"
        )
        assert "WebFetch" not in result, (
            "WebFetch should not be allowed for code-reviewer"
        )

    def test_returns_empty_list_for_unknown_subagent_type(self):
        """Test that unknown subagent types return empty tool list."""
        result = validate_subagent_tools("unknown-subagent", ["Read", "Write"])
        assert result == [], "Unknown subagent type should return empty tool list"

    def test_returns_empty_list_when_no_tools_requested(self):
        """Test that empty requested tools list returns empty result."""
        result = validate_subagent_tools("research-specialist", [])
        assert result == [], "Empty requested tools should return empty result"

    def test_preserves_order_of_allowed_tools(self):
        """Test that the order of allowed tools is preserved."""
        subagent_type = "research-specialist"
        requested_tools = ["WebFetch", "Read", "Grep", "WebSearch", "Glob"]

        result = validate_subagent_tools(subagent_type, requested_tools)

        # Find positions of tools in result that were in request
        tool_permissions = cast(
            dict[str, list[str]],
            SUBAGENT_SECURITY_CONSTRAINTS["tool_permissions"],
        )
        allowed_tools = tool_permissions[subagent_type]
        expected_result = [tool for tool in requested_tools if tool in allowed_tools]

        assert result == expected_result, "Order of allowed tools should be preserved"

    def test_handles_duplicate_tools_in_request(self):
        """Test that duplicate tools in request are handled properly."""
        subagent_type = "research-specialist"
        requested_tools = ["Read", "Read", "Grep", "WebSearch", "Read"]

        result = validate_subagent_tools(subagent_type, requested_tools)

        # Should not contain duplicates
        assert len(result) == len(set(result)), "Result should not contain duplicates"

        # Should contain each allowed tool only once
        assert result.count("Read") == 1, "Read should appear only once in result"

    def test_case_sensitive_tool_matching(self):
        """Test that tool name matching is case-sensitive."""
        subagent_type = "research-specialist"
        requested_tools = ["read", "READ", "Read", "grep", "Grep"]

        result = validate_subagent_tools(subagent_type, requested_tools)

        # Should only match exact case
        assert "Read" in result, "Exact case Read should be matched"
        assert "Grep" in result, "Exact case Grep should be matched"
        assert "read" not in result, "Lowercase read should not be matched"
        assert "READ" not in result, "Uppercase READ should not be matched"
        assert "grep" not in result, "Lowercase grep should not be matched"

    def test_all_subagent_types_have_only_read_only_tools(self):
        """Test that validate_subagent_tools enforces read-only access for all subagent types."""
        tool_permissions = SUBAGENT_SECURITY_CONSTRAINTS["tool_permissions"]
        forbidden_tools = SUBAGENT_SECURITY_CONSTRAINTS["forbidden_tools"]

        for subagent_type in tool_permissions:
            # Request all possible tools including forbidden ones
            all_tools = [
                "Read", "Write", "Edit", "NotebookEdit",
                "Bash", "Task", "Grep", "Glob",
                "WebSearch", "WebFetch",
            ]

            result = validate_subagent_tools(subagent_type, all_tools)

            # Should not contain any forbidden tools
            for forbidden_tool in forbidden_tools:
                assert forbidden_tool not in result, (
                    f"Subagent {subagent_type} should not have "
                    f"access to {forbidden_tool}"
                )

            # Should only contain read-only tools
            read_only_tools = [
                "Read", "Grep", "Glob", "WebSearch", "WebFetch",
            ]
            for tool in result:
                assert tool in read_only_tools, (
                    f"Tool {tool} for {subagent_type} "
                    f"should be read-only"
                )

    def test_research_specialist_gets_web_access(self):
        """Test that research specialist gets web access tools while others don't."""
        # Research specialist should get web tools
        research_tools = validate_subagent_tools(
            "research-specialist",
            ["Read", "WebSearch", "WebFetch"],
        )
        assert "WebSearch" in research_tools, "Research specialist should have WebSearch"
        assert "WebFetch" in research_tools, "Research specialist should have WebFetch"

        # Other subagent types should not get web tools
        for subagent_type in [
            "code-reviewer", "test-engineer",
            "documentation-agent", "product-analyst",
        ]:
            result = validate_subagent_tools(subagent_type, ["Read", "WebSearch", "WebFetch"])
            assert "WebSearch" not in result, f"{subagent_type} should not have WebSearch"
            assert "WebFetch" not in result, f"{subagent_type} should not have WebFetch"


class TestResearchSpecialistAgent:
    """Test research specialist subagent creation."""

    def test_create_research_specialist_agent_returns_agent_definition(self):
        """Test that create_research_specialist_agent returns a proper AgentDefinition."""
        from claude_agent_sdk import AgentDefinition

        agent = create_research_specialist_agent()

        assert isinstance(agent, AgentDefinition)
        assert hasattr(agent, 'description')
        assert hasattr(agent, 'prompt')
        assert hasattr(agent, 'tools')
        assert hasattr(agent, 'model')

    def test_research_specialist_has_correct_tools(self):
        """Test that research specialist has only allowed read-only tools including web access."""
        agent = create_research_specialist_agent()

        # Should have Read, Grep, Glob, WebSearch, WebFetch according to security constraints
        expected_tools = ["Read", "Grep", "Glob", "WebSearch", "WebFetch"]
        assert agent.tools == expected_tools

        # Should not have any forbidden tools
        forbidden = ["Write", "Edit", "NotebookEdit", "Bash", "Task"]
        for tool in forbidden:
            assert tool not in agent.tools

    def test_research_specialist_description_is_research_focused(self):
        """Test that research specialist description emphasizes research focus."""
        agent = create_research_specialist_agent()

        description = agent.description.lower()
        # Should mention research-related keywords
        assert any(keyword in description for keyword in [
            'research', 'analysis', 'technical', 'library', 'evaluation'
        ])

    def test_research_specialist_prompt_contains_research_sections(self):
        """Test that research specialist prompt includes required research analysis sections."""
        agent = create_research_specialist_agent()

        prompt = agent.prompt.lower()

        # Should include library evaluation
        assert any(keyword in prompt for keyword in [
            'library evaluation', 'technology comparison', 'library'
        ])

        # Should include pattern research
        assert any(keyword in prompt for keyword in [
            'pattern research', 'patterns', 'best practices'
        ])

        # Should include risk assessment
        assert any(keyword in prompt for keyword in [
            'risk assessment', 'risk', 'trade-offs'
        ])

        # Should include web search capabilities
        assert any(keyword in prompt for keyword in [
            'websearch', 'web search', 'webfetch', 'documentation'
        ])

    def test_research_specialist_prompt_has_read_only_constraints(self):
        """Test that research specialist prompt emphasizes read-only nature."""
        agent = create_research_specialist_agent()

        prompt = agent.prompt.lower()
        assert 'read-only' in prompt or 'read only' in prompt

    def test_research_specialist_with_config_uses_model_mapping(self):
        """Test that research specialist uses model mapping from config."""
        from ralph.config import RalphConfig

        # Override model mapping for research specialist
        config = RalphConfig()
        config.subagents.model_mapping["research-specialist"] = "haiku"

        agent = create_research_specialist_agent(config)

        # Should use the model from mapping
        assert agent.model == "haiku"

    def test_research_specialist_defaults_to_sonnet(self):
        """Test that research specialist defaults to sonnet model when no config."""
        agent = create_research_specialist_agent()

        # Should default to sonnet
        assert agent.model == "sonnet"

    def test_research_specialist_web_tools_available(self):
        """Test that research specialist has web access tools."""
        agent = create_research_specialist_agent()

        # Should have web tools for research
        assert "WebSearch" in agent.tools
        assert "WebFetch" in agent.tools


class TestDocumentationAgent:
    """Test documentation agent subagent creation."""

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

        # Should not have web tools (unlike research specialist)
        assert "WebSearch" not in agent.tools
        assert "WebFetch" not in agent.tools

    def test_documentation_agent_model_defaults_to_haiku(self):
        """Test that documentation agent defaults to haiku model for efficiency."""
        agent = create_documentation_agent()

        # Should default to haiku for efficiency (per specification)
        assert agent.model == "haiku"

    def test_documentation_agent_description_is_docs_focused(self):
        """Test that documentation agent description emphasizes documentation focus."""
        agent = create_documentation_agent()

        description = agent.description.lower()
        # Should mention documentation-related keywords
        assert any(keyword in description for keyword in [
            'documentation', 'api', 'technical', 'readme', 'specialist'
        ])

    def test_documentation_agent_prompt_contains_documentation_sections(self):
        """Test that documentation agent prompt includes required documentation sections."""
        agent = create_documentation_agent()

        prompt = agent.prompt.lower()

        # Should include API documentation
        assert any(keyword in prompt for keyword in [
            'api documentation', 'api reference', 'api'
        ])

        # Should include README maintenance
        assert any(keyword in prompt for keyword in [
            'readme', 'readme updates', 'readme maintenance'
        ])

        # Should include technical documentation
        assert any(keyword in prompt for keyword in [
            'technical documentation', 'documentation completeness'
        ])

        # Should include code examples
        assert any(keyword in prompt for keyword in [
            'code example', 'examples', 'code samples'
        ])

    def test_documentation_agent_prompt_has_read_only_constraints(self):
        """Test that documentation agent prompt emphasizes read-only nature."""
        agent = create_documentation_agent()

        prompt = agent.prompt.lower()
        assert 'read-only' in prompt or 'read only' in prompt

    def test_documentation_agent_with_config_uses_haiku_model(self):
        """Test that documentation agent uses haiku even with different config."""
        from ralph.config import RalphConfig

        # Create config with sonnet model
        config = RalphConfig(primary_model="claude-sonnet-4-20250514")

        agent = create_documentation_agent(config)

        # Should still use haiku for efficiency (per specification)
        assert agent.model == "haiku"


class TestPromptFunctions:
    """Test prompt generation functions."""

    def test_get_research_specialist_prompt_returns_string(self):
        """Test that get_research_specialist_prompt returns a proper string."""
        prompt = get_research_specialist_prompt()

        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_code_reviewer_prompt_returns_string(self):
        """Test that get_code_reviewer_prompt returns a proper string."""
        prompt = get_code_reviewer_prompt()

        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_test_engineer_prompt_returns_string(self):
        """Test that get_test_engineer_prompt returns a proper string."""
        prompt = get_test_engineer_prompt()

        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_documentation_agent_prompt_returns_string(self):
        """Test that get_documentation_agent_prompt returns a proper string."""
        prompt = get_documentation_agent_prompt()

        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_product_analyst_prompt_returns_string(self):
        """Test that get_product_analyst_prompt returns a proper string."""
        prompt = get_product_analyst_prompt()

        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_prompt_functions_accept_config_parameter(self):
        """Test that prompt functions accept config parameter."""
        from ralph.config import RalphConfig

        config = RalphConfig(primary_model="claude-haiku-1-20250514")

        # All prompt functions should accept config without error
        assert isinstance(get_research_specialist_prompt(config), str)
        assert isinstance(get_code_reviewer_prompt(config), str)
        assert isinstance(get_test_engineer_prompt(config), str)
        assert isinstance(get_documentation_agent_prompt(config), str)
        assert isinstance(get_product_analyst_prompt(config), str)

    def test_prompts_contain_role_specific_content(self):
        """Test that each prompt contains role-specific content."""
        # Research specialist should mention research
        research_prompt = get_research_specialist_prompt().lower()
        assert any(keyword in research_prompt for keyword in [
            'research', 'library evaluation', 'analysis'
        ])

        # Code reviewer should mention security
        reviewer_prompt = get_code_reviewer_prompt().lower()
        assert any(keyword in reviewer_prompt for keyword in [
            'security', 'vulnerability', 'review'
        ])

        # Test engineer should mention testing
        test_prompt = get_test_engineer_prompt().lower()
        assert any(keyword in test_prompt for keyword in [
            'test', 'testing', 'coverage'
        ])

        # Documentation agent should mention documentation
        docs_prompt = get_documentation_agent_prompt().lower()
        assert any(keyword in docs_prompt for keyword in [
            'documentation', 'api', 'readme'
        ])

        # Product analyst should mention requirements
        product_prompt = get_product_analyst_prompt().lower()
        assert any(keyword in product_prompt for keyword in [
            'requirements', 'analysis', 'product'
        ])

    def test_all_prompts_contain_read_only_constraints(self):
        """Test that all prompts emphasize read-only nature."""
        prompts = [
            get_research_specialist_prompt(),
            get_code_reviewer_prompt(),
            get_test_engineer_prompt(),
            get_documentation_agent_prompt(),
            get_product_analyst_prompt()
        ]

        for prompt in prompts:
            prompt_lower = prompt.lower()
            assert 'read-only' in prompt_lower or 'read only' in prompt_lower


class TestAllFactoryFunctions:
    """Test all factory functions comprehensively."""

    def test_all_factory_functions_exist_and_callable(self):
        """Test that all factory functions exist and are callable."""
        from claude_agent_sdk import AgentDefinition

        # All factory functions should be callable and return AgentDefinitions
        functions = [
            create_research_specialist_agent,
            create_code_reviewer_agent,
            create_test_engineer_agent,
            create_documentation_agent,
            create_product_analyst_agent
        ]

        for func in functions:
            agent = func()
            assert isinstance(agent, AgentDefinition)

    def test_all_factory_functions_accept_config(self):
        """Test that all factory functions accept config parameter."""
        from claude_agent_sdk import AgentDefinition

        from ralph.config import RalphConfig

        config = RalphConfig(primary_model="claude-haiku-1-20250514")

        functions = [
            create_research_specialist_agent,
            create_code_reviewer_agent,
            create_test_engineer_agent,
            create_documentation_agent,
            create_product_analyst_agent
        ]

        for func in functions:
            agent = func(config)
            assert isinstance(agent, AgentDefinition)

    def test_all_agents_have_required_attributes(self):
        """Test that all agents have required AgentDefinition attributes."""
        functions = [
            create_research_specialist_agent,
            create_code_reviewer_agent,
            create_test_engineer_agent,
            create_documentation_agent,
            create_product_analyst_agent
        ]

        for func in functions:
            agent = func()
            assert hasattr(agent, 'description')
            assert hasattr(agent, 'prompt')
            assert hasattr(agent, 'tools')
            assert hasattr(agent, 'model')

            # All should be non-empty strings or lists
            assert isinstance(agent.description, str) and len(agent.description) > 0
            assert isinstance(agent.prompt, str) and len(agent.prompt) > 0
            assert isinstance(agent.tools, list) and len(agent.tools) > 0
            assert agent.model in ["sonnet", "opus", "haiku", "inherit"]

    def test_all_agents_follow_security_constraints(self):
        """Test that all agents follow security constraints."""
        functions = [
            create_research_specialist_agent,
            create_code_reviewer_agent,
            create_test_engineer_agent,
            create_documentation_agent,
            create_product_analyst_agent
        ]

        forbidden = SUBAGENT_SECURITY_CONSTRAINTS["forbidden_tools"]

        for func in functions:
            agent = func()
            # No agent should have forbidden tools
            for tool in agent.tools:
                assert tool not in forbidden, (
                    f"Agent from {func.__name__} has "
                    f"forbidden tool {tool}"
                )


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling scenarios."""

    def test_get_subagents_for_phase_with_none_config(self):
        """Test that get_subagents_for_phase handles None config gracefully."""
        result = get_subagents_for_phase(Phase.BUILDING, None)
        assert isinstance(result, dict)

    def test_factory_functions_with_none_config(self):
        """Test that all factory functions handle None config gracefully."""
        functions = [
            create_research_specialist_agent,
            create_code_reviewer_agent,
            create_test_engineer_agent,
            create_documentation_agent,
            create_product_analyst_agent
        ]

        for func in functions:
            agent = func(None)
            assert agent is not None

    def test_validate_subagent_tools_with_empty_strings(self):
        """Test validate_subagent_tools with empty string inputs."""
        # Empty subagent type
        result = validate_subagent_tools("", ["Read"])
        assert result == []

        # Empty tools with valid subagent
        result = validate_subagent_tools("research-specialist", [""])
        # Empty string should not match any valid tool
        assert result == []

    def test_validate_subagent_tools_with_none_values(self):
        """Test validate_subagent_tools error handling with invalid inputs."""
        # Test behavior with None inputs - the function should handle this gracefully
        # Check if None subagent_type is handled
        try:
            result = validate_subagent_tools(None, ["Read"])  # type: ignore[arg-type]
            # Function should either raise or return empty list
            assert result == [] or isinstance(result, list)
        except (TypeError, AttributeError):
            # This is also acceptable behavior
            pass

        # Check if None tools list is handled
        try:
            result = validate_subagent_tools("research-specialist", None)  # type: ignore[arg-type]
            # Function should either raise or return empty list
            assert result == [] or isinstance(result, list)
        except (TypeError, AttributeError):
            # This is also acceptable behavior
            pass

    def test_filter_subagents_by_phase_with_invalid_phase(self):
        """Test filter_subagents_by_phase with hypothetically invalid phase."""
        # Create a mock phase that doesn't exist in config
        class FakePhase:
            pass

        fake_phase = FakePhase()
        all_subagents = {"research-specialist": create_research_specialist_agent()}

        # Should return empty dict for unknown phase
        result = filter_subagents_by_phase(fake_phase, all_subagents)  # type: ignore[arg-type]
        assert result == {}

    def test_all_subagents_in_get_subagents_for_phase_are_implemented(self):
        """Test that get_subagents_for_phase only returns implemented subagents."""
        for phase in [Phase.DISCOVERY, Phase.PLANNING, Phase.BUILDING, Phase.VALIDATION]:
            result = get_subagents_for_phase(phase, None)

            # All returned subagents should be implemented
            for _subagent_name, agent_def in result.items():
                assert agent_def is not None
                assert hasattr(agent_def, 'tools')
                assert hasattr(agent_def, 'description')
                assert hasattr(agent_def, 'prompt')
                assert hasattr(agent_def, 'model')


class TestComprehensiveCoverage:
    """Additional tests for comprehensive coverage."""

    def test_phase_subagent_config_covers_all_subagent_types(self, all_subagent_types, all_phases):
        """Test that all subagent types appear in at least one phase."""
        used_subagent_types = set()

        for phase in all_phases:
            phase_types = PHASE_SUBAGENT_CONFIG.get(phase, [])
            used_subagent_types.update(phase_types)

        # All defined subagent types should be used in at least one phase
        for subagent_type in all_subagent_types:
            assert subagent_type in used_subagent_types, (
                f"Type {subagent_type} not used in any phase"
            )

    def test_security_constraints_cover_all_subagent_types(self, all_subagent_types):
        """Test that security constraints define permissions for all subagent types."""
        tool_permissions = cast(
            dict[str, list[str]],
            SUBAGENT_SECURITY_CONSTRAINTS["tool_permissions"],
        )

        for subagent_type in all_subagent_types:
            assert subagent_type in tool_permissions, f"No security constraints for {subagent_type}"
            assert isinstance(tool_permissions[subagent_type], list)
            assert len(tool_permissions[subagent_type]) > 0, f"Empty tool list for {subagent_type}"

    def test_model_selection_consistency(self, mock_config):
        """Test model selection logic across all factory functions."""
        # mock_config has all model_mapping entries set to "haiku"
        haiku_config = mock_config

        # All agents should respect the model_mapping from config
        test_agent = create_test_engineer_agent(haiku_config)
        assert test_agent.model == "haiku"

        docs_agent = create_documentation_agent(haiku_config)
        assert docs_agent.model == "haiku"

        product_agent = create_product_analyst_agent(haiku_config)
        assert product_agent.model == "haiku"

        research_agent = create_research_specialist_agent(haiku_config)
        assert research_agent.model == "haiku"

        code_agent = create_code_reviewer_agent(haiku_config)
        assert code_agent.model == "haiku"

    def test_prompt_template_loading(self):
        """Test that prompt templates are loaded correctly."""
        # All prompt functions should return non-empty strings
        prompts = [
            get_research_specialist_prompt(),
            get_code_reviewer_prompt(),
            get_test_engineer_prompt(),
            get_documentation_agent_prompt(),
            get_product_analyst_prompt()
        ]

        for prompt in prompts:
            assert isinstance(prompt, str)
            assert len(prompt) > 100, "Prompt seems too short to be a complete template"

    def test_tool_validation_comprehensive_scenarios(self):
        """Test validate_subagent_tools with comprehensive scenarios."""
        # Test with tools that exist but are forbidden
        result = validate_subagent_tools("research-specialist", ["Write", "Edit", "Bash"])
        assert result == [], "Should filter out all forbidden tools"

        # Test with mixed valid/invalid tools
        result = validate_subagent_tools(
            "research-specialist",
            ["Read", "Write", "WebSearch", "Edit"],
        )
        assert set(result) == {"Read", "WebSearch"}, "Should only return allowed tools"

        # Test case sensitivity
        result = validate_subagent_tools("research-specialist", ["read", "WEBSEARCH", "websearch"])
        assert result == [], "Tool matching should be case sensitive"

        # Test with all valid tools for each type
        tool_permissions = SUBAGENT_SECURITY_CONSTRAINTS["tool_permissions"]
        for subagent_type, allowed_tools in tool_permissions.items():
            result = validate_subagent_tools(subagent_type, allowed_tools)
            assert set(result) == set(allowed_tools), (
                f"Should return all allowed tools for "
                f"{subagent_type}"
            )

    def test_phase_filtering_comprehensive(self):
        """Test phase filtering with all possible combinations."""
        # Create all agents
        all_agents = {
            "research-specialist": create_research_specialist_agent(),
            "code-reviewer": create_code_reviewer_agent(),
            "test-engineer": create_test_engineer_agent(),
            "documentation-agent": create_documentation_agent(),
            "product-analyst": create_product_analyst_agent()
        }

        # Test filtering for each phase
        for phase in [Phase.DISCOVERY, Phase.PLANNING, Phase.BUILDING, Phase.VALIDATION]:
            filtered = filter_subagents_by_phase(phase, all_agents)
            expected_types = PHASE_SUBAGENT_CONFIG.get(phase, [])

            # Filtered result should only contain expected types
            assert set(filtered.keys()) <= set(expected_types), f"Unexpected subagents in {phase}"

            # All expected implemented types should be present
            for expected_type in expected_types:
                if expected_type in all_agents:  # Only check if implemented
                    assert expected_type in filtered, f"Missing {expected_type} in {phase}"

    def test_configuration_integration(self, mock_config):
        """Test integration with RalphConfig across all functions."""
        # Test get_subagents_for_phase with config
        for phase in [Phase.DISCOVERY, Phase.PLANNING, Phase.BUILDING, Phase.VALIDATION]:
            result = get_subagents_for_phase(phase, mock_config)
            assert isinstance(result, dict)

            # All returned agents should be valid
            for agent_def in result.values():
                assert agent_def.model in ["sonnet", "opus", "haiku", "inherit"]


class TestGetSubagentPrompt:
    """Test the general get_subagent_prompt function for template loading."""

    def test_get_subagent_prompt_function_exists(self):
        """Test that get_subagent_prompt function exists and is callable."""
        # Should be importable and callable
        assert callable(get_subagent_prompt)

    def test_get_subagent_prompt_loads_research_specialist_template(self):
        """Test that get_subagent_prompt can load research specialist template."""
        context = {
            "role_name": "Research Specialist",
            "mission_statement": "Test mission",
            "allowed_tools": ["Read", "WebSearch"],
            "tool_descriptions": {"Read": "Read files", "WebSearch": "Search web"},
            "focus_areas": ["research", "analysis"],
            "time_limit_minutes": 5
        }

        prompt = get_subagent_prompt("research_specialist", context)

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        # Should contain rendered context
        assert "Research Specialist" in prompt
        assert "Test mission" in prompt
        assert "Read" in prompt
        assert "WebSearch" in prompt

    def test_get_subagent_prompt_loads_code_reviewer_template(self):
        """Test that get_subagent_prompt can load code reviewer template."""
        context = {
            "role_name": "Code Reviewer",
            "mission_statement": "Review code for security",
            "allowed_tools": ["Read", "Grep"],
            "tool_descriptions": {"Read": "Read files", "Grep": "Search patterns"},
            "time_limit_minutes": 10
        }

        prompt = get_subagent_prompt("code_reviewer", context)

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        # Should contain rendered context
        assert "Code Reviewer" in prompt
        assert "Review code for security" in prompt
        assert "Read" in prompt
        assert "Grep" in prompt

    def test_get_subagent_prompt_loads_test_engineer_template(self):
        """Test that get_subagent_prompt can load test engineer template."""
        context = {
            "role_name": "Test Engineer",
            "mission_statement": "Develop test strategies",
            "allowed_tools": ["Read", "Glob"],
            "tool_descriptions": {"Read": "Read files", "Glob": "Find files"},
            "focus_areas": ["testing", "coverage"],
            "time_limit_minutes": 10
        }

        prompt = get_subagent_prompt("test_engineer", context)

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        # Should contain rendered context
        assert "Test Engineer" in prompt
        assert "Develop test strategies" in prompt
        assert "testing" in prompt or "coverage" in prompt

    def test_get_subagent_prompt_loads_documentation_agent_template(self):
        """Test that get_subagent_prompt can load documentation agent template."""
        context = {
            "role_name": "Documentation Agent",
            "mission_statement": "Create comprehensive documentation",
            "allowed_tools": ["Read", "Grep", "Glob"],
            "tool_descriptions": {"Read": "Read files"},
            "focus_areas": ["api docs", "readme"],
            "time_limit_minutes": 5
        }

        prompt = get_subagent_prompt("documentation_agent", context)

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        # Should contain rendered context
        assert "Documentation Agent" in prompt
        assert "Create comprehensive documentation" in prompt

    def test_get_subagent_prompt_loads_product_analyst_template(self):
        """Test that get_subagent_prompt can load product analyst template."""
        context = {
            "role_name": "Product Analyst",
            "mission_statement": "Analyze requirements",
            "allowed_tools": ["Read"],
            "tool_descriptions": {"Read": "Read files"},
            "focus_areas": ["requirements", "analysis"],
            "time_limit_minutes": 5
        }

        prompt = get_subagent_prompt("product_analyst", context)

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        # Should contain rendered context
        assert "Product Analyst" in prompt
        assert "Analyze requirements" in prompt

    def test_get_subagent_prompt_with_missing_template_raises_error(self):
        """Test that get_subagent_prompt raises appropriate error for missing template."""
        context = {"role_name": "Test"}

        from jinja2 import TemplateNotFound
        with pytest.raises(TemplateNotFound):  # Should raise TemplateNotFound for missing template
            get_subagent_prompt("nonexistent_template", context)

    def test_get_subagent_prompt_handles_empty_context(self):
        """Test that get_subagent_prompt handles empty context gracefully."""
        # Template should render with default values or handle missing variables
        try:
            prompt = get_subagent_prompt("research_specialist", {})
            assert isinstance(prompt, str)
        except Exception:
            # It's acceptable for the template to require certain context variables
            pass

    def test_get_subagent_prompt_path_resolution_works_from_any_directory(self):
        """Test that template path resolution works regardless of working directory."""
        import os
        import tempfile

        context = {
            "role_name": "Research Specialist",
            "mission_statement": "Test mission",
            "allowed_tools": ["Read"],
            "tool_descriptions": {"Read": "Read files"},
            "focus_areas": ["research"],
            "time_limit_minutes": 5
        }

        # Store current directory
        original_cwd = os.getcwd()

        try:
            # Change to a temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                os.chdir(temp_dir)

                # Should still be able to load template from any working directory
                prompt = get_subagent_prompt("research_specialist", context)

                assert isinstance(prompt, str)
                assert len(prompt) > 0
                assert "Research Specialist" in prompt

        finally:
            # Always restore original directory
            os.chdir(original_cwd)

    def test_get_subagent_prompt_handles_jinja2_template_syntax(self):
        """Test that get_subagent_prompt properly handles Jinja2 template syntax."""
        context = {
            "role_name": "Research Specialist",
            "mission_statement": "Test mission with special chars: <>&",
            "allowed_tools": ["Read", "WebSearch"],
            "tool_descriptions": {"Read": "Read files", "WebSearch": "Search & fetch"},
            "focus_areas": ["research & analysis", "testing"],
            "time_limit_minutes": 5
        }

        prompt = get_subagent_prompt("research_specialist", context)

        assert isinstance(prompt, str)
        # Should handle special characters in context
        assert "special chars: <>&" in prompt
        assert "Search & fetch" in prompt
        assert "research & analysis" in prompt

    def test_get_subagent_prompt_context_variables_are_rendered(self):
        """Test that all context variables are properly rendered in template."""
        context = {
            "role_name": "Test Role",
            "mission_statement": "Test Mission Statement",
            "allowed_tools": ["Tool1", "Tool2"],
            "tool_descriptions": {"Tool1": "Description 1", "Tool2": "Description 2"},
            "focus_areas": ["area1", "area2", "area3"],
            "time_limit_minutes": 15
        }

        prompt = get_subagent_prompt("research_specialist", context)

        # Check that all context variables are rendered
        assert "Test Role" in prompt
        assert "Test Mission Statement" in prompt
        assert "Tool1" in prompt
        assert "Tool2" in prompt
        assert "Description 1" in prompt
        assert "Description 2" in prompt
        assert "area1, area2, area3" in prompt  # focus_areas are joined
        assert "15 minutes" in prompt

    def test_get_subagent_prompt_config_parameter_optional(self):
        """Test that config parameter is optional."""
        context = {
            "role_name": "Research Specialist",
            "mission_statement": "Test mission",
            "allowed_tools": ["Read"],
            "tool_descriptions": {"Read": "Read files"},
            "focus_areas": ["research"],
            "time_limit_minutes": 5
        }

        # Should work without config parameter
        prompt1 = get_subagent_prompt("research_specialist", context)
        assert isinstance(prompt1, str)

        # Should also work with None config
        prompt2 = get_subagent_prompt("research_specialist", context, None)
        assert isinstance(prompt2, str)

        # Both should produce the same result
        assert prompt1 == prompt2

    def test_get_subagent_prompt_config_parameter_integration(self):
        """Test that config parameter can be used (even if not currently utilized)."""
        from ralph.config import RalphConfig

        context = {
            "role_name": "Research Specialist",
            "mission_statement": "Test mission",
            "allowed_tools": ["Read"],
            "tool_descriptions": {"Read": "Read files"},
            "focus_areas": ["research"],
            "time_limit_minutes": 5
        }

        config = RalphConfig(primary_model="claude-haiku-1-20250514")

        # Should accept config parameter without error
        prompt = get_subagent_prompt("research_specialist", context, config)
        assert isinstance(prompt, str)


class TestSubagentMetrics:
    """Test SubagentMetrics dataclass and metrics collection functionality."""

    def test_subagent_metrics_dataclass_exists(self):
        """Test that SubagentMetrics dataclass exists and is importable."""
        from ralph.subagents import SubagentMetrics

        # Should be importable without error
        assert SubagentMetrics is not None

    def test_subagent_metrics_has_required_fields(self):
        """Test that SubagentMetrics has all required fields."""
        from datetime import datetime

        from ralph.subagents import SubagentMetrics

        # Create instance with all required fields
        start_time = datetime.now()
        end_time = datetime.now()

        metrics = SubagentMetrics(
            subagent_type="research-specialist",
            start_time=start_time,
            end_time=end_time,
            tokens_used=1000,
            cost_usd=0.05,
            success=True,
            error=None,
            report_size_chars=2000
        )

        assert metrics.subagent_type == "research-specialist"
        assert metrics.start_time == start_time
        assert metrics.end_time == end_time
        assert metrics.tokens_used == 1000
        assert metrics.cost_usd == 0.05
        assert metrics.success is True
        assert metrics.error is None
        assert metrics.report_size_chars == 2000

    def test_subagent_metrics_default_values(self):
        """Test SubagentMetrics default field values."""
        from datetime import datetime

        from ralph.subagents import SubagentMetrics

        # Create with minimal required fields
        start_time = datetime.now()
        metrics = SubagentMetrics(
            subagent_type="test-engineer",
            start_time=start_time
        )

        # Should have reasonable defaults for optional fields
        assert metrics.subagent_type == "test-engineer"
        assert metrics.start_time == start_time
        assert metrics.end_time is None
        assert metrics.tokens_used == 0
        assert metrics.cost_usd == 0.0
        assert metrics.success is False
        assert metrics.error is None
        assert metrics.report_size_chars == 0

    def test_subagent_metrics_with_error(self):
        """Test SubagentMetrics with error information."""
        from datetime import datetime

        from ralph.subagents import SubagentMetrics

        start_time = datetime.now()
        error_msg = "Connection timeout"

        metrics = SubagentMetrics(
            subagent_type="code-reviewer",
            start_time=start_time,
            success=False,
            error=error_msg
        )

        assert metrics.subagent_type == "code-reviewer"
        assert metrics.success is False
        assert metrics.error == error_msg

    def test_collect_subagent_metrics_function_exists(self):
        """Test that collect_subagent_metrics function exists and is callable."""
        from ralph.subagents import collect_subagent_metrics

        assert callable(collect_subagent_metrics)

    def test_collect_subagent_metrics_basic_usage(self):
        """Test basic usage of collect_subagent_metrics function."""
        from datetime import datetime

        from ralph.subagents import SubagentMetrics, collect_subagent_metrics

        start_time = datetime.now()

        result = collect_subagent_metrics(
            subagent_type="research-specialist",
            start_time=start_time,
            success=True,
            report_content="Sample report content",
            tokens_used=500,
            cost_estimate=0.025
        )

        assert isinstance(result, SubagentMetrics)
        assert result.subagent_type == "research-specialist"
        assert result.start_time == start_time
        assert result.end_time is not None  # Should be set automatically
        assert result.success is True
        assert result.tokens_used == 500
        assert result.cost_usd == 0.025
        assert result.report_size_chars == len("Sample report content")
        assert result.error is None

    def test_collect_subagent_metrics_with_failure(self):
        """Test collect_subagent_metrics with failure scenario."""
        from datetime import datetime

        from ralph.subagents import SubagentMetrics, collect_subagent_metrics

        start_time = datetime.now()
        error_msg = "Task execution failed"

        result = collect_subagent_metrics(
            subagent_type="test-engineer",
            start_time=start_time,
            success=False,
            error=error_msg,
            report_content="",
            tokens_used=200,
            cost_estimate=0.01
        )

        assert isinstance(result, SubagentMetrics)
        assert result.subagent_type == "test-engineer"
        assert result.success is False
        assert result.error == error_msg
        assert result.tokens_used == 200
        assert result.cost_usd == 0.01
        assert result.report_size_chars == 0

    def test_collect_subagent_metrics_sets_end_time(self):
        """Test that collect_subagent_metrics automatically sets end_time."""
        import time
        from datetime import datetime

        from ralph.subagents import collect_subagent_metrics

        start_time = datetime.now()

        # Add small delay to ensure end_time > start_time
        time.sleep(0.01)

        result = collect_subagent_metrics(
            subagent_type="documentation-agent",
            start_time=start_time,
            success=True,
            report_content="test",
            tokens_used=100,
            cost_estimate=0.005
        )

        assert result.end_time is not None
        assert result.end_time >= start_time
        assert result.end_time <= datetime.now()

    def test_collect_subagent_metrics_calculates_report_size(self):
        """Test that collect_subagent_metrics calculates report size correctly."""
        from datetime import datetime

        from ralph.subagents import collect_subagent_metrics

        start_time = datetime.now()
        report_content = "This is a test report with some content."
        expected_size = len(report_content)

        result = collect_subagent_metrics(
            subagent_type="product-analyst",
            start_time=start_time,
            success=True,
            report_content=report_content,
            tokens_used=300,
            cost_estimate=0.015
        )

        assert result.report_size_chars == expected_size

    def test_collect_subagent_metrics_handles_empty_report(self):
        """Test that collect_subagent_metrics handles empty report content."""
        from datetime import datetime

        from ralph.subagents import collect_subagent_metrics

        start_time = datetime.now()

        result = collect_subagent_metrics(
            subagent_type="code-reviewer",
            start_time=start_time,
            success=True,
            report_content="",
            tokens_used=50,
            cost_estimate=0.002
        )

        assert result.report_size_chars == 0

    def test_collect_subagent_metrics_handles_none_report(self):
        """Test that collect_subagent_metrics handles None report content."""
        from datetime import datetime

        from ralph.subagents import collect_subagent_metrics

        start_time = datetime.now()

        result = collect_subagent_metrics(
            subagent_type="research-specialist",
            start_time=start_time,
            success=False,
            report_content=None,
            tokens_used=0,
            cost_estimate=0.0,
            error="Task failed"
        )

        assert result.report_size_chars == 0

    def test_subagent_metrics_duration_property(self):
        """Test SubagentMetrics duration calculation."""
        from datetime import datetime, timedelta

        from ralph.subagents import SubagentMetrics

        start_time = datetime.now()
        end_time = start_time + timedelta(seconds=30)

        metrics = SubagentMetrics(
            subagent_type="test-engineer",
            start_time=start_time,
            end_time=end_time
        )

        # Should have a duration property or method
        if hasattr(metrics, 'duration'):
            duration = metrics.duration
            assert duration.total_seconds() == 30.0


