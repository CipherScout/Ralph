# Technical Architecture (Discovery Phase)

## System Overview
Comprehensive refactor of the Ralph agentic coding loop to address 9 critical reliability, determinism, and usability issues. The refactor focuses on making Ralph a production-ready, predictable development automation system through improved validation reliability, universal tool access, better memory management, and proper resource tracking.

## Technology Stack
- **Language**: Python 3.11+
- **CLI Framework**: Typer with Rich for display
- **Agent Framework**: Claude Agent SDK (anthropics/claude-agent-sdk-python)
- **Configuration**: Pydantic for config models, YAML for user config files
- **Testing**: pytest with asyncio support, maintaining 554+ existing tests
- **Code Quality**: ruff (linting), mypy (type checking)
- **State Management**: JSON files in .ralph/ directory

## Integration Points
- **Claude Agent SDK**: Core agent orchestration and tool management
- **Context7 MCP Server**: Tool discovery and Claude Agent SDK documentation queries
- **Ralph MCP Tools**: Custom MCP tools for task management and state tracking
- **File System**: State persistence in .ralph/ directory structure

## Key Architecture Changes

### 1. Enhanced RalphSDKClient
- **Universal Tool Access**: Remove all phase-based tool restrictions
- **Context Window Monitoring**: Real-time context usage tracking with 80-85% limits
- **Token/Cost Tracking**: Accurate resource consumption measurement
- **Completion Promise Handling**: Proper detection of agent completion signals

### 2. Improved Executors (executors.py)
- **ValidationExecutor**: Circuit breaker pattern, clear exit conditions, timeout protection
- **PlanningExecutor**: Spec file linkage in task creation, enhanced memory integration
- **BuildingExecutor**: Automatic spec file injection, improved task context
- **All Executors**: Universal tool access, better memory utilization

### 3. Deterministic Memory System
- **Automated Memory Creation**: Phase transitions, iterations, key decisions
- **Structured Storage**: .ralph/memory/ directory with organized markdown files
- **Context Injection**: Relevant memory automatically included in agent context
- **Memory Lifecycle**: Creation, retrieval, cleanup managed by Ralph harness

### 4. Enhanced State Management
- **File Organization**: All Ralph files in .ralph/ directory (including progress.txt)
- **State Cleanup**: Automated cleanup after cycle completion + manual clean command
- **State Persistence**: Enhanced models with spec file references and memory tracking

### 5. CLI Enhancements
- **Clean Command**: `ralph-agent clean` for manual state reset
- **Better Display**: Accurate cost/token reporting, progress indicators
- **User Experience**: Maintain existing interfaces while improving backend

## Security Considerations
- **Tool Permissions**: Maintain appropriate security boundaries while enabling universal access
- **File System**: Restrict Ralph operations to project directory and .ralph/ subdirectory
- **State Cleanup**: Prevent accidental deletion of user source code

## Performance Requirements
- **Context Efficiency**: Utilize 80-85% of context window before session termination
- **Memory Overhead**: Minimize memory system impact on context usage
- **Tool Discovery**: Cache Context7 queries to avoid repeated API calls

## Error Handling & Reliability
- **Circuit Breaker**: Prevent infinite loops in validation and other phases
- **Graceful Degradation**: Handle missing files, API failures, tool restrictions gracefully
- **Deterministic Behavior**: Reduce non-deterministic outcomes through better state management

## Testing Strategy
- **Test-Driven Development**: Write tests before implementing changes
- **Maintain Coverage**: All 554+ existing tests must continue to pass
- **Integration Tests**: Verify spec file integration, memory system, tool access across phases
- **Unit Tests**: Test individual components (memory system, tool registry, cleanup functions)

## Deployment Considerations
- **Backward Compatibility**: Existing CLI commands and user workflows remain unchanged
- **Migration**: Handle existing state files during upgrade
- **Configuration**: Enhanced config options for context limits, cleanup behavior, memory settings

---
*Planning phase will add detailed architecture below this line.*