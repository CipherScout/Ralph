# Product Requirements Document: Ralph Agent Harness Improvements

## Overview
Transform Ralph from a basic coding loop into a deterministic, predictable agent harness with robust state management, proper cost tracking, optimized context usage, and reliable phase transitions.

## Business Context
- **Problem Statement**: Ralph suffers from multiple reliability and usability issues including validation stagnation, poor memory management, inaccurate cost tracking, and phase restrictions that prevent optimal workflow execution
- **Target Users**: Developers, automation engineers, and project managers using Ralph for automated coding workflows who need reliability and predictability
- **Success Metrics**:
  - 100% reliable phase transitions without stagnation
  - Deterministic memory handoffs between sessions/iterations/phases
  - Accurate token and cost tracking throughout workflows
  - Optimal context window utilization (80-85%)
  - Clean state management and file organization

## Jobs to Be Done

| Job ID | Description | Spec File |
|--------|-------------|-----------|
| JTBD-001 | When the phase transition timer expires, automatically continue to next phase without user input | [SPEC-001-auto-transition-timer](./SPEC-001-auto-transition-timer.md) |
| JTBD-002 | When testing phase transition logic, verify behavior without incurring Claude SDK costs | [SPEC-002-test-coverage](./SPEC-002-test-coverage.md) |
| JTBD-003 | When user presses Enter or 'n' during countdown, immediately handle input without race conditions | [SPEC-003-input-handling](./SPEC-003-input-handling.md) |
| JTBD-004 | When Ralph is executing workflows, optimize context consumption and implement completion signals for better resource utilization | [SPEC-004-context-optimization](./SPEC-004-context-optimization.md) |
| JTBD-005 | When Ralph transitions between sessions/iterations/phases, ensure deterministic memory management by the agent harness | [SPEC-005-memory-system-integration](./SPEC-005-memory-system-integration.md) |
| JTBD-006 | When Ralph is executing in any phase, provide access to all tools regardless of phase restrictions | [SPEC-006-tool-phase-restrictions](./SPEC-006-tool-phase-restrictions.md) |
| JTBD-007 | When Ralph reaches validation phase, ensure efficient progress without getting stuck in loops | [SPEC-007-validation-stagnation-fix](./SPEC-007-validation-stagnation-fix.md) |
| JTBD-008 | When Ralph executes workflows, provide accurate token and cost tracking throughout all phases | [SPEC-008-cost-tracking-fix](./SPEC-008-cost-tracking-fix.md) |
| JTBD-009 | When a Ralph workflow cycle completes, provide option to clean up state files for fresh starts | [SPEC-009-state-cleanup-system](./SPEC-009-state-cleanup-system.md) |
| JTBD-010 | When I want to reset Ralph to clean state, provide a CLI command similar to 'ralph-agent init' | [SPEC-010-cli-clean-command](./SPEC-010-cli-clean-command.md) |
| JTBD-011 | When Ralph creates progress tracking files, store them in .ralph/ directory for consistent organization | [SPEC-011-progress-file-location](./SPEC-011-progress-file-location.md) |

## Business Rules
1. **Deterministic Memory Management**: Memory creation/reading MUST be handled by Ralph harness code, not left to LLM decisions
2. **Tool Universality**: ALL tools must be available in ALL phases without artificial restrictions
3. **Context Optimization**: Context consumption should reach 80-85% before triggering handoffs
4. **Cost Transparency**: Accurate token and cost tracking is mandatory for all operations
5. **State Cleanliness**: All Ralph artifacts must be contained within .ralph/ directory
6. **Completion Reliability**: Phase transitions must complete reliably without stagnation

## Global Constraints
- **Technical**: Must use Claude Agent SDK APIs for context measurement, cost tracking, and completion promises
- **Compatibility**: Must maintain backward compatibility with existing workflows and state files
- **Testing**: Must follow TDD approach with comprehensive test coverage before code changes
- **Documentation**: Must use context7 MCP server to research Claude Agent SDK documentation

## Non-Goals (Explicit Exclusions)
- Changing Ralph's core four-phase workflow (Discovery, Planning, Building, Validation)
- Modifying the fundamental agent architecture or SDK integration patterns
- Adding new phases or fundamentally altering the workflow structure
- Changing file formats in breaking ways

## References
- [TECHNICAL_ARCHITECTURE.md](./TECHNICAL_ARCHITECTURE.md)
- Claude Agent SDK documentation via context7 MCP server
- Issue evidence in PROMPT.md appendix logs
- Existing Ralph codebase patterns and conventions