"""Subagent configuration module for Ralph.

Provides Claude Agent SDK AgentDefinition configurations for specialized
subagents that operate within Ralph's phase-based architecture. All subagents
are designed with read-only access to ensure security and maintain the principle
that only the main Ralph agent can make modifications to the codebase.

This module houses all subagent factory functions and phase-specific configuration
for the Claude Agent SDK integration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from claude_agent_sdk import AgentDefinition
from jinja2 import Environment, FileSystemLoader

from ralph.models import Phase

if TYPE_CHECKING:
    from ralph.config import RalphConfig

# Set up logger for structured error logging
logger = logging.getLogger(__name__)

# Resolve the templates directory once at module level
_TEMPLATES_DIR = Path(__file__).parent / "templates" / "subagents"


def _map_model_to_sdk(ralph_model: str) -> Literal["sonnet", "opus", "haiku", "inherit"]:
    """Map Ralph model name strings to SDK literal model types.

    Args:
        ralph_model: Model name string (e.g., "sonnet", "claude-sonnet-4-20250514")

    Returns:
        SDK-compatible model literal
    """
    lower = ralph_model.lower()
    if "sonnet" in lower:
        return "sonnet"
    elif "opus" in lower:
        return "opus"
    elif "haiku" in lower:
        return "haiku"
    return "sonnet"  # Default fallback


def _get_model_for_subagent(
    subagent_type: str, config: RalphConfig | None, default: str = "sonnet"
) -> Literal["sonnet", "opus", "haiku", "inherit"]:
    """Get the SDK model literal for a subagent, reading from config.subagents.model_mapping.

    Args:
        subagent_type: Subagent type key (e.g., "research-specialist")
        config: Ralph configuration (optional)
        default: Default model name if config is not available

    Returns:
        SDK-compatible model literal
    """
    ralph_model = config.subagents.model_mapping.get(subagent_type, default) if config else default
    return _map_model_to_sdk(ralph_model)


class SubagentExecutionError(Exception):
    """Exception raised when subagent execution fails.

    This exception provides structured error information for subagent failures,
    including the subagent type and original exception for debugging purposes.
    Used for timeout handling, retry logic, and graceful degradation.

    Attributes:
        subagent_type: The type of subagent that failed (optional)
        original_exception: The original exception that caused the failure (optional)
    """

    def __init__(
        self,
        message: str,
        subagent_type: str | None = None,
        original_exception: Exception | None = None
    ):
        """Initialize SubagentExecutionError.

        Args:
            message: Error description
            subagent_type: Type of subagent that failed (e.g., "research-specialist")
            original_exception: Original exception that caused the failure
        """
        super().__init__(message)
        self.subagent_type = subagent_type
        self.original_exception = original_exception


# Security constraints defining forbidden tools and tool permissions for each subagent type
SUBAGENT_SECURITY_CONSTRAINTS: dict[str, list[str] | dict[str, list[str]]] = {
    # No subagent gets write access or ability to execute dangerous operations
    "forbidden_tools": ["Write", "Edit", "NotebookEdit", "Bash", "Task"],

    # Tool permissions by subagent type - all are read-only for security
    "tool_permissions": {
        "research-specialist": ["Read", "Grep", "Glob", "WebSearch", "WebFetch"],
        "code-reviewer": ["Read", "Grep", "Glob"],
        "test-engineer": ["Read", "Grep", "Glob"],
        "documentation-agent": ["Read", "Grep", "Glob"],
        "product-analyst": ["Read", "Grep", "Glob"],
    }
}

# Phase-specific subagent configuration mapping
# Maps each Ralph development phase to the list of subagent types appropriate for that phase
PHASE_SUBAGENT_CONFIG: dict[Phase, list[str]] = {
    # Discovery Phase: Focus on gathering requirements and understanding the problem domain
    Phase.DISCOVERY: [
        "research-specialist",  # Essential for gathering technical requirements and solutions
        "product-analyst",      # Critical for understanding user needs and business requirements
        "documentation-agent",  # Helpful for analyzing existing documentation and specs
    ],

    # Planning Phase: Focus on technical architecture and implementation strategy
    Phase.PLANNING: [
        "research-specialist",  # Essential for evaluating technologies and architectural patterns
        "documentation-agent",  # Helpful for creating architecture documentation and specs
    ],

    # Building Phase: Focus on implementation with quality assurance
    Phase.BUILDING: [
        "test-engineer",        # Critical for TDD support and ensuring test coverage
        "code-reviewer",        # Essential for maintaining code quality and security standards
        "research-specialist",  # Useful for resolving implementation questions and finding patterns
    ],

    # Validation Phase: Focus on quality assurance and final review
    Phase.VALIDATION: [
        "code-reviewer",        # Essential for comprehensive security and quality review
        "test-engineer",        # Critical for running comprehensive test suites and validation
        "documentation-agent",  # Helpful for ensuring documentation is complete and accurate
    ],
}


def validate_subagent_tools(subagent_type: str, requested_tools: list[str]) -> list[str]:
    """Validate and filter requested tools for a subagent to enforce security constraints.

    This function implements the core security mechanism for Ralph's subagent system.
    It ensures that no subagent can gain access to dangerous tools like Write, Edit,
    Bash, or Task, which could compromise the security of the codebase or allow
    nested subagent spawning.

    Args:
        subagent_type: The type of subagent requesting tools (e.g., "research-specialist")
        requested_tools: List of tool names being requested by the subagent

    Returns:
        List of validated tools that are safe and allowed for the specific subagent type.
        Only returns tools that are:
        1. Not in the SUBAGENT_SECURITY_CONSTRAINTS["forbidden_tools"] list
        2. Explicitly allowed for the subagent type in tool_permissions mapping
        3. Preserves the original order of allowed tools from the request

    Security Guarantees:
        - No subagent can access Write, Edit, NotebookEdit, Bash, or Task tools
        - Each subagent type only gets tools explicitly configured for its role
        - Unknown subagent types receive no tools (fail-safe behavior)
        - Duplicate tools in the request are deduplicated

    Example:
        # Research specialist requesting various tools
        tools = validate_subagent_tools(
            "research-specialist",
            ["Read", "Write", "WebSearch", "Bash"]
        )
        # Returns: ["Read", "WebSearch"] - dangerous tools filtered out

        # Code reviewer requesting tools beyond its permissions
        tools = validate_subagent_tools(
            "code-reviewer",
            ["Read", "Grep", "WebSearch", "Edit"]
        )
        # Returns: ["Read", "Grep"] - only tools allowed for code reviewer
    """
    # Get the forbidden tools that no subagent should ever have
    forbidden_tools = cast(list[str], SUBAGENT_SECURITY_CONSTRAINTS["forbidden_tools"])

    # Get the tool permissions mapping for all subagent types
    tool_permissions = cast(dict[str, list[str]], SUBAGENT_SECURITY_CONSTRAINTS["tool_permissions"])

    # If subagent type is unknown, return empty list (fail-safe)
    if subagent_type not in tool_permissions:
        return []

    # Get allowed tools for this specific subagent type
    allowed_tools_for_type = tool_permissions[subagent_type]

    # Filter requested tools to only include those that are:
    # 1. Not forbidden globally
    # 2. Allowed for this specific subagent type
    # 3. Preserve order and deduplicate
    validated_tools: list[str] = []
    seen_tools: set[str] = set()

    for tool in requested_tools:
        if (
            tool not in forbidden_tools and
            tool in allowed_tools_for_type and
            tool not in seen_tools
        ):
            validated_tools.append(tool)
            seen_tools.add(tool)

    return validated_tools


def filter_subagents_by_phase(
    phase: Phase, all_subagents: dict[str, AgentDefinition]
) -> dict[str, AgentDefinition]:
    """Filter subagents to only those appropriate for the given phase.

    This function implements phase-specific subagent filtering based on the PHASE_SUBAGENT_CONFIG
    mapping. It ensures that only relevant subagents are available during each Ralph phase,
    improving focus and reducing unnecessary context switching.

    Args:
        phase: The current Ralph development phase
        all_subagents: Dictionary mapping subagent names to AgentDefinition objects

    Returns:
        Dictionary containing only the subagents configured for the specified phase

    Example:
        # Get all available subagents
        all_agents = {
            "research-specialist": create_research_specialist_agent(),
            "code-reviewer": create_code_reviewer_agent(),
            "test-engineer": create_test_engineer_agent(),
        }

        # Filter for building phase
        building_agents = filter_subagents_by_phase(Phase.BUILDING, all_agents)
        # Returns only test-engineer, code-reviewer, and research-specialist
    """
    # Get the list of subagent types configured for this phase
    phase_subagent_types = PHASE_SUBAGENT_CONFIG.get(phase, [])

    # Filter the all_subagents dict to only include phase-appropriate subagents
    filtered_subagents = {
        subagent_name: agent_definition
        for subagent_name, agent_definition in all_subagents.items()
        if subagent_name in phase_subagent_types
    }

    return filtered_subagents


def get_subagent_prompt(
    template_name: str,
    context: dict[str, Any],
    config: RalphConfig | None = None
) -> str:
    """Load and render a Jinja2 template for any subagent.

    This is the general template loading function that can load any subagent template
    from the src/ralph/templates/subagents/ directory, render it with the provided
    context, and handle template not found errors gracefully.

    Args:
        template_name: Name of the template file (without .jinja extension)
        context: Dictionary of context variables to render the template with
        config: Ralph configuration (optional, uses defaults if None)

    Returns:
        Rendered prompt string from Jinja2 template

    Raises:
        jinja2.TemplateNotFound: If the specified template file does not exist
        jinja2.TemplateError: If there are template syntax errors or rendering issues

    Example:
        context = {
            "role_name": "Research Specialist",
            "mission_statement": "Conduct deep technical analysis...",
            "allowed_tools": ["Read", "WebSearch", "WebFetch"],
            "tool_descriptions": {"Read": "Read files", ...},
            "focus_areas": ["library evaluation", "pattern research"],
            "time_limit_minutes": 5
        }
        prompt = get_subagent_prompt("research_specialist", context)
    """
    # Get the templates directory using absolute path resolution
    # This ensures it works regardless of current working directory
    current_file = Path(__file__)
    templates_dir = current_file.parent / "templates" / "subagents"

    # Set up Jinja2 environment with FileSystemLoader
    env = Environment(loader=FileSystemLoader(templates_dir))

    # Load the template (will raise TemplateNotFound if template doesn't exist)
    template_filename = f"{template_name}.jinja"
    template = env.get_template(template_filename)

    # Render the template with provided context
    return template.render(**context)


def get_research_specialist_prompt(config: RalphConfig | None = None) -> str:
    """Load and render the research specialist prompt template.

    Args:
        config: Ralph configuration (optional, uses defaults if None)

    Returns:
        Rendered prompt string from Jinja2 template
    """

    # Define allowed tools for research specialist
    allowed_tools = ["Read", "Grep", "Glob", "WebSearch", "WebFetch"]

    # Tool descriptions mapping
    tool_descriptions = {
        "Read": "Read file contents and documentation",
        "Grep": "Search for patterns within files",
        "Glob": "Find files matching patterns",
        "WebSearch": "Search the web for information and documentation",
        "WebFetch": "Retrieve specific web pages and documentation"
    }

    # Template variables
    context = {
        "role_name": "Research Specialist",
        "mission_statement": (
            "Conduct deep technical analysis, library evaluation, pattern research, "
            "and technology comparison to provide evidence-based recommendations for "
            "architectural decisions."
        ),
        "allowed_tools": allowed_tools,
        "tool_descriptions": tool_descriptions,
        "focus_areas": [
            "library evaluation",
            "pattern research",
            "technology comparison",
            "best practices synthesis",
            "risk assessment"
        ],
        "time_limit_minutes": 5
    }

    return get_subagent_prompt("research_specialist", context, config)


def create_research_specialist_agent(config: RalphConfig | None = None) -> AgentDefinition:
    """Create an AgentDefinition for the research specialist subagent.

    Args:
        config: Ralph configuration (optional, uses defaults if None)

    Returns:
        AgentDefinition configured for research specialist with proper tools and prompt
    """
    # Get the rendered prompt
    prompt = get_research_specialist_prompt(config)

    # Define allowed tools from security constraints
    tool_permissions = cast(dict[str, list[str]], SUBAGENT_SECURITY_CONSTRAINTS["tool_permissions"])
    allowed_tools = tool_permissions["research-specialist"]

    # Get model from config.subagents.model_mapping
    model = _get_model_for_subagent("research-specialist", config, default="sonnet")

    return AgentDefinition(
        description=(
            "Expert research specialist for deep technical analysis, "
            "library evaluation, and pattern research"
        ),
        prompt=prompt,
        tools=allowed_tools,
        model=model
    )


def get_code_reviewer_prompt(config: RalphConfig | None = None) -> str:
    """Load and render the code reviewer prompt template.

    Args:
        config: Ralph configuration (optional, uses defaults if None)

    Returns:
        Rendered prompt string from Jinja2 template
    """

    # Define allowed tools for code reviewer (read-only analysis)
    allowed_tools = ["Read", "Grep", "Glob"]

    # Tool descriptions mapping
    tool_descriptions = {
        "Read": "Read file contents for security and quality analysis",
        "Grep": "Search for security patterns and vulnerability indicators",
        "Glob": "Find files matching security-relevant patterns"
    }

    # Template variables
    context = {
        "role_name": "Code Security Reviewer",
        "mission_statement": (
            "Conduct comprehensive security vulnerability analysis, code quality assessment, "
            "and architecture consistency review to ensure production-ready, secure code that "
            "adheres to industry best practices and organizational standards."
        ),
        "allowed_tools": allowed_tools,
        "tool_descriptions": tool_descriptions,
        "time_limit_minutes": 10  # Longer time for thorough security analysis
    }

    return get_subagent_prompt("code_reviewer", context, config)


def create_code_reviewer_agent(config: RalphConfig | None = None) -> AgentDefinition:
    """Create an AgentDefinition for the code reviewer subagent.

    Args:
        config: Ralph configuration (optional, uses defaults if None)

    Returns:
        AgentDefinition configured for code reviewer with security-focused tools and prompt
    """
    # Get the rendered prompt
    prompt = get_code_reviewer_prompt(config)

    # Define allowed tools from security constraints (read-only)
    tool_permissions = cast(dict[str, list[str]], SUBAGENT_SECURITY_CONSTRAINTS["tool_permissions"])
    allowed_tools = tool_permissions["code-reviewer"]

    # Get model from config.subagents.model_mapping
    model = _get_model_for_subagent("code-reviewer", config, default="sonnet")

    return AgentDefinition(
        description=(
            "Expert security-focused code reviewer for vulnerability analysis, "
            "code quality assessment, and architecture consistency validation"
        ),
        prompt=prompt,
        tools=allowed_tools,
        model=model
    )


def get_test_engineer_prompt(config: RalphConfig | None = None) -> str:
    """Load and render the test engineer prompt template.

    Args:
        config: Ralph configuration (optional, uses defaults if None)

    Returns:
        Rendered prompt string from Jinja2 template
    """

    # Define allowed tools for test engineer (read-only analysis)
    allowed_tools = ["Read", "Grep", "Glob"]

    # Tool descriptions mapping
    tool_descriptions = {
        "Read": "Read file contents for test strategy development",
        "Grep": "Search for existing tests and testing patterns",
        "Glob": "Find test files and testing configuration"
    }

    # Template variables
    template_vars = {
        "role_name": "Test Engineer",
        "mission_statement": (
            "Develop comprehensive test strategies, ensure robust test coverage, and provide "
            "quality validation approaches using agentic AI testing patterns to achieve "
            "production-ready software with predictive quality intelligence."
        ),
        "allowed_tools": allowed_tools,
        "tool_descriptions": tool_descriptions,
        "focus_areas": [
            "test strategy development",
            "coverage analysis",
            "edge case identification",
            "test prioritization",
            "quality validation"
        ],
        "time_limit_minutes": 10
    }

    return get_subagent_prompt("test_engineer", template_vars, config)


def create_test_engineer_agent(config: RalphConfig | None = None) -> AgentDefinition:
    """Create an AgentDefinition for the test engineer subagent.

    Args:
        config: Ralph configuration (optional, uses defaults if None)

    Returns:
        AgentDefinition configured for test engineer with read-only tools and prompt
    """
    # Get the rendered prompt
    prompt = get_test_engineer_prompt(config)

    # Define allowed tools from security constraints (read-only)
    tool_permissions = cast(dict[str, list[str]], SUBAGENT_SECURITY_CONSTRAINTS["tool_permissions"])
    allowed_tools = tool_permissions["test-engineer"]

    # Get model from config.subagents.model_mapping (defaults to sonnet)
    model = _get_model_for_subagent("test-engineer", config, default="sonnet")

    return AgentDefinition(
        description=(
            "Expert test engineering specialist for comprehensive test strategy development, "
            "coverage analysis, and quality validation using agentic AI testing patterns"
        ),
        prompt=prompt,
        tools=allowed_tools,
        model=model
    )


def get_documentation_agent_prompt(config: RalphConfig | None = None) -> str:
    """Load and render the documentation agent prompt template.

    Args:
        config: Ralph configuration (optional, uses defaults if None)

    Returns:
        Rendered prompt string from Jinja2 template
    """

    # Define allowed tools for documentation agent (read-only analysis)
    allowed_tools = ["Read", "Grep", "Glob"]

    # Tool descriptions mapping
    tool_descriptions = {
        "Read": "Read file contents for documentation analysis and content review",
        "Grep": "Search for existing documentation patterns and content structure",
        "Glob": "Find documentation files and analyze documentation organization"
    }

    # Template variables
    template_vars = {
        "role_name": "Documentation Agent",
        "mission_statement": (
            "Create comprehensive technical documentation, API reference generation, "
            "and intelligent content maintenance to ensure clear project knowledge "
            "and effective developer onboarding."
        ),
        "allowed_tools": allowed_tools,
        "tool_descriptions": tool_descriptions,
        "focus_areas": [
            "api documentation generation",
            "technical documentation completeness",
            "readme updates",
            "code example generation",
            "documentation standards compliance"
        ],
        "time_limit_minutes": 5  # Cost-efficient time limit
    }

    return get_subagent_prompt("documentation_agent", template_vars, config)


def create_documentation_agent(config: RalphConfig | None = None) -> AgentDefinition:
    """Create an AgentDefinition for the documentation agent subagent.

    Args:
        config: Ralph configuration (optional, uses defaults if None)

    Returns:
        AgentDefinition configured for documentation agent with read-only tools and haiku model
    """
    # Get the rendered prompt
    prompt = get_documentation_agent_prompt(config)

    # Define allowed tools from security constraints (read-only)
    tool_permissions = cast(dict[str, list[str]], SUBAGENT_SECURITY_CONSTRAINTS["tool_permissions"])
    allowed_tools = tool_permissions["documentation-agent"]

    # Get model from config.subagents.model_mapping (defaults to haiku)
    model = _get_model_for_subagent("documentation-agent", config, default="haiku")

    return AgentDefinition(
        description=(
            "Expert documentation specialist for API documentation generation, "
            "technical documentation completeness, and README maintenance"
        ),
        prompt=prompt,
        tools=allowed_tools,
        model=model
    )


def get_product_analyst_prompt(config: RalphConfig | None = None) -> str:
    """Load and render the product analyst prompt template.

    Args:
        config: Ralph configuration (optional, uses defaults if None)

    Returns:
        Rendered prompt string from Jinja2 template
    """

    # Define allowed tools for product analyst (read-only analysis)
    allowed_tools = ["Read", "Grep", "Glob"]

    # Tool descriptions mapping
    tool_descriptions = {
        "Read": "Read file contents for requirements analysis and specification review",
        "Grep": "Search for existing requirements patterns and specification content",
        "Glob": "Find specification files and analyze requirements organization"
    }

    # Template variables
    template_vars = {
        "role_name": "Product Analyst",
        "mission_statement": (
            "Analyze requirements clarity, validate acceptance criteria, and identify edge cases "
            "to ensure clear, actionable requirements that guide effective technical development "
            "and stakeholder alignment."
        ),
        "allowed_tools": allowed_tools,
        "tool_descriptions": tool_descriptions,
        "focus_areas": [
            "requirements quality assessment",
            "user story validation",
            "acceptance criteria analysis",
            "stakeholder perspective evaluation",
            "edge case identification",
            "research guidance generation"
        ],
        "time_limit_minutes": 5  # Cost-efficient time limit for requirements analysis
    }

    return get_subagent_prompt("product_analyst", template_vars, config)


def create_product_analyst_agent(config: RalphConfig | None = None) -> AgentDefinition:
    """Create an AgentDefinition for the product analyst subagent.

    Args:
        config: Ralph configuration (optional, uses defaults if None)

    Returns:
        AgentDefinition configured for product analyst with read-only tools and haiku model
    """
    # Get the rendered prompt
    prompt = get_product_analyst_prompt(config)

    # Define allowed tools from security constraints (read-only)
    tool_permissions = cast(dict[str, list[str]], SUBAGENT_SECURITY_CONSTRAINTS["tool_permissions"])
    allowed_tools = tool_permissions["product-analyst"]

    # Get model from config.subagents.model_mapping (defaults to haiku)
    model = _get_model_for_subagent("product-analyst", config, default="haiku")

    return AgentDefinition(
        description=(
            "Expert product analyst for requirements clarity assessment, acceptance criteria "
            "validation, and edge case identification with stakeholder perspective analysis"
        ),
        prompt=prompt,
        tools=allowed_tools,
        model=model
    )


def get_subagents_for_phase(
    phase: Phase, config: RalphConfig | None = None
) -> dict[str, AgentDefinition]:
    """Create all available subagent definitions and return phase-appropriate ones.

    This is the main entry point that RalphSDKClient will call to get subagents
    for a specific phase. It instantiates all implemented factory functions,
    then uses filter_subagents_by_phase() to return only the appropriate ones.

    Args:
        phase: Current Ralph phase
        config: Ralph configuration (optional, uses defaults if None)

    Returns:
        Dictionary mapping subagent names to AgentDefinition objects for the given phase
        Only includes subagents that are both:
        1. Configured for the specified phase in PHASE_SUBAGENT_CONFIG
        2. Actually implemented (have factory functions available)

    Example:
        # Get subagents for building phase
        building_subagents = get_subagents_for_phase(Phase.BUILDING, config)
        # Returns: {
        #     "code-reviewer": AgentDefinition(...),
        #     "research-specialist": AgentDefinition(...)
        # }
    """
    # Create all available subagent definitions using their factory functions
    all_subagents: dict[str, AgentDefinition] = {}

    # Factory map: subagent type -> factory function
    factories: dict[str, Any] = {
        "research-specialist": create_research_specialist_agent,
        "code-reviewer": create_code_reviewer_agent,
        "test-engineer": create_test_engineer_agent,
        "documentation-agent": create_documentation_agent,
        "product-analyst": create_product_analyst_agent,
    }

    for subagent_type, factory in factories.items():
        try:
            all_subagents[subagent_type] = factory(config)
        except Exception:
            logger.warning(
                "Failed to create subagent '%s' — it will be unavailable this phase",
                subagent_type,
                exc_info=True,
            )

    # Filter to only include subagents appropriate for the current phase
    return filter_subagents_by_phase(phase, all_subagents)


@dataclass
class SubagentMetrics:
    """Metrics for tracking subagent execution performance and costs.

    This dataclass captures comprehensive metrics about subagent execution
    to enable cost tracking, performance analysis, and debugging of the
    subagent system within Ralph's architecture.

    Attributes:
        subagent_type: The type of subagent (e.g., "research-specialist")
        start_time: When the subagent execution began
        end_time: When the subagent execution completed (None if still running)
        tokens_used: Total tokens consumed during execution
        cost_usd: Estimated cost in USD for the execution
        success: Whether the subagent execution was successful
        error: Error message if execution failed (None if successful)
        report_size_chars: Size of the generated report in characters
    """

    subagent_type: str
    start_time: datetime
    end_time: datetime | None = None
    tokens_used: int = 0
    cost_usd: float = 0.0
    success: bool = False
    error: str | None = None
    report_size_chars: int = 0

    @property
    def duration(self) -> timedelta | None:
        """Calculate execution duration if both start and end times are set."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None


def collect_subagent_metrics(
    subagent_type: str,
    start_time: datetime,
    success: bool,
    report_content: str | None = None,
    tokens_used: int = 0,
    cost_estimate: float = 0.0,
    error: str | None = None
) -> SubagentMetrics:
    """Collect and aggregate metrics for a subagent execution.

    This function creates a SubagentMetrics instance with the provided execution
    data, automatically setting the end time and calculating report size.
    It's designed to be called after subagent execution completes to capture
    comprehensive metrics for cost tracking and performance analysis.

    Args:
        subagent_type: Type of subagent that was executed
        start_time: When the execution began
        success: Whether the execution was successful
        report_content: The content generated by the subagent (optional)
        tokens_used: Number of tokens consumed during execution
        cost_estimate: Estimated cost in USD
        error: Error message if execution failed

    Returns:
        SubagentMetrics instance with all collected data

    Example:
        start = datetime.now()
        # ... execute subagent ...
        metrics = collect_subagent_metrics(
            subagent_type="research-specialist",
            start_time=start,
            success=True,
            report_content=report,
            tokens_used=1500,
            cost_estimate=0.075
        )
    """
    # Calculate report size, handling None content
    report_size = len(report_content) if report_content else 0

    return SubagentMetrics(
        subagent_type=subagent_type,
        start_time=start_time,
        end_time=datetime.now(),  # Set completion time automatically
        tokens_used=tokens_used,
        cost_usd=cost_estimate,
        success=success,
        error=error,
        report_size_chars=report_size
    )


