"""
Git Diff Analyzer
-----------------
Parses git diffs to extract changed functions, files, and affected test hints.
Works with both real git repos and raw diff strings.
"""
import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import git
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False


@dataclass
class ChangedFunction:
    name: str
    filepath: str
    change_type: str  # "added", "modified", "deleted"
    old_code: str = ""
    new_code: str = ""
    lineno: int = 0


@dataclass
class DiffResult:
    changed_files: list[str] = field(default_factory=list)
    changed_functions: list[ChangedFunction] = field(default_factory=list)
    added_lines: list[str] = field(default_factory=list)
    removed_lines: list[str] = field(default_factory=list)
    raw_diff: str = ""
    commit_message: str = ""
    summary: str = ""


def _extract_functions_from_source(source: str, filepath: str) -> dict[str, str]:
    """Return {func_name: source_code} from a Python source string."""
    funcs = {}
    try:
        tree = ast.parse(source)
        lines = source.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = node.lineno - 1
                end = node.end_lineno
                funcs[node.name] = "\n".join(lines[start:end])
    except SyntaxError:
        pass
    return funcs


def _parse_unified_diff(diff_text: str) -> list[dict]:
    """Parse unified diff format into file-level diffs."""
    file_diffs = []
    current = None

    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            if current:
                file_diffs.append(current)
            current = {"header": line, "hunks": [], "filepath": "", "added": [], "removed": []}
        elif line.startswith("+++ b/") and current is not None:
            current["filepath"] = line[6:]
        elif line.startswith("+") and not line.startswith("+++") and current is not None:
            current["added"].append(line[1:])
        elif line.startswith("-") and not line.startswith("---") and current is not None:
            current["removed"].append(line[1:])

    if current:
        file_diffs.append(current)

    return file_diffs


class DiffAnalyzer:
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def analyze_commit(self, commit_sha: str = "HEAD", base_sha: str = "HEAD~1") -> DiffResult:
        """Analyze changes between two commits."""
        if not GIT_AVAILABLE:
            return DiffResult(summary="git not available")

        try:
            repo = git.Repo(self.repo_path)
            commit = repo.commit(commit_sha)
            base = repo.commit(base_sha)
            diff_text = repo.git.diff(base_sha, commit_sha)
            msg = commit.message.strip()
            return self._analyze_diff_text(diff_text, commit_message=msg)
        except Exception as e:
            return DiffResult(summary=f"Error analyzing commit: {e}")

    def analyze_working_tree(self) -> DiffResult:
        """Analyze uncommitted changes (staged + unstaged)."""
        if not GIT_AVAILABLE:
            return DiffResult(summary="git not available")

        try:
            repo = git.Repo(self.repo_path)
            diff_text = repo.git.diff("HEAD")
            staged = repo.git.diff("--cached")
            return self._analyze_diff_text(diff_text + "\n" + staged)
        except Exception as e:
            return DiffResult(summary=f"Error: {e}")

    def analyze_diff_string(self, diff_text: str) -> DiffResult:
        """Analyze a raw diff string directly."""
        return self._analyze_diff_text(diff_text)

    def _analyze_diff_text(self, diff_text: str, commit_message: str = "") -> DiffResult:
        result = DiffResult(raw_diff=diff_text, commit_message=commit_message)
        file_diffs = _parse_unified_diff(diff_text)

        for fd in file_diffs:
            filepath = fd.get("filepath", "")
            if not filepath or not filepath.endswith(".py"):
                continue

            result.changed_files.append(filepath)
            result.added_lines.extend(fd["added"])
            result.removed_lines.extend(fd["removed"])

            # Try to get old and new file content for function extraction
            old_funcs, new_funcs = {}, {}
            try:
                if GIT_AVAILABLE:
                    repo = git.Repo(self.repo_path)
                    try:
                        old_content = repo.git.show(f"HEAD:{filepath}")
                        old_funcs = _extract_functions_from_source(old_content, filepath)
                    except Exception:
                        pass
                    full_path = self.repo_path / filepath
                    if full_path.exists():
                        new_funcs = _extract_functions_from_source(full_path.read_text(), filepath)
            except Exception:
                pass

            # Detect changed functions by looking at added/removed lines
            # Find function names mentioned in the diff
            func_pattern = re.compile(r"^(?:async\s+)?def\s+(\w+)\s*\(", re.MULTILINE)
            class_pattern = re.compile(r"^class\s+(\w+)\s*[:(]", re.MULTILINE)

            changed_names = set()
            for line in fd["added"] + fd["removed"]:
                for m in func_pattern.finditer(line):
                    changed_names.add(m.group(1))
                for m in class_pattern.finditer(line):
                    changed_names.add(m.group(1))

            # Also infer from context: if a function body has changed lines
            for name in changed_names:
                change_type = "modified"
                if name in new_funcs and name not in old_funcs:
                    change_type = "added"
                elif name not in new_funcs and name in old_funcs:
                    change_type = "deleted"

                result.changed_functions.append(ChangedFunction(
                    name=name,
                    filepath=filepath,
                    change_type=change_type,
                    old_code=old_funcs.get(name, ""),
                    new_code=new_funcs.get(name, ""),
                ))

        # Build summary
        n_files = len(result.changed_files)
        n_funcs = len(result.changed_functions)
        n_added = len(result.added_lines)
        n_removed = len(result.removed_lines)
        result.summary = (
            f"{n_files} file(s) changed, {n_funcs} function(s) affected, "
            f"+{n_added} lines / -{n_removed} lines"
        )

        return result
