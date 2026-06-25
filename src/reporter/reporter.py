"""
Reporter
--------
Runs generated tests via pytest, collects results, and produces a rich report.
"""
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class TestRunResult:
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    total: int = 0
    duration: float = 0.0
    failures: list[dict] = field(default_factory=list)
    output: str = ""
    exit_code: int = 0


@dataclass
class Report:
    repo_path: str
    diff_summary: str
    generated_tests: list  # list[GeneratedTest]
    impact: list[dict]
    run_result: Optional[TestRunResult] = None
    tdd_stub: str = ""


def run_tests_in_temp(test_code: str, repo_path: str) -> TestRunResult:
    """Write test code to a temp file, run pytest, return results."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        prefix="codeguard_test_",
        dir=repo_path,
        delete=False,
    ) as f:
        f.write(test_code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", tmp_path, "-v",
             "--tb=short", "--no-header", "-q"],
            capture_output=True,
            text=True,
            cwd=repo_path,
            timeout=60,
        )
        output = result.stdout + result.stderr
        return _parse_pytest_output(output, result.returncode)
    except subprocess.TimeoutExpired:
        return TestRunResult(output="Timeout after 60s", exit_code=1)
    except Exception as e:
        return TestRunResult(output=str(e), exit_code=1)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _parse_pytest_output(output: str, exit_code: int) -> TestRunResult:
    result = TestRunResult(output=output, exit_code=exit_code)

    # Parse summary line like: "3 passed, 1 failed, 0 errors in 0.42s"
    import re
    summary = re.search(
        r"(\d+) passed(?:,\s*(\d+) failed)?(?:,\s*(\d+) error)?.*?in ([\d.]+)s",
        output,
        re.IGNORECASE,
    )
    if summary:
        result.passed = int(summary.group(1) or 0)
        result.failed = int(summary.group(2) or 0)
        result.errors = int(summary.group(3) or 0)
        result.duration = float(summary.group(4) or 0)
        result.total = result.passed + result.failed + result.errors

    # Parse failures
    fail_blocks = re.findall(r"FAILED (.+?) - (.+)", output)
    for test_id, reason in fail_blocks:
        result.failures.append({"test": test_id.strip(), "reason": reason.strip()})

    return result


class Reporter:
    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def build_report(
        self,
        diff_result,
        generated_tests: list,
        impact: list[dict],
        run_results: Optional[list[TestRunResult]] = None,
        tdd_stub: str = "",
    ) -> Report:
        report = Report(
            repo_path=self.repo_path,
            diff_summary=diff_result.summary,
            generated_tests=generated_tests,
            impact=impact,
            tdd_stub=tdd_stub,
        )

        # Aggregate run results
        if run_results:
            agg = TestRunResult()
            for r in run_results:
                agg.passed += r.passed
                agg.failed += r.failed
                agg.errors += r.errors
                agg.total += r.total
                agg.duration += r.duration
                agg.failures.extend(r.failures)
                agg.output += r.output + "\n"
            report.run_result = agg

        return report

    def to_dict(self, report: Report) -> dict:
        return {
            "repo": report.repo_path,
            "diff_summary": report.diff_summary,
            "generated_tests": [
                {
                    "function": t.function_name,
                    "filepath": t.filepath,
                    "change_type": t.change_type,
                    "test_functions": t.test_functions,
                    "edge_cases": t.edge_cases,
                    "explanation": t.explanation,
                    "test_code": t.test_code,
                }
                for t in report.generated_tests
            ],
            "impact": report.impact,
            "run_result": (
                {
                    "passed": report.run_result.passed,
                    "failed": report.run_result.failed,
                    "errors": report.run_result.errors,
                    "total": report.run_result.total,
                    "duration": report.run_result.duration,
                    "failures": report.run_result.failures,
                }
                if report.run_result
                else None
            ),
        }

    def save_json(self, report: Report, output_path: str):
        with open(output_path, "w") as f:
            json.dump(self.to_dict(report), f, indent=2)

    def save_tests(self, report: Report, output_dir: str):
        """Save all generated tests to files."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        for t in report.generated_tests:
            safe_name = t.function_name.replace("/", "_")
            path = out / f"test_codeguard_{safe_name}.py"
            path.write_text(t.test_code)
        return [str(out / f"test_codeguard_{t.function_name}.py") for t in report.generated_tests]
