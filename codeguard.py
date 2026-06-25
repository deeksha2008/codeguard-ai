#!/usr/bin/env python3
"""
CodeGuard AI - CLI
Usage:
  python codeguard.py index  --repo ./demo_repo
  python codeguard.py analyze --repo ./demo_repo --diff demo_repo/sample.diff
  python codeguard.py run    --repo ./demo_repo --diff demo_repo/sample.diff --execute
  python codeguard.py tdd    --repo ./demo_repo --feature "add bulk order discount"
"""
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich import print as rprint

console = Console()


def _get_indexer(repo):
    sys.path.insert(0, str(Path(__file__).parent))
    from src.indexer.indexer import CodebaseIndexer
    return CodebaseIndexer(repo)


def _get_diff_analyzer(repo):
    from src.analyzer.diff_analyzer import DiffAnalyzer
    return DiffAnalyzer(repo)


def _get_impact_analyzer(repo):
    from src.analyzer.impact_analyzer import ImpactAnalyzer
    return ImpactAnalyzer(repo)


def _get_generator():
    from src.generator.test_generator import TestGenerator
    return TestGenerator()


def _get_reporter(repo):
    from src.reporter.reporter import Reporter
    return Reporter(repo)


@click.group()
def cli():
    """CodeGuard AI - LLM-powered regression test generator."""
    pass


@cli.command()
@click.option("--repo", required=True, help="Path to repository")
@click.option("--force", is_flag=True, help="Force re-index")
def index(repo, force):
    """Index a codebase into the vector database."""
    console.print(Panel("[bold cyan]CodeGuard AI — Indexing Codebase[/bold cyan]"))

    indexer = _get_indexer(repo)
    with console.status("[green]Indexing files..."):
        count = indexer.index(force=force)

    console.print(f"[green]✓[/green] Indexed [bold]{count}[/bold] code chunks from [bold]{repo}[/bold]")
    console.print(f"[dim]Total vectors in DB: {indexer.count()}[/dim]")


@cli.command()
@click.option("--repo", required=True)
@click.option("--diff", default=None, help="Path to .diff file (or use HEAD commit)")
@click.option("--commit", default=None, help="Commit SHA to analyze")
def analyze(repo, diff, commit):
    """Analyze a diff and show what changed and what tests are at risk."""
    console.print(Panel("[bold cyan]CodeGuard AI — Diff Analysis[/bold cyan]"))

    analyzer = _get_diff_analyzer(repo)
    impact = _get_impact_analyzer(repo)

    if diff:
        diff_text = Path(diff).read_text()
        result = analyzer.analyze_diff_string(diff_text)
    elif commit:
        result = analyzer.analyze_commit(commit)
    else:
        result = analyzer.analyze_working_tree()

    console.print(f"\n[bold]Diff Summary:[/bold] {result.summary}")
    if result.commit_message:
        console.print(f"[bold]Commit:[/bold] {result.commit_message}")

    # Changed files
    if result.changed_files:
        t = Table(title="Changed Files", show_header=True)
        t.add_column("File", style="cyan")
        for f in result.changed_files:
            t.add_row(f)
        console.print(t)

    # Changed functions
    if result.changed_functions:
        t = Table(title="Changed Functions", show_header=True)
        t.add_column("Function", style="green")
        t.add_column("File")
        t.add_column("Change")
        for cf in result.changed_functions:
            color = {"added": "green", "modified": "yellow", "deleted": "red"}.get(cf.change_type, "white")
            t.add_row(cf.name, cf.filepath, f"[{color}]{cf.change_type}[/{color}]")
        console.print(t)

    # Impact
    affected = impact.find_affected_tests(result.changed_functions, result.changed_files)
    if affected:
        t = Table(title="Tests At Risk", show_header=True)
        t.add_column("Test File", style="yellow")
        t.add_column("Confidence")
        t.add_column("Reasons")
        for a in affected:
            conf = f"{a['confidence']*100:.0f}%"
            t.add_row(a["test_file"], conf, " | ".join(a["reasons"]))
        console.print(t)
    else:
        console.print("[green]No existing tests appear to be at risk.[/green]")


@cli.command()
@click.option("--repo", required=True)
@click.option("--diff", default=None)
@click.option("--commit", default=None)
@click.option("--execute", is_flag=True, help="Run the generated tests")
@click.option("--output", default=None, help="Directory to save test files")
@click.option("--json-report", default=None, help="Save JSON report to path")
def run(repo, diff, commit, execute, output, json_report):
    """Generate tests and optionally run them."""
    
    if False:
        console.print("[red]Error: GEMINI_API_KEY not set. Add it to .env or environment.[/red]")
        sys.exit(1)

    console.print(Panel("[bold cyan]CodeGuard AI — Generating Tests[/bold cyan]"))

    indexer = _get_indexer(repo)
    if indexer.count() == 0:
        console.print("[yellow]Warning: codebase not indexed. Running index first...[/yellow]")
        with console.status("Indexing..."):
            indexer.index()

    analyzer = _get_diff_analyzer(repo)
    impact_analyzer = _get_impact_analyzer(repo)
    generator = _get_generator()
    reporter = _get_reporter(repo)

    # Analyze diff
    if diff:
        diff_text = Path(diff).read_text()
        diff_result = analyzer.analyze_diff_string(diff_text)
    elif commit:
        diff_result = analyzer.analyze_commit(commit)
    else:
        diff_result = analyzer.analyze_working_tree()

    console.print(f"[dim]{diff_result.summary}[/dim]")

    if not diff_result.changed_functions:
        console.print("[yellow]No Python function changes detected.[/yellow]")
        return

    # Impact analysis
    affected = impact_analyzer.find_affected_tests(
        diff_result.changed_functions, diff_result.changed_files
    )

    # Generate tests
    generated = []
    run_results = []

    for cf in diff_result.changed_functions:
        if cf.change_type == "deleted":
            continue

        with console.status(f"[green]Generating tests for [bold]{cf.name}[/bold]..."):
            rag_hits = indexer.query(f"{cf.name} {cf.new_code or cf.old_code}", k=6)
            existing_style = None
            if affected:
                try:
                    tp = Path(repo) / affected[0]["test_file"]
                    if tp.exists():
                        existing_style = tp.read_text()[:1500]
                except Exception:
                    pass
            gen = generator.generate_for_function(cf, rag_hits, existing_style)
            generated.append(gen)

        console.print(f"[green]✓[/green] [bold]{gen.function_name}[/bold] → {len(gen.test_functions)} test(s)")

        # Show generated code
        console.print(Syntax(gen.test_code, "python", theme="monokai", line_numbers=True))

        # Edge cases
        if gen.edge_cases:
            console.print("[bold]Edge cases covered:[/bold]")
            for ec in gen.edge_cases:
                console.print(f"  • {ec}")

        # Run if requested
        if execute:
            from src.reporter.reporter import run_tests_in_temp
            with console.status("Running tests..."):
                rr = run_tests_in_temp(gen.test_code, repo)
            run_results.append(rr)
            status = "[green]PASSED[/green]" if rr.failed == 0 else "[red]FAILED[/red]"
            console.print(f"Result: {status} ({rr.passed} passed, {rr.failed} failed in {rr.duration:.2f}s)")

    # Build and save report
    report = reporter.build_report(diff_result, generated, affected, run_results or None)

    if output:
        reporter.save_tests(report, output)
        console.print(f"[green]Tests saved to {output}[/green]")

    if json_report:
        reporter.save_json(report, json_report)
        console.print(f"[green]JSON report saved to {json_report}[/green]")

    # Final summary
    total_tests = sum(len(g.test_functions) for g in generated)
    console.print(Panel(
        f"[bold green]Done![/bold green]\n"
        f"Functions analyzed: {len(generated)}\n"
        f"Tests generated: {total_tests}\n"
        f"Existing tests at risk: {len(affected)}\n"
        + (f"Tests passed: {sum(r.passed for r in run_results)}\n"
           f"Tests failed: {sum(r.failed for r in run_results)}" if run_results else ""),
        title="Summary"
    ))


@cli.command()
@click.option("--repo", required=True)
@click.option("--feature", required=True, help="Feature description for TDD")
@click.option("--output", default=None)
def tdd(repo, feature, output):
    """TDD mode: generate failing tests before writing the feature."""
    
    if False:
        console.print("[red]GEMINI_API_KEY not set[/red]")
        sys.exit(1)

    console.print(Panel(f"[bold cyan]TDD Mode[/bold cyan]\nFeature: {feature}"))

    indexer = _get_indexer(repo)
    if indexer.count() == 0:
        with console.status("Indexing codebase..."):
            indexer.index()

    generator = _get_generator()
    with console.status("Generating TDD stubs..."):
        stub = generator.generate_tdd_stub(feature, indexer)

    console.print(Syntax(stub, "python", theme="monokai", line_numbers=True))

    if output:
        Path(output).write_text(stub)
        console.print(f"[green]Saved to {output}[/green]")


if __name__ == "__main__":
    cli()
