import random

import pytest

from docex.groundtruth import GroundTruth, read_ground_truth, write_ground_truth
from docex.providers.mock import MockProvider, corrupt
from docex.schemas import DocumentMeta, Invoice
from docex.synthetic.generator import make_invoice


def invoice_doc_n(tmp_path, index, quality) -> DocumentMeta:
    si = make_invoice(42, index, False)
    gt_rel = f"ground_truth/{si.doc_id}.json"
    write_ground_truth(
        tmp_path / gt_rel,
        GroundTruth(si.doc_id, "invoice", "synthetic", si.invoice.model_dump(mode="json")),
    )
    return DocumentMeta(
        si.doc_id,
        "invoice",
        "synthetic",
        f"documents/synthetic/{si.doc_id}.pdf",
        quality,
        si.layout.template,
        (),
        gt_rel,
    )


def invoice_doc(tmp_path, quality) -> DocumentMeta:
    return invoice_doc_n(tmp_path, 1, quality)


def test_zero_error_returns_ground_truth(tmp_path):
    doc = invoice_doc(tmp_path, "clean")
    r = MockProvider(tmp_path, base_error_rate=0, failure_rate=0).extract(doc, Invoice, 1)
    assert r.status == "ok" and r.simulated and r.cost_usd == 0.0
    assert r.data == read_ground_truth(tmp_path / doc.gt_path).data
    assert r.input_tokens == 1500 and r.output_tokens > 0 and r.latency_ms >= 900


def test_deterministic(tmp_path):
    doc = invoice_doc(tmp_path, "scan_heavy")
    m = MockProvider(tmp_path, base_error_rate=0.3)
    assert m.extract(doc, Invoice, 1).data == m.extract(doc, Invoice, 1).data


def test_errors_change_values_but_keep_json_types():
    gt = make_invoice(42, 1, False).invoice.model_dump(mode="json")
    out, paths = corrupt(gt, "invoice", 1.0, random.Random(3))
    assert paths and out != gt
    for field in ("subtotal", "total", "invoice_date", "seller_name"):
        assert out[field] is None or isinstance(out[field], str)


def test_error_rate_scales_with_quality():
    rng = random.Random(0)
    gt = make_invoice(42, 1, False).invoice.model_dump(mode="json")
    clean = sum(len(corrupt(gt, "invoice", 0.03 * 1.0, rng)[1]) for _ in range(400))
    heavy = sum(len(corrupt(gt, "invoice", 0.03 * 3.0, rng)[1]) for _ in range(400))
    assert heavy > 2 * clean > 0


def test_day_month_swap_only_when_valid():
    gt = {"invoice_date": "2026-11-25"}  # day 25 cannot be swapped into a month
    for seed in range(200):
        out, paths = corrupt(gt, "invoice", 1.0, random.Random(seed))
        if out["invoice_date"] is not None:
            year, month, day = map(int, out["invoice_date"].split("-"))
            assert month <= 12


def test_correlation_one_repeats_errors(tmp_path):
    doc = invoice_doc(tmp_path, "scan_heavy")
    m = MockProvider(tmp_path, base_error_rate=0.3, consistency_correlation=1.0, failure_rate=0)
    a1, a2 = m.extract(doc, Invoice, 1).data, m.extract(doc, Invoice, 2).data
    gt = read_ground_truth(tmp_path / doc.gt_path).data
    repeated = 0
    for k, v in a1.items():
        if k != "line_items" and v != gt.get(k):
            assert a2[k] == v
            repeated += 1
    assert repeated > 0
    assert len(a1["line_items"]) == len(a2["line_items"])


def test_correlation_zero_differs_somewhere(tmp_path):
    docs = [invoice_doc_n(tmp_path, i, "scan_heavy") for i in range(1, 11)]
    m = MockProvider(tmp_path, base_error_rate=0.3, consistency_correlation=0.0, failure_rate=0)
    assert any(m.extract(d, Invoice, 1).data != m.extract(d, Invoice, 2).data for d in docs)


def test_failure_and_missing_gt(tmp_path):
    doc = invoice_doc(tmp_path, "clean")
    failed = MockProvider(tmp_path, failure_rate=1.0).extract(doc, Invoice, 1)
    assert failed.status == "failed" and failed.data is None
    assert failed.error == "simulated provider failure"
    (tmp_path / doc.gt_path).unlink()
    r = MockProvider(tmp_path, failure_rate=0).extract(doc, Invoice, 1)
    assert r.status == "failed" and doc.gt_path.split("/")[-1] in r.error


@pytest.mark.parametrize("quality", ["clean", "scan_light", "scan_heavy", "photo"])
def test_receipts_supported(tmp_path, quality):
    gt = {
        "doc_type": "receipt",
        "items": [{"name": "Es Teh", "quantity": "2", "price": "10000.00"}],
        "subtotal": "10000.00",
        "discount": None,
        "service_charge": None,
        "tax": None,
        "total": "10000.00",
        "cash": None,
        "change": None,
    }
    write_ground_truth(
        tmp_path / "ground_truth/cord-0001.json", GroundTruth("cord-0001", "receipt", "cord", gt)
    )
    doc = DocumentMeta(
        "cord-0001",
        "receipt",
        "cord",
        "documents/cord/cord-0001.png",
        quality,
        None,
        (),
        "ground_truth/cord-0001.json",
    )
    r = MockProvider(tmp_path, base_error_rate=0.5, failure_rate=0).extract(doc, Invoice, 1)
    assert r.status == "ok" and set(r.data) == set(gt)
