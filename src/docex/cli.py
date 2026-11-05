"""`docex` command-line interface."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.progress import Progress
from rich.table import Table

from docex.config import Settings
from docex.pipeline import RunSummary, run_pipeline
from docex.providers.registry import get_provider
from docex.storage import Store
from docex.synthetic.generator import generate_dataset

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
    with console.status(f"Rendering {n} invoices..."):
        metas = generate_dataset(n, seed, faulty_rate, scan_rate, settings.data_dir)
    with Store(settings.resolved_db_path) as store:
        store.upsert_documents(metas)
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


if __name__ == "__main__":  # pragma: no cover
    app()
