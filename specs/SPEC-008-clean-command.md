# SPEC-008: Ralph-Agent Clean CLI Command

**JTBD**: When I want to reset Ralph's state manually, I want a simple CLI command that cleans up all state files, so I can start fresh equivalent to running ralph-agent init.

## Problem Statement
Users need a way to manually clean up Ralph state files without going through a full development cycle. The current system only offers cleanup at cycle completion, but users may want to reset state for various reasons (debugging, starting over, etc.).

## Functional Requirements
1. **Clean Command**: Add `ralph-agent clean` CLI command
2. **State Reset**: Remove all state files to achieve init-equivalent state
3. **Confirmation Prompt**: Require user confirmation before destructive operations
4. **Selective Cleaning**: Allow options to clean specific types of state
5. **Status Reporting**: Show what was cleaned and current state after cleanup

## User Stories
- As a developer, I want to run `ralph-agent clean` to reset all Ralph state
- As a developer, I want confirmation before Ralph deletes my state files
- As a developer, I want to see what was cleaned up after the command completes
- As a developer, I want the system to be equivalent to fresh init after cleaning

## Success Criteria
- [ ] `ralph-agent clean` command is available in CLI
- [ ] Command removes all state files from .ralph/ directory
- [ ] User confirmation is required before deletion
- [ ] Command reports what was cleaned
- [ ] State after cleaning is equivalent to ralph-agent init

## Acceptance Criteria
- [ ] New `clean` command added to Typer CLI in cli.py
- [ ] Command removes state.json, implementation_plan.json, progress.txt
- [ ] Command optionally removes memory files with --memory flag
- [ ] Confirmation prompt shows what will be deleted
- [ ] Command works even if some state files don't exist
- [ ] Command provides clear success/failure feedback
- [ ] Unit tests verify clean command functionality

## Constraints
- Must follow existing CLI patterns and styling
- Cannot delete user source code or outputs outside .ralph/ directory
- Must handle missing files gracefully

## Edge Cases
- **No state files exist**: Command completes successfully with appropriate message
- **Partial file access**: Clean what can be cleaned, report what couldn't be
- **Interrupted cleanup**: Leave system in clean state, don't leave partial cleanup
- **Permission issues**: Clear error messages for permission problems

## Dependencies
- **Depends on**: SPEC-007 (state cleanup system) for cleanup logic
- **Required by**: None (standalone CLI enhancement)