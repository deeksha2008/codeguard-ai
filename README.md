# 🛡️ CodeGuard AI

**AI-powered Regression Test Generator** — Flipkart Grid 8.0 · AI Engineering Track

> Automatically generate pytest test cases for every code change using LLM + RAG.
> Prevent regressions before they reach production.

---

## 🧠 How It Works

```
git diff → AST Diff Analyzer → RAG Retriever → Claude (LLM) → Test Cases
                                     ↑
                              ChromaDB (codebase embeddings)
```

1. **Codebase Indexer** — Parses your entire repo using AST, chunks it by function/class, and stores embeddings in ChromaDB
2. **Diff Analyzer** — Parses `git diff` to extract exactly which functions changed and how
3. **RAG Retriever** — Semantically searches the vector DB to pull relevant context for the LLM
4. **Test Generator** — Sends context + diff to Claude API to generate pytest test cases with edge cases
5. **Impact Analyzer** — Statically detects which *existing* tests may break from the change
6. **Reporter** — Runs generated tests, outputs a report, posts PR comments via GitHub Actions

---

## 🚀 Quick Start

```bash
# 1. Clone and install
git clone https://github.com/yourname/codeguard-ai
cd codeguard-ai
pip install -r requirements.txt

# 2. Set API key
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# 3. Index your codebase
python codeguard.py index --repo ./demo_repo

# 4. Analyze a diff
python codeguard.py analyze --repo ./demo_repo --diff demo_repo/sample.diff

# 5. Generate + run tests
python codeguard.py run --repo ./demo_repo --diff demo_repo/sample.diff --execute

# 6. TDD mode
python codeguard.py tdd --repo ./demo_repo --feature "add bulk order discount"

# 7. Launch Web UI
streamlit run app.py
```

---

## 📁 Project Structure

```
codeguard/
├── src/
│   ├── indexer/        # AST chunking + ChromaDB embeddings
│   ├── analyzer/       # Git diff parser + impact analysis
│   ├── generator/      # Claude-powered test generation
│   └── reporter/       # pytest runner + JSON reports
├── demo_repo/          # Sample codebase to test on
│   ├── src/            # E-commerce order service
│   └── tests/          # Existing test suite
├── .github/workflows/  # GitHub Actions CI integration
├── codeguard.py        # CLI entrypoint
├── app.py              # Streamlit web dashboard
└── requirements.txt
```

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| LLM | Claude Sonnet (Anthropic API) |
| Vector DB | ChromaDB |
| Embeddings | Sentence Transformers (default) |
| Code Analysis | Python AST |
| Git Integration | GitPython |
| Test Framework | pytest |
| CLI | Click + Rich |
| Web UI | Streamlit |
| CI/CD | GitHub Actions |

---

## 💡 Key Features

- **AST-level chunking** — not naive line splits; understands function/class boundaries
- **Semantic RAG retrieval** — pulls the most relevant codebase context for each changed function
- **Impact analysis** — identifies which *existing* tests reference changed code (via import tracing + call graph)
- **Edge case generation** — LLM prompted to think adversarially (nulls, boundaries, race conditions)
- **TDD mode** — generates failing tests *before* you write the feature
- **Agentic loop** — generate → run → if fails → re-prompt (configurable)
- **CI integration** — drop-in GitHub Actions workflow with PR comments

---

## 📊 Evaluation Metrics (for competition submission)

- Regression catch rate vs. random baseline
- Test coverage delta (before/after)
- False positive rate on impact analysis
- Time to generate (target: < 10s per function)

---

## 👩‍💻 Author

Deeksha · MT2025038 · IIIT Bengaluru  
Built for Flipkart Grid 8.0 — AI Engineering Track
