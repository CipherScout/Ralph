# Ralph Subagents

Ralph includes specialized AI subagents that provide domain expertise during different phases of the development workflow. These subagents operate with read-only access and are designed to augment the main Ralph agent with specialized knowledge and capabilities.

## Overview

Subagents are automatically available based on the current Ralph phase and can be invoked through the `Task` tool. Each subagent has:

- **Specialized domain expertise** for specific types of analysis or work
- **Phase-specific availability** to ensure relevant skills are accessible when needed
- **Read-only security constraints** to prevent unauthorized modifications
- **Consistent report format** for reliable integration with Ralph's workflow

## Available Subagents

### Research Specialist

**Purpose**: Conduct deep technical analysis, library evaluation, pattern research, and technology comparison.

**Capabilities**:
- Deep library evaluation (production readiness, security, performance, community support)
- Architectural pattern research with comprehensive pros/cons analysis
- Technology comparison with weighted evaluation criteria
- Best practices synthesis from authoritative sources
- Risk assessment and compatibility analysis
- Evidence-based recommendations

**Available Tools**: `Read`, `Grep`, `Glob`, `WebSearch`, `WebFetch`

**Model**: Sonnet (configurable)

**Available In**: discovery, planning, building phases

### Code Reviewer

**Purpose**: Comprehensive security vulnerability analysis, code quality assessment, and architecture consistency review.

**Capabilities**:
- Security vulnerability analysis (OWASP Top 10 patterns, injection attacks, authentication issues)
- Code quality assessment (structure, maintainability, readability, coding standards)
- Architecture consistency review (SOLID principles, established patterns)
- Dependency security scanning for known vulnerabilities
- Performance pattern analysis (bottlenecks, inefficient algorithms)
- Cross-repository impact analysis

**Available Tools**: `Read`, `Grep`, `Glob`

**Model**: Sonnet (configurable)

**Available In**: building, validation phases

### Test Engineer

**Purpose**: Develop comprehensive test strategies, ensure robust test coverage, and provide quality validation approaches.

**Capabilities**:
- Test strategy development using agentic AI testing patterns
- Coverage analysis and gap identification
- Edge case identification and prioritization
- Test prioritization based on risk and impact
- Quality validation approaches for production readiness
- Testing framework recommendations and best practices

**Available Tools**: `Read`, `Grep`, `Glob`

**Model**: Sonnet (fixed for comprehensive analysis)

**Available In**: building, validation phases

### Documentation Agent

**Purpose**: Create comprehensive technical documentation, API reference generation, and intelligent content maintenance.

**Capabilities**:
- API documentation generation and maintenance
- Technical documentation completeness analysis
- README updates and improvement suggestions
- Code example generation and validation
- Documentation standards compliance checking
- Developer onboarding documentation review

**Available Tools**: `Read`, `Grep`, `Glob`

**Model**: Haiku (fixed for cost efficiency)

**Available In**: discovery, planning, validation phases

### Product Analyst

**Purpose**: Analyze requirements clarity, validate acceptance criteria, and identify edge cases for effective development.

**Capabilities**:
- Requirements quality assessment and clarity analysis
- User story validation and improvement suggestions
- Acceptance criteria analysis and enhancement
- Stakeholder perspective evaluation
- Edge case identification for comprehensive coverage
- Research guidance generation for unclear requirements

**Available Tools**: `Read`, `Grep`, `Glob`

**Model**: Haiku (fixed for efficiency)

**Available In**: discovery phase

## Phase-Specific Availability

Ralph automatically filters subagents based on the current development phase:

### discovery Phase
- **Research Specialist**: Gather technical requirements and evaluate solution approaches
- **Product Analyst**: Analyze and improve requirement specifications
- **Documentation Agent**: Review existing documentation and identify gaps

### planning Phase
- **Research Specialist**: Evaluate technologies and architectural patterns
- **Documentation Agent**: Create architecture documentation and specifications

### building Phase
- **Test Engineer**: Develop test strategies and ensure TDD compliance
- **Code Reviewer**: Maintain code quality and security standards
- **Research Specialist**: Resolve implementation questions and find patterns

### validation Phase
- **Code Reviewer**: Comprehensive security and quality review
- **Test Engineer**: Run comprehensive test suites and validation
- **Documentation Agent**: Ensure documentation completeness and accuracy

## Security Model

All subagents operate under strict security constraints to maintain system integrity:

### Forbidden Tools

No subagent can access these tools:
- `Write` - Cannot create or overwrite files
- `Edit` - Cannot modify existing files
- `NotebookEdit` - Cannot modify Jupyter notebooks
- `Bash` - Cannot execute shell commands
- `Task` - Cannot spawn other subagents (prevents nesting)

### Tool Permissions by Subagent

| Subagent | Read | Grep | Glob | WebSearch | WebFetch |
|----------|------|------|------|-----------|----------|
| Research Specialist | ✅ | ✅ | ✅ | ✅ | ✅ |
| Code Reviewer | ✅ | ✅ | ✅ | ❌ | ❌ |
| Test Engineer | ✅ | ✅ | ✅ | ❌ | ❌ |
| Documentation Agent | ✅ | ✅ | ✅ | ❌ | ❌ |
| Product Analyst | ✅ | ✅ | ✅ | ❌ | ❌ |

**Note**: Only the Research Specialist has web access for gathering external information and documentation.

### Security Guarantees

1. **No file modification**: Subagents can only read and analyze, never modify
2. **No command execution**: Cannot run shell commands or modify system state
3. **No subagent nesting**: Cannot spawn other subagents to prevent recursive calls
4. **Isolated analysis**: Each subagent operates independently with no shared state
5. **Read-only validation**: All tool access is validated against security constraints

## Usage Examples

### Basic Subagent Invocation

```python
# In Ralph's Building phase, invoke the test engineer
Task(
    subagent_type="test-engineer",
    description="Analyze test coverage for authentication module",
    prompt="Review the authentication module and identify test coverage gaps"
)
```

### Research Specialist for Technology Evaluation

```python
# During Planning phase, evaluate competing technologies
Task(
    subagent_type="research-specialist",
    description="Compare authentication libraries",
    prompt="Compare JWT libraries (PyJWT vs python-jose vs authlib) for API authentication, focusing on security, performance, and ecosystem support"
)
```

### Code Reviewer for Security Analysis

```python
# During Building phase, review security implications
Task(
    subagent_type="code-reviewer",
    description="Security review of user input handling",
    prompt="Analyze the user input validation code for potential security vulnerabilities, focusing on injection attacks and data validation"
)
```

### Documentation Agent for API Documentation

```python
# During Validation phase, ensure documentation completeness
Task(
    subagent_type="documentation-agent",
    description="Review API documentation completeness",
    prompt="Analyze the REST API endpoints and ensure all endpoints have comprehensive documentation with examples"
)
```

### Product Analyst for Requirement Analysis

```python
# During Discovery phase, analyze user requirements
Task(
    subagent_type="product-analyst",
    description="Validate authentication requirements",
    prompt="Review the authentication user stories and identify missing edge cases or unclear acceptance criteria"
)
```

## Expected Report Format

All subagents return structured reports with consistent sections:

### Standard Report Structure

```markdown
### Executive Summary
[2-3 sentence overview of key findings and primary recommendation]

### Detailed Analysis
[Comprehensive analysis with specific findings]

### Recommendations
[Actionable recommendations with priorities]

### Implementation Notes
[Specific guidance for implementation]

### Risks and Considerations
[Potential risks, trade-offs, and important considerations]

### Confidence Assessment
[Assessment of confidence level and any limitations]
```

### Cost and Performance Information

Each subagent report includes:
- **Estimated cost**: Token usage and cost estimate
- **Processing time**: Time taken for analysis
- **Confidence level**: Assessment reliability indicator

## Troubleshooting

### Common Issues

#### Subagent Not Available
**Problem**: Trying to invoke a subagent not available in the current phase.

**Solution**: Check the phase-specific availability table above. Use `ralph-agent status` to see current phase and available subagents.

```bash
# Check current phase and state
uv run ralph-agent status --verbose
```

#### Security Constraint Violations
**Problem**: Subagent attempts to use forbidden tools.

**Solution**: This is automatically prevented by Ralph's security system. The subagent will only have access to its allowed tools.

#### Empty or Error Responses
**Problem**: Subagent returns empty response or error.

**Solution**: Check that:
1. The prompt is specific and actionable
2. Required files exist and are accessible
3. The subagent type is correctly specified

#### Web Access Issues (Research Specialist)
**Problem**: Research Specialist cannot access web resources.

**Solution**: Ensure:
1. Internet connection is available
2. WebSearch and WebFetch tools are not blocked by network policies
3. The specific URLs are accessible

### Debugging Subagent Issues

#### Enable Verbose Output
```bash
# Run Ralph with verbose output to see subagent invocations
uv run ralph-agent build --verbose
```

#### Check Subagent Configuration
```python
# In a test environment, verify subagent configuration
from ralph.subagents import get_subagents_for_phase, PHASE_SUBAGENT_CONFIG
from ralph.models import Phase

# Check which subagents are available for a phase
building_subagents = get_subagents_for_phase(Phase.BUILDING)
print(f"Building phase subagents: {list(building_subagents.keys())}")
```

#### Validate Tool Permissions
```python
# Check tool permissions for a subagent
from ralph.subagents import validate_subagent_tools

# Test tool validation
allowed_tools = validate_subagent_tools("research-specialist", ["Read", "Write", "WebSearch"])
print(f"Allowed tools: {allowed_tools}")  # Should not include "Write"
```

### Performance Considerations

#### Cost Optimization
- **Documentation Agent** and **Product Analyst** use Haiku model for cost efficiency
- **Test Engineer** uses Sonnet for comprehensive analysis accuracy
- **Research Specialist** and **Code Reviewer** use configurable models

#### Time Limits
- Most subagents have 5-10 minute time limits to prevent excessive costs
- Complex analysis tasks may require breaking into smaller, focused requests

#### Parallel Invocation
Multiple subagents can be invoked in parallel when appropriate:

```python
# Example: Parallel analysis during validation
Task(subagent_type="code-reviewer", description="Security analysis", ...)
Task(subagent_type="test-engineer", description="Test validation", ...)
Task(subagent_type="documentation-agent", description="Doc completeness", ...)
```

## Integration with Ralph Workflow

### Automatic Phase Filtering
Ralph automatically provides only phase-appropriate subagents to prevent irrelevant invocations and reduce context switching.

### State Management
Subagent results are integrated into Ralph's state management:
- Reports are stored in session memory
- Cost tracking includes subagent usage
- Results influence task progression and decision making

### Circuit Breaker Integration
Subagent failures count toward Ralph's circuit breaker limits:
- Failed subagent invocations contribute to failure count
- Excessive subagent errors can trigger circuit breaker activation
- Cost overruns from subagents are included in budget monitoring

## Best Practices

### When to Use Subagents

1. **Use for specialized analysis**: When you need domain expertise beyond general development
2. **Leverage during decision points**: Technology choices, architecture decisions, security reviews
3. **Parallel analysis**: When multiple perspectives would be valuable
4. **Quality assurance**: During building and validation phases for comprehensive review

### When NOT to Use Subagents

1. **Simple file operations**: Basic reading, writing, or editing tasks
2. **Straightforward implementation**: When the approach is clear and established
3. **Cost-sensitive scenarios**: When budget is tight and general analysis is sufficient
4. **Rapid prototyping**: When speed is more important than comprehensive analysis

### Effective Prompting

1. **Be specific**: Provide clear, actionable prompts with specific context
2. **Include constraints**: Mention any limitations, requirements, or preferences
3. **Define scope**: Specify what should and shouldn't be analyzed
4. **Request format**: Ask for specific output format if different from standard

### Result Integration

1. **Review reports thoroughly**: Subagent recommendations should inform but not replace judgment
2. **Cross-validate findings**: Compare recommendations across multiple subagents when applicable
3. **Consider context**: Evaluate recommendations within the broader project context
4. **Document decisions**: Record which recommendations were accepted and why

## Advanced Usage

### Custom Subagent Configuration

While subagents use predefined configurations, Ralph's config file can influence behavior:

```yaml
# ralph.yml
primary_model: "claude-opus-4-20250514"  # Affects Research Specialist and Code Reviewer
cost_limits:
  per_iteration: 15.0  # Higher limits allow more subagent usage
```

### Monitoring Subagent Usage

```bash
# Check subagent costs and usage
uv run ralph-agent status --verbose

# Review session history for subagent patterns
cat .ralph/session_history/session-*.json | grep -A5 -B5 "subagent"
```

### Extending Subagent Capabilities

For contributors wanting to add new subagent types:

1. Create template in `src/ralph/templates/subagents/`
2. Add factory function in `src/ralph/subagents.py`
3. Update `SUBAGENT_SECURITY_CONSTRAINTS` and `PHASE_SUBAGENT_CONFIG`
4. Add comprehensive tests following existing patterns
5. Update this documentation

This documentation covers the current subagent system as of Ralph v0.1.0.