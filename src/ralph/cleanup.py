"""State cleanup utilities for Ralph.

Handles cleanup of workflow state files after cycle completion.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CleanupResult:
    """Result of a cleanup operation."""

    files_deleted: list[str] = field(default_factory=list)
    files_skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Returns True if no errors occurred."""
        return len(self.errors) == 0

    @property
    def any_cleaned(self) -> bool:
        """Returns True if at least one file was cleaned up."""
        return len(self.files_deleted) > 0


def get_cleanup_targets(project_root: Path, include_memory: bool = False) -> list[Path]:
    """Get list of files/directories to clean up.

    Args:
        project_root: Path to project root
        include_memory: Whether to include memory files

    Returns:
        List of paths to clean up
    """
    ralph_dir = project_root / ".ralph"
    targets = []

    # Core state files (always included)
    targets.append(ralph_dir / "state.json")
    targets.append(ralph_dir / "implementation_plan.json")
    targets.append(ralph_dir / "injections.json")

    # Progress file (currently at project root)
    targets.append(project_root / "progress.txt")

    # Memory files (optional)
    if include_memory:
        targets.append(ralph_dir / "MEMORY.md")
        targets.append(ralph_dir / "memory")  # Directory

    return targets


def cleanup_state_files(
    project_root: Path,
    include_memory: bool = False,
) -> CleanupResult:
    """Clean up Ralph state files.

    Removes state files while preserving user configuration.

    Args:
        project_root: Path to project root
        include_memory: Whether to also clean up memory files

    Returns:
        CleanupResult with details of what was deleted
    """
    result = CleanupResult()
    targets = get_cleanup_targets(project_root, include_memory)

    for target in targets:
        if not target.exists():
            logger.debug("Cleanup target does not exist: %s", target)
            result.files_skipped.append(str(target))
            continue

        try:
            if target.is_dir():
                shutil.rmtree(target)
                logger.info("Deleted directory: %s", target)
            else:
                target.unlink()
                logger.info("Deleted file: %s", target)
            result.files_deleted.append(str(target))
        except PermissionError:
            error_msg = f"Permission denied: {target}"
            logger.error(error_msg)
            result.errors.append(error_msg)
        except OSError as e:
            error_msg = f"Failed to delete {target}: {e}"
            logger.error(error_msg)
            result.errors.append(error_msg)

    return result
