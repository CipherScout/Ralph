# SPEC-007: Automated State Cleanup System

**JTBD**: When Ralph completes a full development cycle, I want the option to clean up all state files automatically, so I can start fresh without manual file management or state corruption issues.

## Problem Statement
At the end of a full Ralph cycle, state files (implementation_plan.json, state.json, progress.txt) remain in the system, potentially causing issues with future runs or consuming disk space unnecessarily. Users need an automated way to clean up state.

## Functional Requirements
1. **Cycle Completion Detection**: Detect when a full Ralph cycle (Discovery → Planning → Building → Validation) completes
2. **Cleanup Prompt**: Ask user if they want to clean up state at cycle completion
3. **Selective Cleanup**: Clean up state files while preserving important outputs
4. **Safety Checks**: Prevent accidental cleanup of important work
5. **Cleanup Verification**: Confirm cleanup completion and show what was removed

## User Stories
- As a developer, I want Ralph to offer cleanup after completing a full cycle
- As a developer, I want to choose what gets cleaned up to preserve important work
- As a developer, I want confirmation of what was cleaned up
- As a developer, I want to start fresh without manual file deletion

## Success Criteria
- [ ] Cleanup prompt appears after successful validation phase completion
- [ ] User can choose to clean up state or keep it
- [ ] State files are properly removed when cleanup is confirmed
- [ ] Important outputs (like generated code) are preserved
- [ ] Cleanup process is logged and confirmed

## Acceptance Criteria
- [ ] Cleanup prompt is shown after validation phase completes
- [ ] User can accept or decline cleanup
- [ ] State files (.ralph/state.json, .ralph/implementation_plan.json) are removed
- [ ] Progress files (.ralph/progress.txt) are removed
- [ ] Memory files can be optionally preserved
- [ ] Cleanup is implemented in Ralph harness, not delegated to agent
- [ ] Cleanup process is tested and verified

## Constraints
- Must be implemented in Ralph harness (CLI/executors)
- Cannot accidentally delete user's source code or important outputs
- Must provide clear confirmation of what will be deleted

## Edge Cases
- **Incomplete cycle**: No cleanup prompt for incomplete cycles
- **File permission errors**: Handle cleanup failures gracefully
- **User interruption**: Handle cleanup interruption safely
- **Partial cleanup**: Handle cases where some files can't be deleted

## Dependencies
- **Depends on**: None (standalone feature)
- **Required by**: SPEC-008 (clean command) for manual cleanup option