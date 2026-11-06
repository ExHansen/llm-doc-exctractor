from docex.evaluation.metrics import evaluate
from docex.evaluation.report import write_report
from tests.evaluation.test_metrics import rec

FILES = (
    "report.md",
    "metrics.json",
    "field_accuracy.png",
    "accuracy_by_quality.png",
    "threshold_tradeoff.png",
    "calibration.png",
)


def test_report_files(tmp_path):
    recs = [
        rec("a", "auto_approved", 0.9, True),
        rec(
            "b",
            "needs_review",
            0.3,
            False,
            faults=("tax_mismatch",),
            hard_failed=True,
            quality="scan_heavy",
        ),
    ]
    path = write_report(evaluate(recs, "r1", True), tmp_path, threshold=0.7)
    for f in FILES:
        assert (tmp_path / f).exists(), f
    text = path.read_text(encoding="utf-8")
    assert "Simulated extractor" in text and "Automation rate" in text and "tax_mismatch" in text
    for f in FILES[2:]:
        assert f"]({f})" in text


def test_report_without_simulated_banner(tmp_path):
    path = write_report(evaluate([rec("a", "needs_review", 0.1, True)], "r2", False), tmp_path)
    assert "Simulated extractor" not in path.read_text(encoding="utf-8")


def test_breakdown_table_lists_every_headline_metric(tmp_path):
    path = write_report(evaluate([rec("a", "auto_approved", 0.9, True)], "r3", True), tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "| quality | n | Automation | Auto-approved acc. | Error catch | Fault catch |" in text
    assert "`invoice.total`" in text and "failed extractions excluded" in text
