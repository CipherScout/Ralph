# SPEC-009: File Organization - Move Progress.txt to .ralph Directory

**JTBD**: When Ralph creates progress tracking files, I want them organized in the .ralph directory alongside other state files, so my project root stays clean and all Ralph files are in one place.

## Problem Statement
Ralph currently creates progress.txt in the project root directory, which clutters the user's project and is inconsistent with other Ralph state files (state.json, implementation_plan.json) that are properly organized in the .ralph/ directory.

## Functional Requirements
1. **File Relocation**: Move progress.txt creation from project root to .ralph/ directory
2. **Path Updates**: Update all code references to use .ralph/progress.txt
3. **Migration Handling**: Handle existing progress.txt files during transition
4. **Consistency**: Ensure all Ralph-generated files follow the same organization pattern
5. **Documentation**: Update any documentation that references progress.txt location

## User Stories
- As a developer, I want my project root to stay clean of Ralph temporary files
- As a developer, I want all Ralph files organized in the .ralph directory
- As a developer, I want consistent file organization across all Ralph operations

## Success Criteria
- [ ] progress.txt is created in .ralph/ directory, not project root
- [ ] All code references updated to use .ralph/progress.txt
- [ ] Existing progress.txt files are handled gracefully during migration
- [ ] No Ralph temporary files remain in project root
- [ ] File organization is consistent across all Ralph operations

## Acceptance Criteria
- [ ] Progress file creation updated in relevant modules
- [ ] All file path references updated throughout codebase
- [ ] Migration logic handles existing progress.txt files
- [ ] Unit tests updated to expect .ralph/progress.txt
- [ ] Integration tests verify correct file organization
- [ ] No regression in progress tracking functionality
- [ ] Clean command includes progress.txt in cleanup

## Constraints
- Must maintain backward compatibility during transition
- Cannot break existing progress tracking functionality
- Must work with all existing file operations

## Edge Cases
- **Existing progress.txt in root**: Move or merge with new location
- **Permission issues with .ralph/ directory**: Create directory if needed
- **Concurrent access to progress file**: Handle file locking appropriately
- **Missing .ralph/ directory**: Create automatically

## Dependencies
- **Depends on**: None (standalone file organization change)
- **Required by**: SPEC-007 and SPEC-008 (cleanup commands need to know correct location)