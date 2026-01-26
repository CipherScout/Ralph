"""Configuration management for Ralph.

Handles YAML configuration loading, environment variables,
and cost control settings.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class CostLimits:
    """Cost control limits."""

    per_iteration: float = 2.0
    per_session: float = 50.0
    total: float = 200.0


@dataclass
class ContextConfig:
    """Context window management settings."""

    budget_percent: int = 60
    handoff_threshold_percent: int = 75
    total_capacity: int = 200_000

    # Context loading limits
    max_progress_entries: int = 20
    max_files_in_memory: int = 10
    max_session_history: int = 50


@dataclass
class PhaseConfig:
    """Configuration for a specific phase."""

    human_in_loop: bool = False
    max_questions: int = 10
    task_size_tokens: int = 30_000
    dependency_analysis: bool = True
    max_iterations: int = 100
    require_human_approval: bool = False
    backpressure: list[str] = field(default_factory=list)


@dataclass
class SafetyConfig:
    """Safety and sandboxing settings."""

    sandbox_enabled: bool = True
    blocked_commands: list[str] = field(default_factory=list)
    git_read_only: bool = True
    allowed_git_operations: list[str] = field(default_factory=list)
    max_retries: int = 3


@dataclass
class BuildConfig:
    """Build system configuration."""

    tool: str = "uv"
    test_command: str = "uv run pytest"
    lint_command: str = "uv run ruff check ."
    typecheck_command: str = "uv run mypy ."
    format_command: str = "uv run ruff format ."


@dataclass
class ProjectConfig:
    """Project-level configuration."""

    name: str = ""
    root: str = "."
    python_version: str = "3.13"


@dataclass
class RalphConfig:
    """Complete Ralph configuration.

    Can be loaded from .ralph/config.yaml or constructed with defaults.
    Environment variables override config file values.
    """

    project: ProjectConfig = field(default_factory=ProjectConfig)
    build: BuildConfig = field(default_factory=BuildConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    cost_limits: CostLimits = field(default_factory=CostLimits)

    # Phase-specific configs
    discovery: PhaseConfig = field(default_factory=lambda: PhaseConfig(
        human_in_loop=True,
        max_questions=10,
    ))
    planning: PhaseConfig = field(default_factory=lambda: PhaseConfig(
        task_size_tokens=30_000,
        dependency_analysis=True,
    ))
    building: PhaseConfig = field(default_factory=lambda: PhaseConfig(
        max_iterations=100,
        backpressure=["uv run pytest", "uv run mypy .", "uv run ruff check ."],
    ))
    validation: PhaseConfig = field(default_factory=lambda: PhaseConfig(
        require_human_approval=True,
    ))

    # Model configuration
    primary_model: str = "claude-sonnet-4-20250514"
    planning_model: str = "claude-opus-4-20250514"

    # Runtime settings
    max_iterations: int = 100
    circuit_breaker_failures: int = 3
    circuit_breaker_stagnation: int = 5


def _parse_phase_config(data: dict[str, Any]) -> PhaseConfig:
    """Parse phase configuration from dict."""
    return PhaseConfig(
        human_in_loop=data.get("human_in_loop", False),
        max_questions=data.get("max_questions", 10),
        task_size_tokens=data.get("task_size_tokens", 30_000),
        dependency_analysis=data.get("dependency_analysis", True),
        max_iterations=data.get("max_iterations", 100),
        require_human_approval=data.get("require_human_approval", False),
        backpressure=data.get("backpressure", []),
    )


def load_config(project_root: Path) -> RalphConfig:
    """Load configuration from .ralph/config.yaml.

    Falls back to defaults if config file doesn't exist.
    Environment variables override config file values.

    Args:
        project_root: Path to project root

    Returns:
        Loaded RalphConfig
    """
    config = RalphConfig()
    config_path = project_root / ".ralph" / "config.yaml"

    # Load from file if exists
    if config_path.exists():
        try:
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}

            # Parse project config
            if "project" in data:
                proj = data["project"]
                config.project = ProjectConfig(
                    name=proj.get("name", ""),
                    root=proj.get("root", "."),
                    python_version=proj.get("python_version", "3.13"),
                )

            # Parse build config
            if "build" in data:
                build = data["build"]
                config.build = BuildConfig(
                    tool=build.get("tool", "uv"),
                    test_command=build.get("test_command", "uv run pytest"),
                    lint_command=build.get("lint_command", "uv run ruff check ."),
                    typecheck_command=build.get("typecheck_command", "uv run mypy ."),
                    format_command=build.get("format_command", "uv run ruff format ."),
                )

            # Parse context config
            if "context" in data:
                ctx = data["context"]
                config.context = ContextConfig(
                    budget_percent=ctx.get("budget_percent", 60),
                    handoff_threshold_percent=ctx.get("handoff_threshold_percent", 75),
                    total_capacity=ctx.get("total_capacity", 200_000),
                    max_progress_entries=ctx.get("max_progress_entries", 20),
                    max_files_in_memory=ctx.get("max_files_in_memory", 10),
                    max_session_history=ctx.get("max_session_history", 50),
                )

            # Parse safety config
            if "safety" in data:
                safety = data["safety"]
                config.safety = SafetyConfig(
                    sandbox_enabled=safety.get("sandbox_enabled", True),
                    blocked_commands=safety.get("blocked_commands", []),
                    git_read_only=safety.get("git_read_only", True),
                    allowed_git_operations=safety.get("allowed_git_operations", []),
                )
                if "cost_limits" in safety:
                    limits = safety["cost_limits"]
                    config.cost_limits = CostLimits(
                        per_iteration=limits.get("per_iteration", 2.0),
                        per_session=limits.get("per_session", 50.0),
                        total=limits.get("total", 200.0),
                    )

            # Parse phase configs
            if "phases" in data:
                phases = data["phases"]
                if "discovery" in phases:
                    config.discovery = _parse_phase_config(phases["discovery"])
                if "planning" in phases:
                    config.planning = _parse_phase_config(phases["planning"])
                if "building" in phases:
                    config.building = _parse_phase_config(phases["building"])
                if "validation" in phases:
                    config.validation = _parse_phase_config(phases["validation"])

        except yaml.YAMLError as e:
            logger.warning("Failed to parse config file %s: %s. Using defaults.", config_path, e)

    # Override with environment variables
    config = _apply_env_overrides(config)

    return config


def _apply_env_overrides(config: RalphConfig) -> RalphConfig:
    """Apply environment variable overrides to config.

    Args:
        config: Base configuration

    Returns:
        Configuration with env overrides applied
    """
    # Model overrides
    if env_model := os.environ.get("RALPH_PRIMARY_MODEL"):
        config.primary_model = env_model
    if env_model := os.environ.get("RALPH_PLANNING_MODEL"):
        config.planning_model = env_model

    # Runtime overrides
    if env_val := os.environ.get("RALPH_MAX_ITERATIONS"):
        config.max_iterations = int(env_val)
    if env_val := os.environ.get("RALPH_MAX_COST_USD"):
        config.cost_limits.total = float(env_val)
    if env_val := os.environ.get("RALPH_CONTEXT_BUDGET_PERCENT"):
        config.context.budget_percent = int(env_val)
    if env_val := os.environ.get("RALPH_CIRCUIT_BREAKER_FAILURES"):
        config.circuit_breaker_failures = int(env_val)
    if env_val := os.environ.get("RALPH_CIRCUIT_BREAKER_STAGNATION"):
        config.circuit_breaker_stagnation = int(env_val)

    return config


def save_config(config: RalphConfig, project_root: Path) -> Path:
    """Save configuration to .ralph/config.yaml.

    Args:
        config: Configuration to save
        project_root: Path to project root

    Returns:
        Path to saved config file
    """
    config_path = project_root / ".ralph" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "project": {
            "name": config.project.name,
            "root": config.project.root,
            "python_version": config.project.python_version,
        },
        "build": {
            "tool": config.build.tool,
            "test_command": config.build.test_command,
            "lint_command": config.build.lint_command,
            "typecheck_command": config.build.typecheck_command,
        },
        "phases": {
            "discovery": {
                "human_in_loop": config.discovery.human_in_loop,
                "max_questions": config.discovery.max_questions,
            },
            "planning": {
                "task_size_tokens": config.planning.task_size_tokens,
                "dependency_analysis": config.planning.dependency_analysis,
            },
            "building": {
                "max_iterations": config.building.max_iterations,
                "backpressure": config.building.backpressure,
            },
            "validation": {
                "require_human_approval": config.validation.require_human_approval,
            },
        },
        "context": {
            "budget_percent": config.context.budget_percent,
            "handoff_threshold_percent": config.context.handoff_threshold_percent,
            "max_progress_entries": config.context.max_progress_entries,
            "max_files_in_memory": config.context.max_files_in_memory,
            "max_session_history": config.context.max_session_history,
        },
        "safety": {
            "sandbox_enabled": config.safety.sandbox_enabled,
            "blocked_commands": config.safety.blocked_commands,
            "cost_limits": {
                "per_iteration": config.cost_limits.per_iteration,
                "per_session": config.cost_limits.per_session,
                "total": config.cost_limits.total,
            },
        },
    }

    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    return config_path


def create_default_config(project_root: Path, project_name: str = "") -> RalphConfig:
    """Create and save a default configuration.

    Args:
        project_root: Path to project root
        project_name: Optional project name

    Returns:
        Created configuration
    """
    config = RalphConfig()
    config.project.name = project_name or project_root.name
    config.project.root = "."

    # Set default backpressure commands
    config.building.backpressure = [
        "uv run pytest",
        "uv run mypy .",
        "uv run ruff check .",
    ]

    # Set default safety blocked commands
    config.safety.blocked_commands = [
        "rm -rf",
        "docker rm",
        "pip install",
        "python -m venv",
    ]

    config.safety.allowed_git_operations = [
        "status",
        "log",
        "diff",
    ]

    save_config(config, project_root)
    return config


@dataclass
class CostController:
    """Controller for enforcing cost limits.

    Tracks costs and determines when limits are exceeded.
    """

    limits: CostLimits
    iteration_cost: float = 0.0
    session_cost: float = 0.0
    total_cost: float = 0.0

    def add_cost(self, cost: float) -> None:
        """Add cost to all trackers."""
        self.iteration_cost += cost
        self.session_cost += cost
        self.total_cost += cost

    def start_new_iteration(self) -> None:
        """Reset iteration cost tracker."""
        self.iteration_cost = 0.0

    def start_new_session(self) -> None:
        """Reset session cost tracker."""
        self.session_cost = 0.0
        self.iteration_cost = 0.0

    def check_limits(self) -> tuple[bool, str | None]:
        """Check if any cost limit is exceeded.

        Returns:
            Tuple of (within_limits, violation_reason)
        """
        if self.iteration_cost > self.limits.per_iteration:
            return False, f"iteration_cost_exceeded:${self.iteration_cost:.2f}"
        if self.session_cost > self.limits.per_session:
            return False, f"session_cost_exceeded:${self.session_cost:.2f}"
        if self.total_cost > self.limits.total:
            return False, f"total_cost_exceeded:${self.total_cost:.2f}"
        return True, None

    def get_remaining_budget(self) -> dict[str, float]:
        """Get remaining budget for each limit."""
        return {
            "iteration": max(0, self.limits.per_iteration - self.iteration_cost),
            "session": max(0, self.limits.per_session - self.session_cost),
            "total": max(0, self.limits.total - self.total_cost),
        }


def create_cost_controller(config: RalphConfig) -> CostController:
    """Create a cost controller from config.

    Args:
        config: Ralph configuration

    Returns:
        Configured CostController
    """
    return CostController(limits=config.cost_limits)
