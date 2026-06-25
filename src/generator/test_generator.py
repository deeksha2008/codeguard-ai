import json
import re
from dataclasses import dataclass, field
from typing import Optional
import ollama

@dataclass
class GeneratedTest:
    function_name: str
    filepath: str
    test_code: str
    test_functions: list = field(default_factory=list)
    edge_cases: list = field(default_factory=list)
    explanation: str = ""
    change_type: str = "modified"

SYSTEM_PROMPT = """You are CodeGuard AI, an expert Python test engineer.
Write production-quality pytest test cases for changed code.
Rules:
1. Write pytest-style tests (def test_...).
2. Cover: happy path, edge cases, error conditions, boundary values.
3. Use pytest.raises for exception tests.
4. Use descriptive names: test_<function>_<scenario>.
Only output Python code, no explanations outside the code."""

def _extract_test_functions(code):
    return re.findall(r"^def (test_\w+)\s*\(", code, re.MULTILINE)

def _clean_code(raw):
    raw = re.sub(r"```python\n?", "", raw)
    raw = re.sub(r"```\n?", "", raw)
    return raw.strip()

class TestGenerator:
    def __init__(self):
        self.model = "llama3.2"

    def _call(self, prompt):
        response = ollama.chat(model=self.model, messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ])
        return response["message"]["content"]

    def generate_for_function(self, cf, rag_context, existing_tests=None):
        context = "\n\n".join(h["document"] for h in rag_context[:4])
        prompt = f"Function: {cf.name}\nFile: {cf.filepath}\nChange: {cf.change_type}\n"
        if cf.new_code: prompt += f"\n```python\n{cf.new_code}\n```\n"
        if context: prompt += f"\nContext:\n```python\n{context[:2000]}\n```\n"
        prompt += f"\nWrite comprehensive pytest tests for `{cf.name}`."
        raw = self._call(prompt)
        test_code = _clean_code(raw)
        return GeneratedTest(
            function_name=cf.name, filepath=cf.filepath, test_code=test_code,
            test_functions=_extract_test_functions(test_code),
            edge_cases=[], explanation="", change_type=cf.change_type)

    def generate_tdd_stub(self, feature, indexer):
        hits = indexer.query(feature, k=4)
        ctx = "\n\n".join(h["document"] for h in hits[:3])
        return _clean_code(self._call(f"Feature: {feature}\nContext:\n{ctx[:2000]}\nWrite failing TDD tests."))
