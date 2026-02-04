"""Mock subagent responses for integration testing.

This module provides standardized mock responses for subagent invocations
to support consistent integration testing. Each subagent type has predefined
responses for different scenarios (success, error, timeout, etc.).
"""

from __future__ import annotations

from typing import Any

# Mock responses for research specialist subagent
RESEARCH_SPECIALIST_RESPONSES = {
    "technology_analysis": {
        "success": True,
        "response": """# Research Analysis Report

## Executive Summary
After comprehensive analysis of the requested technology, I've evaluated three primary options
with detailed trade-off analysis.

## Detailed Analysis

### Option 1: WebSocket-based Implementation
- **Pros**: Real-time bidirectional communication, low latency
- **Cons**: More complex state management, requires connection handling
- **Use Cases**: Interactive applications, live collaboration

### Option 2: Server-Sent Events (SSE)
- **Pros**: Simpler than WebSockets, built-in reconnection
- **Cons**: Unidirectional from server, limited browser support
- **Use Cases**: Live updates, notifications

### Option 3: HTTP Polling
- **Pros**: Simple implementation, universal compatibility
- **Cons**: Higher latency, increased server load
- **Use Cases**: Basic status updates, simple notifications

## Recommendations
1. **Primary**: WebSocket implementation for real-time features
2. **Fallback**: SSE for environments with WebSocket limitations
3. **Consider**: HTTP polling for backwards compatibility

## Confidence Assessment
**High** - Based on extensive documentation review and industry best practices analysis.
""",
        "tokens_used": 245,
        "cost_estimate": 0.12
    },
    "library_evaluation": {
        "success": True,
        "response": """# Library Evaluation Report

## Executive Summary
Evaluated 5 candidate libraries for the requested functionality. Primary recommendation is
Library A with strong performance and security characteristics.

## Detailed Analysis

### Library A (Recommended)
- **Version**: 2.1.0
- **Stars**: 15,240
- **Maintenance**: Active (last update 2 days ago)
- **Security**: No known vulnerabilities
- **Performance**: Excellent (99th percentile < 50ms)
- **Documentation**: Comprehensive with examples

### Library B (Alternative)
- **Version**: 1.8.3
- **Stars**: 8,150
- **Maintenance**: Moderate (last update 1 month ago)
- **Security**: 1 low-severity issue
- **Performance**: Good (99th percentile < 100ms)
- **Documentation**: Good but limited examples

## Recommendations
1. **Primary**: Use Library A for production implementation
2. **Testing**: Prototype with both libraries for comparison
3. **Migration**: Plan for potential future migration path

## Confidence Assessment
**High** - Based on thorough analysis of GitHub metrics, security scans, and performance benchmarks.
""",
        "tokens_used": 210,
        "cost_estimate": 0.10
    },
    "error_scenario": {
        "success": False,
        "error": "Research specialist timed out after 300 seconds",
        "tokens_used": 0,
        "cost_estimate": 0.0
    }
}

# Mock responses for code reviewer subagent
CODE_REVIEWER_RESPONSES = {
    "security_analysis": {
        "success": True,
        "response": """# Code Security Analysis Report

## Executive Summary
Completed security analysis of the submitted code. Found 2 medium-priority issues and
3 low-priority improvements.

## Security Findings

### Medium Priority Issues

#### 1. Input Validation Gap
- **File**: `src/auth/login.py:45`
- **Issue**: User input not sanitized before database query
- **Risk**: Potential SQL injection vulnerability
- **Recommendation**: Use parameterized queries or ORM methods

#### 2. Error Information Disclosure
- **File**: `src/api/handlers.py:123`
- **Issue**: Detailed error messages exposed to client
- **Risk**: Information disclosure to potential attackers
- **Recommendation**: Implement generic error responses for production

### Low Priority Improvements

#### 1. Logging Enhancement
- **File**: `src/utils/logger.py:67`
- **Issue**: Sensitive data potentially logged
- **Recommendation**: Implement data sanitization in logging

#### 2. Authentication Header
- **File**: `src/middleware/auth.py:34`
- **Issue**: Missing secure flag on authentication cookies
- **Recommendation**: Set secure and httpOnly flags

#### 3. Rate Limiting
- **File**: `src/api/routes.py:12`
- **Issue**: No rate limiting on API endpoints
- **Recommendation**: Implement rate limiting middleware

## Code Quality Assessment
- **Maintainability**: Good - Clear structure and naming
- **Test Coverage**: 78% - Could improve edge case testing
- **Documentation**: Adequate - Some functions missing docstrings

## Recommendations
1. **Immediate**: Fix medium-priority security issues
2. **Short-term**: Implement logging improvements
3. **Long-term**: Add comprehensive rate limiting

## Confidence Assessment
**High** - Based on static analysis and security best practices review.
""",
        "tokens_used": 320,
        "cost_estimate": 0.16
    },
    "quality_review": {
        "success": True,
        "response": """# Code Quality Review Report

## Executive Summary
Code quality review completed. Overall good structure with some opportunities for improvement
in maintainability and performance.

## Quality Findings

### Strengths
- Clear function and variable naming
- Appropriate separation of concerns
- Good error handling patterns
- Consistent code formatting

### Improvement Areas

#### 1. Performance Optimization
- **Issue**: Inefficient database queries in user lookup
- **Impact**: N+1 query problem in user list endpoint
- **Recommendation**: Implement eager loading or batch queries

#### 2. Code Duplication
- **Issue**: Similar validation logic repeated across modules
- **Impact**: Maintenance burden and inconsistency risk
- **Recommendation**: Extract common validation utilities

#### 3. Magic Numbers
- **Issue**: Hard-coded values scattered throughout code
- **Impact**: Difficult to maintain and configure
- **Recommendation**: Move to configuration constants

## Test Coverage Analysis
- **Overall**: 85%
- **Critical Paths**: 92%
- **Edge Cases**: 67%
- **Integration**: 73%

## Recommendations
1. **High Priority**: Optimize database query patterns
2. **Medium Priority**: Refactor duplicated validation logic
3. **Low Priority**: Replace magic numbers with constants

## Confidence Assessment
**High** - Based on comprehensive static analysis and code review guidelines.
""",
        "tokens_used": 285,
        "cost_estimate": 0.14
    },
    "error_scenario": {
        "success": False,
        "error": "Code reviewer encountered parsing error in source files",
        "tokens_used": 15,
        "cost_estimate": 0.01
    }
}

# Mock responses for test engineer subagent
TEST_ENGINEER_RESPONSES = {
    "test_strategy": {
        "success": True,
        "response": """# Test Strategy Report

## Executive Summary
Comprehensive test strategy developed for the authentication module. Recommends unit,
integration, and e2e testing with specific focus areas.

## Test Strategy Overview

### Test Pyramid Structure
- **Unit Tests**: 70% of total test suite
- **Integration Tests**: 20% of total test suite
- **End-to-End Tests**: 10% of total test suite

## Test Coverage Plan

### Unit Tests (Priority: High)
#### Authentication Service Tests
```python
# Critical test cases
test_valid_user_login()
test_invalid_credentials()
test_account_lockout_after_failed_attempts()
test_password_hash_verification()
test_token_generation()
test_token_expiration()
```

#### User Management Tests
```python
# User lifecycle testing
test_user_creation_validation()
test_user_role_assignment()
test_user_deactivation()
test_user_password_reset()
```

### Integration Tests (Priority: Medium)
- Database integration testing
- API endpoint testing
- External service mocking
- Session management testing

### End-to-End Tests (Priority: Medium)
- Complete user journey testing
- Browser automation scenarios
- Mobile app testing (if applicable)

## Test Data Management
- **Fixtures**: Create standardized test data sets
- **Factories**: Implement user/data factories for consistent test data
- **Cleanup**: Ensure proper test isolation and cleanup

## Performance Testing
- **Load Testing**: Simulate concurrent user authentication
- **Stress Testing**: Test system limits and failure modes
- **Security Testing**: Penetration testing for auth vulnerabilities

## Recommendations
1. **Immediate**: Implement comprehensive unit test suite
2. **Short-term**: Add integration tests for critical workflows
3. **Long-term**: Establish automated performance testing

## Confidence Assessment
**High** - Based on authentication system analysis and testing best practices.
""",
        "tokens_used": 380,
        "cost_estimate": 0.19
    },
    "coverage_analysis": {
        "success": True,
        "response": """# Test Coverage Analysis Report

## Executive Summary
Current test coverage analyzed across all modules. Overall coverage is 78% with specific
gaps identified in error handling and edge cases.

## Coverage Breakdown

### Module Coverage
- **Authentication**: 92% (Excellent)
- **User Management**: 85% (Good)
- **API Handlers**: 73% (Fair)
- **Database Utilities**: 68% (Needs improvement)
- **Error Handling**: 45% (Critical gap)

### Coverage Gaps Analysis

#### Critical Gaps (Immediate attention needed)
1. **Error Handling Paths**: Only 45% of error scenarios tested
2. **Edge Cases**: Boundary conditions in validation logic
3. **Database Failures**: Connection and transaction error handling
4. **External API Failures**: Third-party service error scenarios

#### Important Gaps (Address soon)
1. **Performance Edge Cases**: Large dataset handling
2. **Concurrent Access**: Multi-user scenarios
3. **Configuration Edge Cases**: Invalid configuration handling

## Test Quality Assessment
- **Assertion Quality**: Good - Tests verify expected behavior
- **Test Isolation**: Excellent - Proper setup/teardown
- **Test Maintainability**: Good - Clear test structure
- **Test Performance**: Fair - Some slow integration tests

## Recommendations
1. **Priority 1**: Increase error handling test coverage to 80%+
2. **Priority 2**: Add edge case testing for validation logic
3. **Priority 3**: Implement performance regression testing

## Coverage Goals
- **Short-term**: Achieve 85% overall coverage
- **Medium-term**: 90% coverage with quality metrics
- **Long-term**: Maintain 90%+ with automated reporting

## Confidence Assessment
**High** - Based on comprehensive coverage analysis and testing metrics.
""",
        "tokens_used": 340,
        "cost_estimate": 0.17
    },
    "error_scenario": {
        "success": False,
        "error": "Test engineer could not access test files - permission denied",
        "tokens_used": 8,
        "cost_estimate": 0.01
    }
}

# Mock responses for documentation agent
DOCUMENTATION_AGENT_RESPONSES = {
    "api_documentation": {
        "success": True,
        "response": """# API Documentation Analysis Report

## Executive Summary
Analyzed existing API documentation and identified key areas for improvement. Current
documentation coverage is 65% with gaps in error responses and examples.

## Documentation Assessment

### Current Documentation Quality
- **API Endpoints**: 80% documented
- **Request/Response Examples**: 45% coverage
- **Error Codes**: 30% coverage
- **Authentication**: 90% coverage
- **Rate Limiting**: 60% coverage

### Missing Documentation

#### Critical Missing Elements
1. **Error Response Documentation**
   - Standard error format not documented
   - HTTP status code meanings unclear
   - Error recovery guidance missing

2. **Request/Response Examples**
   - Most endpoints lack example payloads
   - Response schema documentation incomplete
   - Authentication examples minimal

3. **Integration Guides**
   - No quick start guide available
   - SDK usage examples missing
   - Common use case scenarios undocumented

### Recommended Documentation Structure

#### API Reference
```markdown
## Authentication Endpoints

### POST /api/v1/auth/login
**Description**: Authenticate user and receive access token

**Request Body**:
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Success Response (200)**:
```json
{
  "access_token": "eyJ0eXAiOiJKV1Q...",
  "refresh_token": "dGhpc0lzQVJlZn...",
  "expires_in": 3600,
  "user": {
    "id": 123,
    "email": "user@example.com",
    "role": "user"
  }
}
```

**Error Responses**:
- `401 Unauthorized`: Invalid credentials
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server error
```

## Recommendations
1. **Immediate**: Document all error responses with examples
2. **Short-term**: Add comprehensive request/response examples
3. **Long-term**: Create interactive API documentation

## Documentation Tools
- **Recommended**: OpenAPI/Swagger specification
- **Alternative**: API Blueprint or Postman collections
- **Interactive**: Consider API documentation platforms

## Confidence Assessment
**High** - Based on thorough analysis of existing documentation and industry best practices.
""",
        "tokens_used": 425,
        "cost_estimate": 0.21
    },
    "completeness_check": {
        "success": True,
        "response": """# Documentation Completeness Check Report

## Executive Summary
Comprehensive review of project documentation completed. Overall completeness is 72% with
specific gaps in technical documentation and user guides.

## Documentation Inventory

### Existing Documentation
- **README.md**: Present, good quality
- **API Documentation**: 65% complete
- **Installation Guide**: 80% complete
- **Configuration Guide**: 90% complete
- **Contributing Guide**: 70% complete
- **Architecture Documentation**: 45% complete
- **Troubleshooting Guide**: 40% complete
- **User Guide**: 35% complete

### Documentation Quality Assessment

#### High Quality (>80% complete)
- Configuration and setup documentation
- Basic installation procedures
- Core API endpoint documentation

#### Medium Quality (50-80% complete)
- Contributing guidelines and development setup
- Basic API documentation with some examples
- README with good project overview

#### Low Quality (<50% complete)
- Architecture and design decisions
- Comprehensive troubleshooting guides
- End-user documentation and tutorials

### Critical Documentation Gaps

#### 1. Architecture Documentation
- System design decisions not documented
- Database schema documentation missing
- Service interaction diagrams absent

#### 2. User Documentation
- Getting started tutorials missing
- Common use case examples absent
- Feature explanation lacking

#### 3. Operational Documentation
- Deployment procedures incomplete
- Monitoring and alerting setup missing
- Backup and recovery procedures absent

## Recommended Documentation Additions

### Priority 1 (Critical)
1. **Architecture Decision Records (ADRs)**
2. **Comprehensive API documentation with examples**
3. **User onboarding guide**

### Priority 2 (Important)
1. **Troubleshooting guide with common issues**
2. **Development environment setup guide**
3. **Performance optimization guide**

### Priority 3 (Nice to have)
1. **Video tutorials for complex features**
2. **FAQ section based on user feedback**
3. **Best practices and patterns guide**

## Maintenance Recommendations
- **Documentation reviews**: Include in pull request process
- **Automated checks**: Implement documentation link validation
- **User feedback**: Regular documentation usability testing

## Confidence Assessment
**High** - Based on systematic review of all documentation artifacts and completeness analysis.
""",
        "tokens_used": 445,
        "cost_estimate": 0.22
    },
    "error_scenario": {
        "success": False,
        "error": "Documentation agent failed to parse markdown files - encoding issues",
        "tokens_used": 12,
        "cost_estimate": 0.01
    }
}

# Mock responses for product analyst
PRODUCT_ANALYST_RESPONSES = {
    "requirements_analysis": {
        "success": True,
        "response": """# Requirements Analysis Report

## Executive Summary
Analyzed provided requirements for clarity, completeness, and feasibility. Overall
requirements quality is good but identified several areas needing clarification.

## Requirements Quality Assessment

### Clear Requirements (85%)
- **Functional Requirements**: Well-defined user actions and system behaviors
- **Performance Requirements**: Specific metrics and targets provided
- **Security Requirements**: Clear security standards and compliance needs

### Ambiguous Requirements (15%)
- **User Experience**: Vague descriptions of interface requirements
- **Integration**: Unclear external system dependencies
- **Error Handling**: Insufficient error scenario specifications

## Detailed Analysis

### Functional Requirements
#### Strengths
- User stories follow standard format (As a... I want... So that...)
- Acceptance criteria clearly defined for most features
- Business logic well articulated

#### Gaps
- **Edge Cases**: Limited coverage of boundary conditions
- **Validation Rules**: Some input validation requirements unclear
- **Data Processing**: Batch processing requirements ambiguous

### Non-Functional Requirements
#### Strengths
- Performance targets specified (response time < 200ms)
- Scalability requirements defined (1000 concurrent users)
- Security compliance standards identified (SOC2, GDPR)

#### Gaps
- **Availability**: Uptime requirements not specified
- **Disaster Recovery**: Backup and recovery requirements missing
- **Monitoring**: Observability requirements unclear

## Risk Analysis

### High Risk Requirements
1. **Real-time Features**: WebSocket implementation complexity
2. **Data Migration**: Legacy system integration challenges
3. **Performance**: Concurrent user load handling

### Medium Risk Requirements
1. **Third-party Integration**: External API dependencies
2. **Mobile Compatibility**: Cross-platform testing needs
3. **Security Audit**: Compliance verification process

## Recommendations

### Priority 1 (Immediate)
1. **Clarify Integration Requirements**: Define external system interfaces
2. **Specify Error Handling**: Document all error scenarios and responses
3. **Define UX Requirements**: Create detailed interface specifications

### Priority 2 (Short-term)
1. **Add Performance Metrics**: Define comprehensive performance criteria
2. **Expand Test Scenarios**: Include edge cases and error conditions
3. **Document Assumptions**: Make implicit assumptions explicit

### Priority 3 (Long-term)
1. **Create Requirements Traceability**: Link requirements to test cases
2. **Establish Review Process**: Regular requirements validation cycles
3. **User Feedback Integration**: Process for requirement evolution

## Quality Metrics
- **Completeness**: 78%
- **Clarity**: 82%
- **Testability**: 75%
- **Feasibility**: 88%

## Confidence Assessment
**High** - Based on systematic requirements analysis and industry best practices for
requirement quality.
""",
        "tokens_used": 485,
        "cost_estimate": 0.24
    },
    "clarity_validation": {
        "success": True,
        "response": """# Requirements Clarity Validation Report

## Executive Summary
Validated requirements clarity across all functional areas. Identified 12 areas requiring
clarification and 8 recommendations for improved specificity.

## Clarity Assessment Results

### High Clarity (70% of requirements)
Requirements that are specific, measurable, and unambiguous:
- User authentication workflows
- Data validation rules
- API endpoint specifications
- Performance benchmarks

### Medium Clarity (20% of requirements)
Requirements that are generally clear but could benefit from more detail:
- User interface layouts
- Integration error handling
- Notification preferences
- Reporting requirements

### Low Clarity (10% of requirements)
Requirements that need significant clarification:
- Complex business rule processing
- Multi-step workflow exceptions
- Advanced search functionality
- Data synchronization logic

## Specific Clarification Needs

### Critical Clarifications Required

#### 1. Business Rule Processing
**Current**: "System should handle complex business rules"
**Issues**:
- What constitutes "complex"?
- Which specific business rules apply?
- How should rule conflicts be resolved?
**Recommendation**: Provide specific rule examples and decision trees

#### 2. Error Handling Strategy
**Current**: "System should gracefully handle errors"
**Issues**:
- What constitutes "graceful" handling?
- Which errors require user notification?
- What's the recovery mechanism?
**Recommendation**: Define error categories and specific handling procedures

#### 3. Integration Workflows
**Current**: "Integrate with external systems as needed"
**Issues**:
- Which specific systems require integration?
- What data flows between systems?
- How should integration failures be handled?
**Recommendation**: Create integration specification documents

### Important Clarifications

#### 4. User Experience Requirements
**Current**: "Provide intuitive user interface"
**Recommendation**: Define usability criteria and conduct user testing

#### 5. Performance Expectations
**Current**: "System should be fast and responsive"
**Recommendation**: Specify concrete performance metrics and measurement methods

#### 6. Security Requirements
**Current**: "Implement appropriate security measures"
**Recommendation**: Define specific security standards and compliance requirements

## Improvement Recommendations

### Documentation Enhancements
1. **Add Examples**: Include concrete examples for abstract requirements
2. **Define Terms**: Create glossary of domain-specific terminology
3. **Specify Metrics**: Quantify qualitative requirements where possible

### Process Improvements
1. **Stakeholder Reviews**: Regular requirement validation sessions
2. **Prototyping**: Create mockups for unclear interface requirements
3. **User Stories**: Break down complex requirements into user stories

### Quality Assurance
1. **Requirement Checklists**: Implement clarity validation checklists
2. **Review Templates**: Standardize requirement documentation format
3. **Traceability**: Link requirements to design and test artifacts

## Next Steps
1. **Schedule Clarification Sessions**: Meet with stakeholders for ambiguous requirements
2. **Create Detailed Specifications**: Develop comprehensive requirement documents
3. **Implement Review Process**: Establish ongoing requirement validation

## Confidence Assessment
**High** - Based on systematic clarity analysis using established requirement engineering
principles.
""",
        "tokens_used": 510,
        "cost_estimate": 0.25
    },
    "error_scenario": {
        "success": False,
        "error": "Product analyst encountered invalid requirement format - unable to parse",
        "tokens_used": 18,
        "cost_estimate": 0.01
    }
}

def get_mock_subagent_response(
    subagent_type: str,
    scenario: str = "success"
) -> dict[str, Any]:
    """Get a mock response for a specific subagent and scenario.

    Args:
        subagent_type: The type of subagent (e.g., "research-specialist")
        scenario: The scenario to mock (defaults to first available scenario)

    Returns:
        Mock response data including success status, response content, and metrics

    Raises:
        ValueError: If subagent_type or scenario is not found
    """
    response_map = {
        "research-specialist": RESEARCH_SPECIALIST_RESPONSES,
        "code-reviewer": CODE_REVIEWER_RESPONSES,
        "test-engineer": TEST_ENGINEER_RESPONSES,
        "documentation-agent": DOCUMENTATION_AGENT_RESPONSES,
        "product-analyst": PRODUCT_ANALYST_RESPONSES,
    }

    if subagent_type not in response_map:
        raise ValueError(f"Unknown subagent type: {subagent_type}")

    subagent_responses = response_map[subagent_type]

    if scenario not in subagent_responses:
        # If specific scenario not found, try to get the first available scenario
        if subagent_responses:
            scenario = next(iter(subagent_responses.keys()))
        else:
            raise ValueError(f"No responses available for subagent type: {subagent_type}")

    return subagent_responses[scenario]


def get_all_subagent_types() -> list[str]:
    """Get list of all available subagent types for testing."""
    return [
        "research-specialist",
        "code-reviewer",
        "test-engineer",
        "documentation-agent",
        "product-analyst"
    ]


def get_subagent_scenarios(subagent_type: str) -> list[str]:
    """Get available scenarios for a specific subagent type.

    Args:
        subagent_type: The subagent type to get scenarios for

    Returns:
        List of available scenario names

    Raises:
        ValueError: If subagent_type is not found
    """
    response_map = {
        "research-specialist": RESEARCH_SPECIALIST_RESPONSES,
        "code-reviewer": CODE_REVIEWER_RESPONSES,
        "test-engineer": TEST_ENGINEER_RESPONSES,
        "documentation-agent": DOCUMENTATION_AGENT_RESPONSES,
        "product-analyst": PRODUCT_ANALYST_RESPONSES,
    }

    if subagent_type not in response_map:
        raise ValueError(f"Unknown subagent type: {subagent_type}")

    return list(response_map[subagent_type].keys())
