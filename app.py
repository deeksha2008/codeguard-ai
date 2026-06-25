"""
CodeGuard AI - Streamlit Dashboard
Run with: streamlit run app.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

st.set_page_config(
    page_title="CodeGuard AI",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styles ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.metric-card {
    background: #1e1e2e;
    border: 1px solid #313244;
    border-radius: 10px;
    padding: 1rem 1.25rem;
    text-align: center;
}
.metric-val { font-size: 2rem; font-weight: 700; margin: 0; }
.metric-lbl { font-size: 0.8rem; color: #a6adc8; margin: 0; }
.green { color: #a6e3a1; }
.yellow { color: #f9e2af; }
.red { color: #f38ba8; }
.blue { color: #89b4fa; }
.tag {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    margin: 2px;
}
.tag-added { background: #1e3a2f; color: #a6e3a1; }
.tag-modified { background: #3a2e1e; color: #f9e2af; }
.tag-deleted { background: #3a1e1e; color: #f38ba8; }
.tag-risk { background: #2e1e3a; color: #cba6f7; }
</style>
""", unsafe_allow_html=True)


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🛡️ CodeGuard AI")
    st.caption("LLM-powered Regression Test Generator")
    st.divider()

    api_key = st.text_input(
        "Anthropic API Key",
        type="password",
        value=os.getenv("GROQ_API_KEY", ""),
        help="Get yours at console.anthropic.com",
    )
    if api_key:
        os.environ["GROQ_API_KEY"] = api_key

    st.divider()
    mode = st.radio("Mode", ["🔍 Analyze Diff", "🧪 Generate Tests", "🚀 TDD Mode"])
    st.divider()
    st.caption("Built for Flipkart Grid 8.0 · AI Engineering Track")


# ── Helper ────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_indexer(repo_path: str):
    from src.indexer.indexer import CodebaseIndexer
    return CodebaseIndexer(repo_path)


def index_repo(repo_path: str):
    idx = get_indexer(repo_path)
    with st.spinner("Indexing codebase into vector DB..."):
        count = idx.index()
    return idx, count


# ── Main ──────────────────────────────────────────────────────────────────────
DEMO_REPO = str(Path(__file__).parent / "demo_repo")
SAMPLE_DIFF = (Path(__file__).parent / "demo_repo" / "sample.diff").read_text()

st.title("🛡️ CodeGuard AI")
st.subheader("Regression Test Generator · Flipkart Grid 8.0")

# ── Mode: Analyze Diff ────────────────────────────────────────────────────────
if "Analyze" in mode:
    st.markdown("### Step 1 — Provide Your Diff")

    col1, col2 = st.columns([3, 1])
    with col1:
        diff_input = st.text_area(
            "Paste a unified diff here",
            value=SAMPLE_DIFF,
            height=300,
            help="Paste output of `git diff HEAD~1`",
        )
    with col2:
        st.markdown("**Or upload:**")
        uploaded = st.file_uploader("Upload .diff file", type=["diff", "patch", "txt"])
        if uploaded:
            diff_input = uploaded.read().decode()

    repo_path = st.text_input("Repository path", value=DEMO_REPO)

    if st.button("🔍 Analyze Changes", type="primary"):
        from src.analyzer.diff_analyzer import DiffAnalyzer
        from src.analyzer.impact_analyzer import ImpactAnalyzer

        analyzer = DiffAnalyzer(repo_path)
        impact_analyzer = ImpactAnalyzer(repo_path)

        result = analyzer.analyze_diff_string(diff_input)
        affected = impact_analyzer.find_affected_tests(
            result.changed_functions, result.changed_files
        )

        # Metrics row
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Files Changed", len(result.changed_files))
        c2.metric("Functions Affected", len(result.changed_functions))
        c3.metric("Lines Added", len(result.added_lines))
        c4.metric("Tests At Risk", len(affected))

        if result.changed_functions:
            st.markdown("#### Changed Functions")
            for cf in result.changed_functions:
                badge = f"<span class='tag tag-{cf.change_type}'>{cf.change_type.upper()}</span>"
                st.markdown(f"{badge} **`{cf.name}`** in `{cf.filepath}`", unsafe_allow_html=True)

        if affected:
            st.markdown("#### Tests At Risk")
            for a in affected:
                with st.expander(f"⚠️ `{a['test_file']}` ({a['confidence']*100:.0f}% confidence)"):
                    for r in a["reasons"]:
                        st.markdown(f"- {r}")
                    if a["test_functions"]:
                        st.markdown("**Test functions in this file:**")
                        for tf in a["test_functions"]:
                            st.code(tf, language=None)


# ── Mode: Generate Tests ──────────────────────────────────────────────────────
elif "Generate" in mode:
    st.markdown("### Generate Regression Tests")

    if False:
        st.warning("⚠️ Enter your Anthropic API key in the sidebar to generate tests.")
        st.stop()

    col1, col2 = st.columns([2, 1])
    with col1:
        diff_input = st.text_area("Paste diff", value=SAMPLE_DIFF, height=250)
        repo_path = st.text_input("Repository path", value=DEMO_REPO)
    with col2:
        st.markdown("**Options**")
        run_tests = st.checkbox("Run generated tests", value=False)
        save_tests = st.checkbox("Save test files", value=True)
        top_k = st.slider("RAG context chunks", 3, 10, 6)

    if st.button("🧪 Generate Tests", type="primary"):
        from src.analyzer.diff_analyzer import DiffAnalyzer
        from src.analyzer.impact_analyzer import ImpactAnalyzer
        from src.generator.test_generator import TestGenerator

        # Index
        idx, count = index_repo(repo_path)
        st.info(f"Vector DB: {count} chunks indexed")

        analyzer = DiffAnalyzer(repo_path)
        impact_analyzer = ImpactAnalyzer(repo_path)
        generator = TestGenerator()

        diff_result = analyzer.analyze_diff_string(diff_input)
        affected = impact_analyzer.find_affected_tests(
            diff_result.changed_functions, diff_result.changed_files
        )

        if not diff_result.changed_functions:
            st.warning("No Python function changes detected in this diff.")
            st.stop()

        st.success(f"Found {len(diff_result.changed_functions)} changed function(s). Generating tests...")

        results_container = st.container()

        total_tests = 0
        for cf in diff_result.changed_functions:
            if cf.change_type == "deleted":
                continue

            with st.spinner(f"Generating tests for `{cf.name}`..."):
                rag_hits = idx.query(f"{cf.name} {cf.new_code or cf.old_code}", k=top_k)
                existing_style = None
                if affected:
                    try:
                        tp = Path(repo_path) / affected[0]["test_file"]
                        if tp.exists():
                            existing_style = tp.read_text()[:1500]
                    except Exception:
                        pass
                gen = generator.generate_for_function(cf, rag_hits, existing_style)

            with results_container:
                with st.expander(
                    f"✅ `{gen.function_name}` → {len(gen.test_functions)} tests",
                    expanded=True,
                ):
                    tabs = st.tabs(["Test Code", "Edge Cases", "Explanation", "RAG Context"])

                    with tabs[0]:
                        st.code(gen.test_code, language="python")
                        if save_tests:
                            st.download_button(
                                f"⬇️ Download test_{gen.function_name}.py",
                                gen.test_code,
                                file_name=f"test_codeguard_{gen.function_name}.py",
                                mime="text/plain",
                            )

                    with tabs[1]:
                        if gen.edge_cases:
                            for ec in gen.edge_cases:
                                st.markdown(f"- {ec}")
                        else:
                            st.info("No edge cases extracted.")

                    with tabs[2]:
                        st.markdown(gen.explanation or "_No explanation generated._")

                    with tabs[3]:
                        for i, hit in enumerate(rag_hits[:3]):
                            st.caption(f"Context chunk {i+1} (score: {hit['score']:.3f})")
                            st.code(hit["document"][:400], language="python")

                    if run_tests:
                        from src.reporter.reporter import run_tests_in_temp
                        with st.spinner("Running tests..."):
                            rr = run_tests_in_temp(gen.test_code, repo_path)
                        if rr.failed == 0 and rr.passed > 0:
                            st.success(f"✅ {rr.passed} passed in {rr.duration:.2f}s")
                        elif rr.passed == 0 and rr.failed == 0:
                            st.warning("⚠️ No tests collected (check imports)")
                        else:
                            st.error(f"❌ {rr.failed} failed, {rr.passed} passed")
                        with st.expander("pytest output"):
                            st.code(rr.output)

            total_tests += len(gen.test_functions)

        st.balloons()
        st.success(f"🎉 Generated {total_tests} total test cases!")

        if affected:
            st.markdown("#### ⚠️ Also review these existing tests:")
            for a in affected:
                st.markdown(f"- `{a['test_file']}` — {', '.join(a['reasons'])}")


# ── Mode: TDD ─────────────────────────────────────────────────────────────────
elif "TDD" in mode:
    st.markdown("### TDD Mode — Write Tests Before the Feature")
    st.caption("Describe a feature you plan to implement. CodeGuard will generate failing tests that define its contract.")

    if False:
        st.warning("⚠️ Enter your Anthropic API key in the sidebar.")
        st.stop()

    repo_path = st.text_input("Repository path", value=DEMO_REPO)
    feature = st.text_area(
        "Feature description",
        placeholder="e.g. Add a bulk_order() method that creates multiple orders atomically and rolls back all if any item is out of stock.",
        height=120,
    )

    if st.button("🚀 Generate TDD Tests", type="primary") and feature:
        from src.generator.test_generator import TestGenerator

        idx, count = index_repo(repo_path)
        generator = TestGenerator()

        with st.spinner("Generating TDD stubs..."):
            stub = generator.generate_tdd_stub(feature, idx)

        st.markdown("#### Generated failing tests:")
        st.code(stub, language="python")
        st.download_button(
            "⬇️ Download TDD stub",
            stub,
            file_name="test_tdd_stub.py",
            mime="text/plain",
        )
        st.info("These tests should **fail now** and pass once you implement the feature.")
