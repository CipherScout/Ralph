"""Tests for the verification system."""

from pathlib import Path

import pytest

from ralph.models import Task
from ralph.persistence import initialize_plan, initialize_state
from ralph.verification import (
    TaskVerificationReport,
    ValidationReport,
    VerificationResult,
    VerificationStatus,
    format_validation_report,
    run_command,
    verify_command,
    verify_task,
)


@pytest.fixture
def project_path(tmp_path: Path) -> Path:
    """Create an initialized project directory."""
    initialize_state(tmp_path)
    initialize_plan(tmp_path)
    return tmp_path


class TestVerificationStatus:
    """Tests for VerificationStatus enum."""

    def test_all_statuses_defined(self) -> None:
        """All expected statuses are defined."""
        assert VerificationStatus.PASSED == "passed"
        assert VerificationStatus.FAILED == "failed"
        assert VerificationStatus.SKIPPED == "skipped"
        assert VerificationStatus.ERROR == "error"


class TestVerificationResult:
    """Tests for VerificationResult."""

    def test_default_values(self) -> None:
        """Has correct default values."""
        result = VerificationResult(
            name="test",
            status=VerificationStatus.PASSED,
        )
        assert result.message is None
        assert result.output is None
        assert result.duration_seconds == 0.0


class TestTaskVerificationReport:
    """Tests for TaskVerificationReport."""

    def test_passed_count(self) -> None:
        """Counts passed checks."""
        report = TaskVerificationReport(
            task_id="task-1",
            task_description="Test task",
            overall_status=VerificationStatus.PASSED,
            checks=[
                VerificationResult(name="check1", status=VerificationStatus.PASSED),
                VerificationResult(name="check2", status=VerificationStatus.PASSED),
                VerificationResult(name="check3", status=VerificationStatus.FAILED),
            ],
        )
        assert report.passed_count == 2

    def test_failed_count(self) -> None:
        """Counts failed checks."""
        report = TaskVerificationReport(
            task_id="task-1",
            task_description="Test task",
            overall_status=VerificationStatus.FAILED,
            checks=[
                VerificationResult(name="check1", status=VerificationStatus.PASSED),
                VerificationResult(name="check2", status=VerificationStatus.FAILED),
            ],
        )
        assert report.failed_count == 1

    def test_all_passed_true(self) -> None:
        """all_passed is True when all pass."""
        report = TaskVerificationReport(
            task_id="task-1",
            task_description="Test task",
            overall_status=VerificationStatus.PASSED,
            checks=[
                VerificationResult(name="check1", status=VerificationStatus.PASSED),
                VerificationResult(name="check2", status=VerificationStatus.PASSED),
            ],
        )
        assert report.all_passed is True

    def test_all_passed_false(self) -> None:
        """all_passed is False when any fail."""
        report = TaskVerificationReport(
            task_id="task-1",
            task_description="Test task",
            overall_status=VerificationStatus.FAILED,
            checks=[
                VerificationResult(name="check1", status=VerificationStatus.PASSED),
                VerificationResult(name="check2", status=VerificationStatus.FAILED),
            ],
        )
        assert report.all_passed is False


class TestValidationReport:
    """Tests for ValidationReport."""

    def test_all_passed_true(self) -> None:
        """all_passed is True when all pass."""
        report = ValidationReport(
            test_results=VerificationResult(name="tests", status=VerificationStatus.PASSED),
            lint_results=VerificationResult(name="lint", status=VerificationStatus.PASSED),
            typecheck_results=VerificationResult(
                name="typecheck", status=VerificationStatus.PASSED
            ),
        )
        assert report.all_passed is True

    def test_all_passed_false(self) -> None:
        """all_passed is False when any fail."""
        report = ValidationReport(
            test_results=VerificationResult(name="tests", status=VerificationStatus.FAILED),
            lint_results=VerificationResult(name="lint", status=VerificationStatus.PASSED),
            typecheck_results=VerificationResult(
                name="typecheck", status=VerificationStatus.PASSED
            ),
        )
        assert report.all_passed is False

    def test_all_passed_with_none_results(self) -> None:
        """all_passed handles None results."""
        report = ValidationReport()
        assert report.all_passed is True  # Empty means nothing failed


class TestRunCommand:
    """Tests for run_command."""

    def test_successful_command(self, tmp_path: Path) -> None:
        """Runs successful command."""
        exit_code, stdout, stderr = run_command("echo hello", tmp_path)
        assert exit_code == 0
        assert "hello" in stdout

    def test_failed_command(self, tmp_path: Path) -> None:
        """Runs failed command."""
        exit_code, stdout, stderr = run_command("exit 1", tmp_path)
        assert exit_code == 1

    def test_nonexistent_command(self, tmp_path: Path) -> None:
        """Handles nonexistent command."""
        exit_code, stdout, stderr = run_command(
            "nonexistent_command_xyz_123", tmp_path
        )
        assert exit_code != 0


class TestVerifyCommand:
    """Tests for verify_command."""

    def test_passing_verification(self, tmp_path: Path) -> None:
        """Returns passed for successful command."""
        result = verify_command("test", "echo success", tmp_path)
        assert result.status == VerificationStatus.PASSED
        assert result.name == "test"

    def test_failing_verification(self, tmp_path: Path) -> None:
        """Returns failed for failed command."""
        result = verify_command("test", "exit 1", tmp_path)
        assert result.status == VerificationStatus.FAILED

    def test_captures_output(self, tmp_path: Path) -> None:
        """Captures command output."""
        result = verify_command("test", "echo hello", tmp_path)
        assert result.output is not None
        assert "hello" in result.output


class TestVerifyTask:
    """Tests for verify_task."""

    def test_verifies_task(self, project_path: Path) -> None:
        """Verifies a task."""
        task = Task(
            id="task-1",
            description="Test task",
            priority=1,
            verification_criteria=["Tests pass", "Lint passes"],
        )

        report = verify_task(task, project_path)

        assert report.task_id == "task-1"
        assert len(report.checks) > 0

    def test_includes_criteria_as_skipped(self, project_path: Path) -> None:
        """Includes verification criteria as skipped checks."""
        task = Task(
            id="task-1",
            description="Test task",
            priority=1,
            verification_criteria=["Manual check needed"],
        )

        report = verify_task(task, project_path)

        skipped = [c for c in report.checks if c.status == VerificationStatus.SKIPPED]
        assert len(skipped) >= 1


class TestFormatValidationReport:
    """Tests for format_validation_report."""

    def test_formats_passed_report(self) -> None:
        """Formats passed report."""
        report = ValidationReport(
            test_results=VerificationResult(
                name="tests",
                status=VerificationStatus.PASSED,
                message="All tests pass",
            ),
            overall_status=VerificationStatus.PASSED,
        )

        output = format_validation_report(report)

        assert "Validation Report" in output
        assert "PASSED" in output
        assert "Tests" in output

    def test_formats_failed_report(self) -> None:
        """Formats failed report."""
        report = ValidationReport(
            test_results=VerificationResult(
                name="tests",
                status=VerificationStatus.FAILED,
                message="5 tests failed",
            ),
            overall_status=VerificationStatus.FAILED,
        )

        output = format_validation_report(report)

        assert "FAILED" in output
        assert "5 tests failed" in output

    def test_includes_all_sections(self) -> None:
        """Includes all sections."""
        report = ValidationReport(
            test_results=VerificationResult(name="tests", status=VerificationStatus.PASSED),
            lint_results=VerificationResult(name="lint", status=VerificationStatus.PASSED),
            typecheck_results=VerificationResult(
                name="typecheck", status=VerificationStatus.PASSED
            ),
            overall_status=VerificationStatus.PASSED,
        )

        output = format_validation_report(report)

        assert "Tests" in output
        assert "Linting" in output
        assert "Type Checking" in output
