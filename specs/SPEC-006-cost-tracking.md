# SPEC-006: Proper Cost and Token Tracking

**JTBD**: When Ralph completes any operation or phase, I want accurate cost and token usage information displayed, so I can monitor resource consumption and budget my usage effectively.

## Problem Statement
Ralph consistently shows "OK (0 tokens, $0.0000)" at the end of sessions, indicating that cost and token tracking is not working properly. This prevents users from understanding resource consumption and budgeting their usage.

## Functional Requirements
1. **Token Counting**: Accurately count input and output tokens using Claude Agent SDK APIs
2. **Cost Calculation**: Calculate costs based on current Claude pricing tiers
3. **Real-time Tracking**: Track costs and tokens throughout session execution
4. **Cumulative Reporting**: Show per-iteration and total session costs
5. **Budget Monitoring**: Track against configured budget limits
6. **Cost Breakdown**: Show costs by phase, iteration, and tool usage

## User Stories
- As a developer, I want to see how much each Ralph session costs me
- As a developer, I want to track token usage to understand efficiency
- As a developer, I want to budget my Ralph usage based on accurate cost data
- As a developer, I want cost breakdowns to optimize my usage patterns

## Success Criteria
- [ ] Accurate token counts are displayed for every operation
- [ ] Costs are calculated using current Claude pricing
- [ ] Cost information is shown in CLI output
- [ ] Cumulative costs are tracked across iterations
- [ ] Budget warnings are shown when approaching limits

## Acceptance Criteria
- [ ] RalphSDKClient tracks tokens for all operations
- [ ] Cost calculation uses up-to-date Claude pricing
- [ ] CLI displays real token counts and costs (not $0.0000)
- [ ] Cost tracking works across all phases and iterations
- [ ] Budget limits are configurable and enforced
- [ ] Cost data is persisted in Ralph state for session totals

## Constraints
- Must use Claude Agent SDK token counting APIs
- Must stay current with Claude pricing changes
- Cannot significantly impact performance with tracking overhead

## Edge Cases
- **API token count unavailable**: Fall back to estimated token counting
- **Pricing changes**: Graceful handling of pricing API updates
- **Budget exceeded**: Clear warnings and optional session termination
- **Token counting errors**: Log errors but continue operation

## Dependencies
- **Depends on**: Context7 MCP server for Claude Agent SDK documentation
- **Required by**: None (standalone improvement)

## References
- Use `context7` mcp server to read the claude agent sdk documentation to find how to access context windows details for the current session of the agent.