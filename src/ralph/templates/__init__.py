"""Template loading and rendering for Ralph prompts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

TEMPLATES_DIR = Path(__file__).parent


def get_template_path(name: str) -> Path:
    """Get path to a template file.

    Args:
        name: Template name (without extension)

    Returns:
        Path to template file

    Raises:
        FileNotFoundError: If template doesn't exist
    """
    path = TEMPLATES_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {name}")
    return path


def load_template(name: str) -> str:
    """Load a template file.

    Args:
        name: Template name (without extension)

    Returns:
        Template content
    """
    path = get_template_path(name)
    return path.read_text()


def render_template(name: str, **kwargs: Any) -> str:
    """Load and render a template with variables.

    Args:
        name: Template name (without extension)
        **kwargs: Variables to substitute

    Returns:
        Rendered template
    """
    template = load_template(name)

    # Simple string formatting
    for key, value in kwargs.items():
        placeholder = f"{{{key}}}"
        if isinstance(value, list):
            # Format lists as markdown
            value = "\n".join(f"- {item}" for item in value) if value else "(none)"
        elif value is None:
            value = "(none)"
        template = template.replace(placeholder, str(value))

    return template


__all__ = [
    "get_template_path",
    "load_template",
    "render_template",
]
