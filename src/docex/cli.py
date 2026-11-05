"""`docex` command-line interface."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import Progress
from rich.table import Table

from docex.config import Settings
from docex.datasets import cord
from docex.evaluation.metrics import EvalResult, build_records, evaluate
from docex.evaluation.report import METRIC_ROWS, pct, write_report
from docex.pipeline import RunSummary, run_pipeline
from docex.providers.registry import get_provider
from docex.review_logic import export_labels
from docex.storage import Store
from docex.synthetic.generator import generate_dataset

REVIEW_APP = Path(__file__).parent / "review_app.py"

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Extract, validate, score, route and evaluate documents (offline mock provider).",
)
console = Console()

SIMULATED_NOTICE = "Results come from a simulated extractor (mock provider)."


@app.command()
def generate(
    n: int = typer.Option(100, help="Number of invoices to create."),
    seed: int | None = typer.Option(None, help="Random seed (default: DOCEX_SEED or 42)."),
    faulty_rate: float = typer.Option(0.15, help="Share of invoices with an injected fault."),
    scan_rate: float = typer.Option(0.3, help="Share of invoices degraded to look scanned."),
) -> None:
    """Create synthetic Indonesian invoice PDFs with ground truth."""
    settings = Settings()
    seed = settings.seed if seed is None else seed
    metas = create_invoices(settings, n, seed, faulty_rate, scan_rate)
    faulty = sum(1 for m in metas if m.injected_faults)
    scanned = sum(1 for m in metas if m.quality != "clean")
    console.print(
        f"Generated {len(metas)} invoices ({faulty} with faults, {scanned} scanned) "
        f"in {settings.data_dir / 'documents' / 'synthetic'}"
    )


def print_summary(summary: RunSummary) -> None:
    table = Table(title=f"Run {summary.run_id}")
    for col in ("documents", "auto-approved", "needs review", "extraction failed"):
        table.add_column(col, justify="right")
    table.add_row(
        str(summary.n_docs), str(summary.n_auto), str(summary.n_review), str(summary.n_failed)
    )
    console.print(table)
    if summary.simulated:
        console.print(f"[yellow]{SIMULATED_NOTICE}[/yellow]")
    console.print(f"run_id: {summary.run_id}")


def execute_run(settings: Settings, source: str = "all", limit: int | None = None) -> RunSummary:
    with Store(settings.resolved_db_path) as store:
        docs = store.list_documents(None if source == "all" else source, limit)
        if not docs:
            console.print("No documents found. Run `docex generate` first.")
            raise typer.Exit(1)
        try:
            provider = get_provider(settings.provider, settings)
        except ValueError as exc:
            console.print(str(exc))
            raise typer.Exit(2) from exc
        with Progress(console=console, transient=True) as progress:
            task = progress.add_task("Processing documents", total=len(docs))
            summary = run_pipeline(
                store, provider, docs, settings,
                on_progress=lambda done, total: progress.update(task, completed=done),
            )  # fmt: skip
    return summary


@app.command()
def run(
    provider: str | None = typer.Option(None, help="Provider name (default: DOCEX_PROVIDER)."),
    source: str = typer.Option("all", help="synthetic, cord or all."),
    limit: int | None = typer.Option(None, help="Process at most N documents."),
) -> None:
    """Extract, validate, score and route every registered document."""
    settings = Settings()
    if provider:
        settings = settings.model_copy(update={"provider": provider})
    print_summary(execute_run(settings, source, limit))


def create_invoices(settings: Settings, n: int, seed: int, faulty_rate: float, scan_rate: float):
    with console.status(f"Rendering {n} invoices..."):
        metas = generate_dataset(n, seed, faulty_rate, scan_rate, settings.data_dir)
    with Store(settings.resolved_db_path) as store:
        store.upsert_documents(metas)
    return metas


def evaluate_run(settings: Settings, run_id: str | None) -> tuple[EvalResult, Path]:
    with Store(settings.resolved_db_path) as store:
        run_id = run_id or store.latest_run_id()
        if run_id is None:
            console.print("No runs found. Run `docex run` first.")
            raise typer.Exit(1)
        config = store.get_run_config(run_id)
        if config is None:
            console.print(f"Run '{run_id}' not found. Known runs: see `docex run` output.")
            raise typer.Exit(1)
        records = build_records(store, run_id, settings.data_dir)
        simulated = store.run_simulated(run_id)
    result = evaluate(records, run_id, simulated)
    threshold = config.get("review_threshold", settings.review_threshold)
    path = write_report(result, settings.reports_dir / run_id, threshold)
    return result, path


def print_headline(result: EvalResult, path: Path) -> None:
    table = Table(title=f"Evaluation of {result.run_id}")
    table.add_column("metric")
    table.add_column("value", justify="right")
    for label, key, _ in METRIC_ROWS:
        value = getattr(result, key)
        table.add_row(label, str(value) if key == "n_docs" else pct(value))
    console.print(table)
    if result.simulated:
        console.print(f"[yellow]{SIMULATED_NOTICE}[/yellow]")
    console.print(f"Report: {path}")


@app.command("fetch-cord")
def fetch_cord(n: int = typer.Option(50, help="Number of CORD receipts to register.")) -> None:
    """Download real Indonesian receipts (CORD v2 test split) and register them."""
    settings = Settings()
    try:
        with console.status("Downloading CORD v2 test split..."):
            parquet = cord.download_cord_test_split()
            rows = cord.load_cord_rows(parquet, n)
    except Exception as exc:  # noqa: BLE001 - any network/HF error gets the same advice
        console.print(
            f"Could not download CORD ({exc}). Check your internet connection and retry; "
            "the synthetic dataset still works.",
            markup=False,
            soft_wrap=True,
        )
        raise typer.Exit(1) from exc
    metas = cord.materialize_cord(rows, settings.data_dir)
    with Store(settings.resolved_db_path) as store:
        store.upsert_documents(metas)
    console.print(f"Registered {len(metas)} receipts in {settings.data_dir / 'documents' / 'cord'}")
    console.print(cord.CORD_ATTRIBUTION, markup=False, soft_wrap=True)


@app.command("eval")
def eval_command(
    run: str | None = typer.Option(None, "--run", help="Run id (default: the latest run)."),
) -> None:
    """Score a run against ground truth and write a Markdown report with charts."""
    result, path = evaluate_run(Settings(), run)
    print_headline(result, path)


@app.command()
def demo(n: int = typer.Option(40, help="Invoices to generate if none exist yet.")) -> None:
    """Generate (if needed), run and evaluate in one go."""
    settings = Settings()
    with Store(settings.resolved_db_path) as store:
        has_docs = bool(store.list_documents(source="synthetic", limit=1))
    if not has_docs:
        metas = create_invoices(settings, n, settings.seed, 0.15, 0.3)
        console.print(f"Generated {len(metas)} synthetic invoices.")
    summary = execute_run(settings)
    print_summary(summary)
    result, path = evaluate_run(settings, summary.run_id)
    print_headline(result, path)


@app.command()
def review() -> None:
    """Open the Streamlit review queue in your browser."""
    command = [sys.executable, "-m", "streamlit", "run", str(REVIEW_APP)]
    raise typer.Exit(subprocess.run(command, check=False).returncode)


@app.command("export-labels")
def export_labels_command(
    run: str | None = typer.Option(None, "--run", help="Run id (default: the latest run)."),
) -> None:
    """Write reviewer corrections as new ground-truth labels under data/labels/."""
    settings = Settings()
    with Store(settings.resolved_db_path) as store:
        run_id = run or store.latest_run_id()
        if run_id is None:
            console.print("No runs found. Run `docex run` first.")
            raise typer.Exit(1)
        paths = export_labels(store, run_id, settings.data_dir)
    console.print(f"Wrote {len(paths)} labels to {settings.data_dir / 'labels'}")


if __name__ == "__main__":  # pragma: no cover
    app()
