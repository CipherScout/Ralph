"""Tests for subagent configuration in config.py."""

from pathlib import Path

import pytest
import yaml

from ralph.config import (
    RalphConfig,
    SubagentConfig,
    load_config,
    save_config,
)


class TestSubagentConfig:
    """Tests for SubagentConfig dataclass."""

    def test_default_values(self) -> None:
        """SubagentConfig has sensible defaults."""
        config = SubagentConfig()

        # Test default model assignments
        assert config.model_mapping["research-specialist"] == "sonnet"
        assert config.model_mapping["code-reviewer"] == "sonnet"
        assert config.model_mapping["test-engineer"] == "sonnet"
        assert config.model_mapping["documentation-agent"] == "haiku"
        assert config.model_mapping["product-analyst"] == "haiku"

        # Test other defaults
        assert config.max_parallel == 2
        assert config.timeout_seconds == 300
        assert config.enabled_subagents == [
            "research-specialist",
            "code-reviewer",
            "test-engineer",
            "documentation-agent",
            "product-analyst"
        ]

    def test_model_mapping_has_all_subagents(self) -> None:
        """Model mapping includes all known subagent types."""
        config = SubagentConfig()

        expected_subagents = {
            "research-specialist",
            "code-reviewer",
            "test-engineer",
            "documentation-agent",
            "product-analyst"
        }

        assert set(config.model_mapping.keys()) == expected_subagents

    def test_enabled_subagents_default_to_all(self) -> None:
        """Enabled subagents defaults to all available subagents."""
        config = SubagentConfig()

        # Should have all 5 subagent types enabled by default
        assert len(config.enabled_subagents) == 5
        assert all(name in config.model_mapping for name in config.enabled_subagents)


class TestRalphConfigWithSubagents:
    """Tests for RalphConfig with subagents field."""

    def test_includes_subagents_field(self) -> None:
        """RalphConfig includes subagents field with defaults."""
        config = RalphConfig()

        assert hasattr(config, "subagents")
        assert isinstance(config.subagents, SubagentConfig)

    def test_subagents_field_uses_defaults(self) -> None:
        """Subagents field initializes with proper defaults."""
        config = RalphConfig()

        # Check that subagents field has the expected default model mappings
        assert config.subagents.model_mapping["research-specialist"] == "sonnet"
        assert config.subagents.model_mapping["documentation-agent"] == "haiku"
        assert config.subagents.max_parallel == 2
        assert config.subagents.timeout_seconds == 300


@pytest.fixture
def project_path(tmp_path: Path) -> Path:
    """Create a project directory."""
    ralph_dir = tmp_path / ".ralph"
    ralph_dir.mkdir()
    return tmp_path


class TestSubagentConfigValidation:
    """Tests for validating subagent configuration requirements."""

    def test_all_subagent_types_have_default_models(self) -> None:
        """All subagent types from subagents.py have default model assignments."""
        from ralph.subagents import SUBAGENT_SECURITY_CONSTRAINTS

        config = SubagentConfig()

        # Get the subagent types from the security constraints
        tool_permissions = SUBAGENT_SECURITY_CONSTRAINTS["tool_permissions"]
        assert isinstance(tool_permissions, dict)
        expected_subagent_types = set(tool_permissions.keys())

        # All subagent types should have model assignments
        actual_subagent_types = set(config.model_mapping.keys())
        assert actual_subagent_types == expected_subagent_types

    def test_model_assignments_follow_specification(self) -> None:
        """Model assignments follow the specification.

        Sonnet for complex tasks, haiku for simple ones.
        """
        config = SubagentConfig()

        # Sonnet for research/code-reviewer/test-engineer (complex analysis tasks)
        assert config.model_mapping["research-specialist"] == "sonnet"
        assert config.model_mapping["code-reviewer"] == "sonnet"
        assert config.model_mapping["test-engineer"] == "sonnet"

        # Haiku for documentation/product-analyst (efficient tasks)
        assert config.model_mapping["documentation-agent"] == "haiku"
        assert config.model_mapping["product-analyst"] == "haiku"


class TestSubagentConfigLoading:
    """Tests for loading subagent configuration from YAML."""

    def test_loads_subagent_config_from_yaml(self, project_path: Path) -> None:
        """Loads subagent configuration from YAML file."""
        config_data = {
            "subagents": {
                "max_parallel": 3,
                "timeout_seconds": 600,
                "model_mapping": {
                    "research-specialist": "opus",
                    "code-reviewer": "haiku",
                    "test-engineer": "sonnet",
                    "documentation-agent": "haiku",
                    "product-analyst": "sonnet"
                },
                "enabled_subagents": [
                    "research-specialist",
                    "code-reviewer"
                ]
            }
        }

        config_path = project_path / ".ralph" / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        config = load_config(project_path)

        assert config.subagents.max_parallel == 3
        assert config.subagents.timeout_seconds == 600
        assert config.subagents.model_mapping["research-specialist"] == "opus"
        assert config.subagents.model_mapping["code-reviewer"] == "haiku"
        assert config.subagents.enabled_subagents == ["research-specialist", "code-reviewer"]

    def test_loads_partial_subagent_config(self, project_path: Path) -> None:
        """Loads partial subagent configuration with defaults for missing fields."""
        config_data = {
            "subagents": {
                "max_parallel": 4,
                # timeout_seconds not specified - should use default
                # model_mapping not specified - should use defaults
                # enabled_subagents not specified - should use defaults
            }
        }

        config_path = project_path / ".ralph" / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        config = load_config(project_path)

        assert config.subagents.max_parallel == 4
        assert config.subagents.timeout_seconds == 300  # default
        assert config.subagents.model_mapping["research-specialist"] == "sonnet"  # default
        assert len(config.subagents.enabled_subagents) == 5  # all enabled by default

    def test_uses_defaults_when_no_subagent_config(self, project_path: Path) -> None:
        """Uses default subagent configuration when not specified in YAML."""
        config_data = {
            "project": {
                "name": "test-project"
            }
            # No subagents section
        }

        config_path = project_path / ".ralph" / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        config = load_config(project_path)

        # Should get defaults
        assert config.subagents.max_parallel == 2
        assert config.subagents.timeout_seconds == 300
        assert config.subagents.model_mapping["research-specialist"] == "sonnet"
        assert len(config.subagents.enabled_subagents) == 5


class TestSubagentConfigSaving:
    """Tests for saving subagent configuration to YAML."""

    def test_saves_subagent_config(self, project_path: Path) -> None:
        """Saves subagent configuration to YAML file."""
        config = RalphConfig()
        config.subagents.max_parallel = 4
        config.subagents.timeout_seconds = 450
        config.subagents.model_mapping["research-specialist"] = "opus"
        config.subagents.enabled_subagents = ["research-specialist", "code-reviewer"]

        path = save_config(config, project_path)

        assert path.exists()

        # Verify content
        with open(path) as f:
            data = yaml.safe_load(f)

        assert "subagents" in data
        assert data["subagents"]["max_parallel"] == 4
        assert data["subagents"]["timeout_seconds"] == 450
        assert data["subagents"]["model_mapping"]["research-specialist"] == "opus"
        assert data["subagents"]["enabled_subagents"] == ["research-specialist", "code-reviewer"]

    def test_saves_complete_subagent_config(self, project_path: Path) -> None:
        """Saves complete subagent configuration including all fields."""
        config = RalphConfig()

        # Modify some values from defaults
        config.subagents.max_parallel = 1

        path = save_config(config, project_path)

        # Verify all subagent fields are saved
        with open(path) as f:
            data = yaml.safe_load(f)

        subagents_data = data["subagents"]
        assert "max_parallel" in subagents_data
        assert "timeout_seconds" in subagents_data
        assert "model_mapping" in subagents_data
        assert "enabled_subagents" in subagents_data

        # Verify model mapping has all subagents
        model_mapping = subagents_data["model_mapping"]
        expected_subagents = {
            "research-specialist",
            "code-reviewer",
            "test-engineer",
            "documentation-agent",
            "product-analyst"
        }
        assert set(model_mapping.keys()) == expected_subagents
