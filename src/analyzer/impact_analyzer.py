"""
Impact Analyzer
---------------
Finds existing test files that are likely to break given the changed functions.
Uses both static analysis (import tracing) and semantic search.
"""
import ast
import re
from pathlib import Path


def _get_imports(source: str) -> set[str]:
    """Extract all imported names from a Python source file."""
    imports = set()
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
                    if alias.asname:
                        imports.add(alias.asname)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])
                for alias in node.names:
                    imports.add(alias.name)
                    if alias.asname:
                        imports.add(alias.asname)
    except SyntaxError:
        pass
    return imports


def _get_called_names(source: str) -> set[str]:
    """Extract all function/method call names from source."""
    names = set()
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    names.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    names.add(node.func.attr)
    except SyntaxError:
        # Regex fallback
        for m in re.finditer(r"(\w+)\s*\(", source):
            names.add(m.group(1))
    return names


class ImpactAnalyzer:
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def find_affected_tests(self, changed_functions: list, changed_files: list[str]) -> list[dict]:
        """
        Returns list of {test_file, test_functions, reason, confidence} for tests
        likely affected by the given changes.
        """
        # Find all test files
        test_files = list(self.repo_path.rglob("test_*.py")) + \
                     list(self.repo_path.rglob("*_test.py")) + \
                     list(self.repo_path.rglob("tests/**/*.py"))
        test_files = list(set(test_files))

        changed_module_names = set()
        for cf in changed_files:
            p = Path(cf)
            changed_module_names.add(p.stem)
            changed_module_names.add(p.name)

        changed_func_names = {f.name for f in changed_functions}

        affected = []
        for test_file in test_files:
            try:
                source = test_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            reasons = []
            confidence = 0.0

            # Check 1: imports of changed modules
            imports = _get_imports(source)
            matched_imports = imports & changed_module_names
            if matched_imports:
                reasons.append(f"imports changed module(s): {', '.join(matched_imports)}")
                confidence += 0.5

            # Check 2: calls to changed functions
            calls = _get_called_names(source)
            matched_calls = calls & changed_func_names
            if matched_calls:
                reasons.append(f"calls changed function(s): {', '.join(matched_calls)}")
                confidence += 0.6

            # Check 3: string references (e.g., mock patches)
            for fn in changed_func_names:
                if fn in source:
                    if fn not in matched_calls:  # avoid duplicate
                        reasons.append(f"references '{fn}' by name (possible mock/patch)")
                        confidence += 0.2
                    break

            if reasons:
                # Find test functions in this file
                test_funcs = re.findall(r"def (test_\w+)\s*\(", source)
                relative = str(test_file.relative_to(self.repo_path))
                affected.append({
                    "test_file": relative,
                    "test_functions": test_funcs,
                    "reasons": reasons,
                    "confidence": min(confidence, 1.0),
                })

        # Sort by confidence descending
        affected.sort(key=lambda x: x["confidence"], reverse=True)
        return affected
