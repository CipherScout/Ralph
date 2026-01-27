# SPEC-005: Context Window Utilization & Completion Detection

**JTBD**: When Ralph executes any phase, I want it to utilize 80-85% of the context window efficiently and detect completion signals properly, so that sessions don't exit prematurely and agent has sufficient context to work effectively.

## Problem Statement
Ralph currently has aggressive context consumption thresholds that cause premature session/iteration exits. Additionally, completion promise detection from Claude Agent SDK is not properly implemented, leading to inefficient resource utilization and incomplete work.

## Functional Requirements
1. **Context Window Monitoring**: Track context window usage using Claude Agent SDK APIs
2. **Optimal Utilization**: Allow context usage up to 80-85% before session termination
3. **Completion Promise Detection**: Implement proper completion signal handling from Claude Agent SDK
4. **Dynamic Threshold**: Adjust context limits based on phase and task complexity
5. **Context Optimization**: Optimize context usage through selective memory and spec inclusion
6. **Early Warning**: Provide warnings when approaching context limits

## User Stories
- As an agent, I want to use most of my available context window for complex tasks
- As a developer, I want sessions to complete natural work units rather than arbitrary limits
- As a developer, I want clear feedback on context usage and limits
- As an agent, I want to signal completion explicitly rather than hitting arbitrary limits

## Success Criteria
- [ ] Context window usage reaches 80-85% before session termination
- [ ] Completion promise signals are properly detected and handled
- [ ] No premature session exits due to conservative context limits
- [ ] Context usage is accurately measured and reported
- [ ] Sessions complete logical work units rather than arbitrary boundaries

## Acceptance Criteria
- [ ] RalphSDKClient tracks context usage in real-time
- [ ] Configuration allows context threshold adjustment (default 80-85%)
- [ ] Completion promise handling is implemented and tested
- [ ] Context usage is displayed in CLI output
- [ ] Sessions exit on completion signals, not just context limits
- [ ] Integration tests verify context optimization works

## Constraints
- Must use Claude Agent SDK APIs for context measurement
- Cannot exceed actual context window limits (safety margin required)
- Must work with existing executor patterns

## Edge Cases
- **Context measurement API failure**: Fall back to conservative estimates
- **Rapid context growth**: Implement emergency exit at 90% usage
- **Completion signal false positives**: Require confirmation for critical operations
- **Context optimization failure**: Graceful degradation to current behavior

## Dependencies
- **Depends on**: Context7 MCP server for Claude Agent SDK documentation
- **Required by**: SPEC-001 (validation reliability) for better validation completion

## References
- Use `context7` mcp server to read the claude agent sdk documentation to find how to access context windows details for the current session of the agent.