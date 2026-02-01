"""Tests for configuration management."""

from pathlib import Path

import pytest
import yaml

from ralph.config import (
    BuildConfig,
    CostLimits,
    PhaseConfig,
    ProjectConfig,
    RalphConfig,
    SafetyConfig,
    create_default_config,
    load_config,
    save_config,
)


@pytest.fixture
def project_path(tmp_path: Path) -> Path:
    """Create a project directory."""
    ralph_dir = tmp_path / ".ralph"
    ralph_dir.mkdir()
    return tmp_path


class TestRalphConfig:
    """Tests for RalphConfig dataclass."""

    def test_default_values(self) -> None:
        """Default config has sensible values."""
        config = RalphConfig()

        assert config.primary_model == "claude-sonnet-4-20250514"
        assert config.planning_model == "claude-opus-4-20250514"
        assert config.max_iterations == 100
        assert config.cost_limits.total == 100.0

    def test_nested_configs(self) -> None:
        """Nested configs are properly initialized."""
        config = RalphConfig()

        assert isinstance(config.project, ProjectConfig)
        assert isinstance(config.build, BuildConfig)
        assert isinstance(config.safety, SafetyConfig)

    def test_phase_configs(self) -> None:
        """Phase configs have correct defaults."""
        config = RalphConfig()

        assert config.building.max_iterations == 100
        assert config.validation.require_human_approval is True


class TestLoadConfig:
    """Tests for load_config."""

    def test_loads_defaults_when_no_file(self, project_path: Path) -> None:
        """Uses defaults when config file doesn't exist."""
        config = load_config(project_path)

        assert config.primary_model == "claude-sonnet-4-20250514"
        assert config.max_iterations == 100

    def test_loads_from_yaml(self, project_path: Path) -> None:
        """Loads configuration from YAML file."""
        config_data = {
            "project": {
                "name": "test-project",
                "python_version": "3.12",
            },
            "build": {
                "tool": "uv",
                "test_command": "uv run pytest -v",
            },
            "safety": {
                "sandbox_enabled": False,
                "cost_limits": {
                    "per_iteration": 5.0,
                    "total": 500.0,
                },
            },
        }

        config_path = project_path / ".ralph" / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        config = load_config(project_path)

        assert config.project.name == "test-project"
        assert config.project.python_version == "3.12"
        assert config.build.test_command == "uv run pytest -v"
        assert config.safety.sandbox_enabled is False
        assert config.cost_limits.per_iteration == 5.0
        assert config.cost_limits.total == 500.0

    def test_loads_phase_configs(self, project_path: Path) -> None:
        """Loads phase-specific configurations."""
        config_data = {
            "phases": {
                "building": {
                    "max_iterations": 50,
                    "backpressure": ["pytest", "mypy"],
                },
            },
        }

        config_path = project_path / ".ralph" / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        config = load_config(project_path)

        assert config.building.max_iterations == 50
        assert config.building.backpressure == ["pytest", "mypy"]

    def test_handles_invalid_yaml(self, project_path: Path) -> None:
        """Uses defaults for invalid YAML."""
        config_path = project_path / ".ralph" / "config.yaml"
        config_path.write_text("invalid: yaml: content: {{{{")

        config = load_config(project_path)

        # Should still get defaults
        assert config.primary_model == "claude-sonnet-4-20250514"


class TestEnvOverrides:
    """Tests for environment variable overrides."""

    def test_overrides_model(self, project_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Environment variables override config values."""
        monkeypatch.setenv("RALPH_PRIMARY_MODEL", "custom-model")
        monkeypatch.setenv("RALPH_PLANNING_MODEL", "planning-model")

        config = load_config(project_path)

        assert config.primary_model == "custom-model"
        assert config.planning_model == "planning-model"

    def test_overrides_numeric_values(
        self, project_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Numeric environment variables are parsed."""
        monkeypatch.setenv("RALPH_MAX_ITERATIONS", "50")
        monkeypatch.setenv("RALPH_MAX_COST_USD", "100.0")

        config = load_config(project_path)

        assert config.max_iterations == 50
        assert config.cost_limits.total == 100.0


class TestSaveConfig:
    """Tests for save_config."""

    def test_saves_config(self, project_path: Path) -> None:
        """Saves configuration to YAML file."""
        config = RalphConfig()
        config.project.name = "my-project"
        config.cost_limits.total = 300.0

        path = save_config(config, project_path)

        assert path.exists()
        assert path.name == "config.yaml"

        # Verify content
        with open(path) as f:
            data = yaml.safe_load(f)

        assert data["project"]["name"] == "my-project"
        assert data["safety"]["cost_limits"]["total"] == 300.0

    def test_creates_ralph_dir(self, tmp_path: Path) -> None:
        """Creates .ralph directory if needed."""
        config = RalphConfig()
        save_config(config, tmp_path)

        assert (tmp_path / ".ralph").is_dir()
        assert (tmp_path / ".ralph" / "config.yaml").exists()


class TestCreateDefaultConfig:
    """Tests for create_default_config."""

    def test_creates_config_file(self, tmp_path: Path) -> None:
        """Creates config file with defaults."""
        config = create_default_config(tmp_path, "test-project")

        assert config.project.name == "test-project"
        assert (tmp_path / ".ralph" / "config.yaml").exists()

    def test_sets_project_name_from_path(self, tmp_path: Path) -> None:
        """Uses directory name if project name not provided."""
        config = create_default_config(tmp_path)
        assert config.project.name == tmp_path.name

    def test_sets_default_backpressure(self, tmp_path: Path) -> None:
        """Sets default backpressure commands."""
        config = create_default_config(tmp_path)

        assert "uv run pytest" in config.building.backpressure
        assert "uv run mypy ." in config.building.backpressure

    def test_sets_default_blocked_commands(self, tmp_path: Path) -> None:
        """Sets default blocked commands."""
        config = create_default_config(tmp_path)

        assert "rm -rf" in config.safety.blocked_commands
        assert "pip install" in config.safety.blocked_commands


class TestCostLimits:
    """Tests for CostLimits."""

    def test_default_limits(self) -> None:
        """Default limits are set."""
        limits = CostLimits()

        assert limits.per_iteration == 10.0
        assert limits.per_session == 50.0
        assert limits.total == 100.0


class TestBuildConfig:
    """Tests for BuildConfig."""

    def test_defaults_to_uv(self) -> None:
        """Defaults to uv for all commands."""
        config = BuildConfig()

        assert config.tool == "uv"
        assert "uv run" in config.test_command
        assert "uv run" in config.lint_command
        assert "uv run" in config.typecheck_command


class TestPhaseConfig:
    """Tests for PhaseConfig."""

    def test_default_values(self) -> None:
        """Has sensible defaults."""
        config = PhaseConfig()

        assert config.max_iterations == 100
        assert config.backpressure == []
