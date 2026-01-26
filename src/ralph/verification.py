"""Verification system for task completion criteria.

This module provides verification of task completion by running
backpressure commands and checking their results.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ralph.config import RalphConfig, load_config
from ralph.models import Task


class VerificationStatus(str, Enum):
    """Status of a verification check."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class VerificationResult:
    """Result of a single verification check."""

    name: str
    status: VerificationStatus
    message: str | None = None
    output: str | None = None
    duration_seconds: float = 0.0


@dataclass
class TaskVerificationReport:
    """Complete verification report for a task."""

    task_id: str
    task_description: str
    overall_status: VerificationStatus
    checks: list[VerificationResult] = field(default_factory=list)
    total_duration_seconds: float = 0.0

    @property
    def passed_count(self) -> int:
        """Count of passed checks."""
        return sum(1 for c in self.checks if c.status == VerificationStatus.PASSED)

    @property
    def failed_count(self) -> int:
        """Count of failed checks."""
        return sum(1 for c in self.checks if c.status == VerificationStatus.FAILED)

    @property
    def all_passed(self) -> bool:
        """Check if all checks passed."""
        return all(c.status == VerificationStatus.PASSED for c in self.checks)


@dataclass
class ValidationReport:
    """Complete validation report for the project."""

    test_results: VerificationResult | None = None
    lint_results: VerificationResult | None = None
    typecheck_results: VerificationResult | None = None
    task_reports: list[TaskVerificationReport] = field(default_factory=list)
    overall_status: VerificationStatus = VerificationStatus.PASSED

    @property
    def all_passed(self) -> bool:
        """Check if all validations passed."""
        results = []
        if self.test_results:
            results.append(self.test_results.status == VerificationStatus.PASSED)
        if self.lint_results:
            results.append(self.lint_results.status == VerificationStatus.PASSED)
        if self.typecheck_results:
            results.append(self.typecheck_results.status == VerificationStatus.PASSED)
        return all(results)


def run_command(
    command: str,
    cwd: Path,
    timeout: int = 300,
) -> tuple[int, str, str]:
    """Run a shell command and return results.

    Args:
        command: Command to run
        cwd: Working directory
        timeout: Timeout in seconds

    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return 1, "", str(e)


def verify_command(
    name: str,
    command: str,
    cwd: Path,
    timeout: int = 300,
) -> VerificationResult:
    """Run a verification command.

    Args:
        name: Name of the verification
        command: Command to run
        cwd: Working directory
        timeout: Timeout in seconds

    Returns:
        VerificationResult
    """
    import time

    start = time.time()
    exit_code, stdout, stderr = run_command(command, cwd, timeout)
    duration = time.time() - start

    if exit_code == 0:
        return VerificationResult(
            name=name,
            status=VerificationStatus.PASSED,
            message="Command succeeded",
            output=stdout[:1000] if stdout else None,
            duration_seconds=duration,
        )
    else:
        return VerificationResult(
            name=name,
            status=VerificationStatus.FAILED,
            message=f"Command failed with exit code {exit_code}",
            output=(stderr or stdout)[:1000],
            duration_seconds=duration,
        )


def run_tests(project_root: Path, config: RalphConfig | None = None) -> VerificationResult:
    """Run project tests.

    Args:
        project_root: Project root path
        config: Optional configuration

    Returns:
        VerificationResult
    """
    config = config or load_config(project_root)
    return verify_command("tests", config.build.test_command, project_root)


def run_linting(project_root: Path, config: RalphConfig | None = None) -> VerificationResult:
    """Run project linting.

    Args:
        project_root: Project root path
        config: Optional configuration

    Returns:
        VerificationResult
    """
    config = config or load_config(project_root)
    return verify_command("lint", config.build.lint_command, project_root)


def run_typecheck(project_root: Path, config: RalphConfig | None = None) -> VerificationResult:
    """Run project type checking.

    Args:
        project_root: Project root path
        config: Optional configuration

    Returns:
        VerificationResult
    """
    config = config or load_config(project_root)
    return verify_command("typecheck", config.build.typecheck_command, project_root)


def run_backpressure(
    project_root: Path,
    commands: list[str] | None = None,
    config: RalphConfig | None = None,
) -> list[VerificationResult]:
    """Run all backpressure commands.

    Args:
        project_root: Project root path
        commands: Optional list of commands (uses config if not provided)
        config: Optional configuration

    Returns:
        List of VerificationResults
    """
    config = config or load_config(project_root)
    commands = commands or config.building.backpressure

    results = []
    for i, cmd in enumerate(commands):
        result = verify_command(f"backpressure_{i}", cmd, project_root)
        results.append(result)

    return results


def verify_task(
    task: Task,
    project_root: Path,
    config: RalphConfig | None = None,
) -> TaskVerificationReport:
    """Verify a task's completion criteria.

    Args:
        task: Task to verify
        project_root: Project root path
        config: Optional configuration

    Returns:
        TaskVerificationReport
    """
    import time

    config = config or load_config(project_root)
    start = time.time()

    checks: list[VerificationResult] = []

    # Run backpressure commands
    backpressure_results = run_backpressure(project_root, config=config)
    checks.extend(backpressure_results)

    # Check verification criteria (these are descriptive, not commands)
    for criterion in task.verification_criteria:
        # These would typically be checked by the LLM
        # Here we just note them as needing manual verification
        checks.append(
            VerificationResult(
                name=f"criterion: {criterion[:50]}",
                status=VerificationStatus.SKIPPED,
                message="Requires LLM verification",
            )
        )

    duration = time.time() - start

    # Determine overall status
    failed = any(c.status == VerificationStatus.FAILED for c in checks)
    overall = VerificationStatus.FAILED if failed else VerificationStatus.PASSED

    return TaskVerificationReport(
        task_id=task.id,
        task_description=task.description,
        overall_status=overall,
        checks=checks,
        total_duration_seconds=duration,
    )


def run_full_validation(
    project_root: Path,
    config: RalphConfig | None = None,
) -> ValidationReport:
    """Run full project validation.

    Args:
        project_root: Project root path
        config: Optional configuration

    Returns:
        ValidationReport
    """
    config = config or load_config(project_root)

    report = ValidationReport()

    # Run tests
    report.test_results = run_tests(project_root, config)

    # Run linting
    report.lint_results = run_linting(project_root, config)

    # Run type checking
    report.typecheck_results = run_typecheck(project_root, config)

    # Determine overall status
    if report.all_passed:
        report.overall_status = VerificationStatus.PASSED
    else:
        report.overall_status = VerificationStatus.FAILED

    return report


def format_validation_report(report: ValidationReport) -> str:
    """Format validation report as markdown.

    Args:
        report: ValidationReport to format

    Returns:
        Markdown string
    """
    lines = ["# Validation Report", ""]

    status_emoji = {
        VerificationStatus.PASSED: "✓",
        VerificationStatus.FAILED: "✗",
        VerificationStatus.SKIPPED: "○",
        VerificationStatus.ERROR: "!",
    }

    # Overall status
    emoji = status_emoji[report.overall_status]
    lines.append(f"**Overall Status:** {emoji} {report.overall_status.value.upper()}")
    lines.append("")

    # Tests
    if report.test_results:
        emoji = status_emoji[report.test_results.status]
        lines.append(f"## Tests {emoji}")
        lines.append(f"- Status: {report.test_results.status.value}")
        if report.test_results.message:
            lines.append(f"- Message: {report.test_results.message}")
        lines.append("")

    # Lint
    if report.lint_results:
        emoji = status_emoji[report.lint_results.status]
        lines.append(f"## Linting {emoji}")
        lines.append(f"- Status: {report.lint_results.status.value}")
        if report.lint_results.message:
            lines.append(f"- Message: {report.lint_results.message}")
        lines.append("")

    # Typecheck
    if report.typecheck_results:
        emoji = status_emoji[report.typecheck_results.status]
        lines.append(f"## Type Checking {emoji}")
        lines.append(f"- Status: {report.typecheck_results.status.value}")
        if report.typecheck_results.message:
            lines.append(f"- Message: {report.typecheck_results.message}")
        lines.append("")

    return "\n".join(lines)
