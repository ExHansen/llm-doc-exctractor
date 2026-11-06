"""Write a Markdown report, a metrics.json and four PNG charts for one evaluated run."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from docex.evaluation.metrics import BREAKDOWN_METRICS, EvalResult  # noqa: E402

# Reference palette (dataviz skill), light surface. Slots 1-2 validated as a pair.
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
GRID = "#e4e3df"
SERIES = ("#2a78d6", "#eb6834")

SIMULATED_BANNER = (
    "> **Simulated extractor.** These numbers come from the offline mock provider, which "
    "returns ground truth with injected LLM/OCR-style errors. They measure the QC pipeline "
    "(validation, confidence, routing), not a real model."
)

METRIC_ROWS = (
    ("Documents", "n_docs", "Documents in the run."),
    ("Automation rate", "automation_rate", "Share of documents auto-approved."),
    ("Auto-approved accuracy", "auto_approved_accuracy",
     "Share of auto-approved documents whose critical fields are all correct."),
    ("Error catch rate", "error_catch_rate",
     "Share of documents with a wrong critical field that were sent to review "
     "(failed extractions excluded: they always go to review)."),
    ("Fault catch rate", "fault_catch_rate",
     "Share of documents with a printed fault (wrong total, bad NPWP...) sent to review."),
    ("Document accuracy", "doc_accuracy", "Share of documents with every critical field correct."),
    ("Line-item F1", "item_f1", "Line items extracted with every field correct."),
)  # fmt: skip


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _style(ax, title: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=TEXT, fontsize=12, pad=12)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT_2, labelsize=9)
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _figure(width: float = 7.5, height: float = 4.2):
    fig, ax = plt.subplots(figsize=(width, height), dpi=120)
    fig.patch.set_facecolor(SURFACE)
    return fig, ax


def _save(fig, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def chart_field_accuracy(result: EvalResult, path: Path) -> None:
    items = sorted(
        ((f, v) for f, v in result.field_accuracy.items() if v is not None), key=lambda x: x[1]
    )
    fig, ax = _figure(height=max(3.0, 0.32 * len(items) + 1.2))
    _style(ax, "Field accuracy")
    names = [f for f, _ in items]
    values = [v * 100 for _, v in items]
    ax.barh(names, values, color=SERIES[0], height=0.6, edgecolor=SURFACE, linewidth=2)
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, 100)
    ax.set_xlabel("% correct", color=TEXT_2, fontsize=9)
    if items:  # label only the weakest field
        ax.annotate(f"{values[0]:.1f}%", (values[0], 0), xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=9, color=TEXT)  # fmt: skip
    _save(fig, path)


def chart_by_quality(result: EvalResult, path: Path) -> None:
    groups = result.breakdown.get("quality", {})
    names = list(groups)
    series = (("Automation rate", "automation_rate"), ("Document accuracy", "doc_accuracy"))
    fig, ax = _figure()
    _style(ax, "Automation and accuracy by document quality")
    width = 0.38
    for k, (label, key) in enumerate(series):
        xs = [i + (k - 0.5) * width for i in range(len(names))]
        values = [(groups[g][key] or 0) * 100 for g in names]
        bars = ax.bar(xs, values, width=width, color=SERIES[k], label=label,
                      edgecolor=SURFACE, linewidth=2)  # fmt: skip
        ax.bar_label(bars, fmt="%.0f%%", fontsize=8, color=TEXT_2, padding=2)
    ax.set_xticks(range(len(names)), [f"{g}\n(n={groups[g]['n']})" for g in names])
    ax.set_ylim(0, 110)
    ax.set_ylabel("%", color=TEXT_2, fontsize=9)
    ax.grid(axis="x", visible=False)
    ax.legend(frameon=False, fontsize=9, loc="upper right", ncols=2, labelcolor=TEXT)
    _save(fig, path)


def chart_tradeoff(result: EvalResult, path: Path, threshold: float | None) -> None:
    rows = result.tradeoff
    xs = [r["threshold"] for r in rows]
    fig, ax = _figure()
    _style(ax, "Review threshold trade-off")
    series = (("Automation rate", "automation_rate"),
              ("Auto-approved accuracy", "auto_approved_accuracy"))  # fmt: skip
    for k, (label, key) in enumerate(series):
        points = [(x, r[key] * 100) for x, r in zip(xs, rows, strict=True) if r[key] is not None]
        if not points:
            continue
        px, py = zip(*points, strict=True)
        ax.plot(px, py, color=SERIES[k], linewidth=2, marker="o", markersize=4, label=label)
        ax.annotate(label, (px[-1], py[-1]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=8, color=TEXT_2)  # fmt: skip
    if threshold is not None:
        ax.axvline(threshold, color=TEXT_2, linewidth=1, linestyle="--")
        ax.annotate(f"current threshold {threshold:.2f}", (threshold, 4), xytext=(4, 0),
                    textcoords="offset points", fontsize=8, color=TEXT_2)  # fmt: skip
    ax.set_xlim(0, 1.18)
    ax.set_ylim(0, 105)
    ax.set_xlabel("document confidence threshold", color=TEXT_2, fontsize=9)
    ax.set_ylabel("%", color=TEXT_2, fontsize=9)
    ax.legend(frameon=False, fontsize=9, loc="lower left", labelcolor=TEXT)
    _save(fig, path)


def chart_calibration(result: EvalResult, path: Path) -> None:
    fig, ax = _figure(width=5.6, height=4.6)
    _style(ax, "Confidence calibration (critical fields)")
    ax.plot([0, 1], [0, 100], color=GRID, linewidth=1.5, linestyle="--")
    ax.annotate("perfect calibration", (0.62, 66), fontsize=8, color=TEXT_2, rotation=0)
    rows = [r for r in result.calibration if r["accuracy"] is not None]
    if rows:
        xs = [r["mean_confidence"] for r in rows]
        ys = [r["accuracy"] * 100 for r in rows]
        ax.plot(xs, ys, color=SERIES[0], linewidth=2, marker="o", markersize=6,
                markeredgecolor=SURFACE, markeredgewidth=2)  # fmt: skip
    ax.set_xlim(0, 1.02)
    ax.set_ylim(0, 105)
    ax.set_xlabel("mean field confidence", color=TEXT_2, fontsize=9)
    ax.set_ylabel("% correct", color=TEXT_2, fontsize=9)
    _save(fig, path)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def write_report(result: EvalResult, out_dir: Path, threshold: float | None = None) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(
        json.dumps(asdict(result), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    chart_field_accuracy(result, out_dir / "field_accuracy.png")
    chart_by_quality(result, out_dir / "accuracy_by_quality.png")
    chart_tradeoff(result, out_dir / "threshold_tradeoff.png", threshold)
    chart_calibration(result, out_dir / "calibration.png")

    md = [f"# Extraction QC report: run `{result.run_id}`", ""]
    if result.simulated:
        md += [SIMULATED_BANNER, ""]
    md += ["## Headline", ""]
    md.append(_table(
        ["Metric", "Value", "Meaning"],
        [[label, str(result.n_docs) if key == "n_docs" else pct(getattr(result, key)), meaning]
         for label, key, meaning in METRIC_ROWS],
    ))  # fmt: skip
    if threshold is not None:
        md += ["", f"Review threshold: **{threshold:.2f}** (document confidence)."]

    md += ["", "## Field accuracy", "", "![Field accuracy](field_accuracy.png)", ""]
    md.append(_table(
        ["Field", "Accuracy"],
        [[f"`{f}`", pct(v)] for f, v in sorted(result.field_accuracy.items())],
    ))  # fmt: skip

    md += ["", "## Fault catch rate by fault type", ""]
    if result.fault_catch_by_type:
        md.append(_table(
            ["Injected fault", "Sent to review"],
            [[f"`{k}`", pct(v)] for k, v in result.fault_catch_by_type.items()],
        ))  # fmt: skip
    else:
        md.append("No documents with injected faults in this run.")

    md += ["", "## Breakdown", "", "![By quality](accuracy_by_quality.png)"]
    for key, groups in result.breakdown.items():
        md += ["", f"### By {key}", ""]
        md.append(_table(
            [key, "n", "Automation", "Auto-approved acc.", "Error catch", "Fault catch",
             "Doc accuracy", "Item F1"],
            [[name, str(g["n"])] + [pct(g[m]) for m in BREAKDOWN_METRICS]
             for name, g in groups.items()],
        ))  # fmt: skip

    md += [
        "",
        "## Threshold trade-off",
        "",
        "Raising the threshold sends more documents to review and makes the auto-approved "
        "set more accurate.",
        "",
        "![Threshold trade-off](threshold_tradeoff.png)",
        "",
    ]
    md.append(_table(
        ["Threshold", "Automation rate", "Auto-approved accuracy"],
        [[f"{r['threshold']:.2f}", pct(r["automation_rate"]), pct(r["auto_approved_accuracy"])]
         for r in result.tradeoff],
    ))  # fmt: skip

    md += ["", "## Calibration", "",
           "Do fields with confidence X turn out correct X% of the time?", "",
           "![Calibration](calibration.png)", ""]  # fmt: skip
    md.append(_table(
        ["Confidence bin", "Fields", "Mean confidence", "Accuracy"],
        [[f"{r['bin_low']:.1f}-{r['bin_high']:.1f}", str(r["n"]), f"{r['mean_confidence']:.2f}",
          pct(r["accuracy"])] for r in result.calibration],
    ))  # fmt: skip
    md.append("")

    path = out_dir / "report.md"
    path.write_text("\n".join(md), encoding="utf-8")
    return path
