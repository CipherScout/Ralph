# SPEC-002: Tool Access Parity Across All Phases

**JTBD**: When Ralph executes any phase, I want all Claude Agent SDK tools to be available, so I can use the same capabilities consistently regardless of which phase I'm in.

## Problem Statement
Currently, some tools (like TodoWrite) are restricted in certain phases (validation), creating artificial limitations that prevent optimal workflow execution. This inconsistency makes the system unpredictable and limits the agent's ability to maintain context and track progress.

## Functional Requirements
1. **Universal Tool Access**: All Claude Agent SDK tools must be available in all phases
2. **Tool Discovery**: Systematically identify all available Claude Agent SDK tools using Context7
3. **Permission Configuration**: Configure RalphSDKClient to allow all tools in all phases
4. **Tool Registry**: Maintain a comprehensive registry of available tools
5. **Phase-Specific Guidance**: Provide context-appropriate guidance for tool usage per phase

## User Stories
- As a validation agent, I want to use TodoWrite to track validation progress
- As a building agent, I want to use all available tools for optimal implementation
- As a planning agent, I want access to all tools for comprehensive task creation
- As a discovery agent, I want full tool access for thorough requirements gathering

## Success Criteria
- [ ] All Claude Agent SDK tools are available in all four phases
- [ ] No "tool not allowed" errors occur during phase execution
- [ ] Tool permissions are centrally configured and consistent
- [ ] Context7 MCP server integration provides complete tool discovery
- [ ] Documentation shows which tools are available in each phase

## Acceptance Criteria
- [ ] Context7 query identifies all available Claude Agent SDK tools
- [ ] RalphSDKClient configuration enables all tools for all phases
- [ ] TodoWrite tool works in validation phase
- [ ] All existing tool restrictions are removed from executors
- [ ] New tool registry system is implemented and tested
- [ ] Integration tests verify tool access across all phases

## Constraints
- Must use Context7 MCP server for tool discovery
- Cannot break existing tool usage patterns
- Must maintain security boundaries where appropriate

## Edge Cases
- **New tools added to Claude Agent SDK**: Registry system should auto-discover
- **Tools with security implications**: May require explicit approval patterns
- **Tools that conflict across phases**: Provide phase-specific usage guidance

## Dependencies
- **Depends on**: Context7 MCP server integration
- **Required by**: SPEC-001 (validation reliability), SPEC-003 (spec integration)