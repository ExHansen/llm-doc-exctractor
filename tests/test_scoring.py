from docex.scoring import doc_confidence, score_fields
from docex.validation.rules import validate
from tests.helpers import TODAY, clean_invoice_raw


def scores_by_field(raw, others=()):
    out = validate(raw, "invoice", TODAY)
    return {x.field: x for x in score_fields("invoice", out, list(others))}


def test_clean_doc_scores_one():
    out = validate(clean_invoice_raw(), "invoice", TODAY)
    scores = score_fields("invoice", out, [out.draft])
    assert all(s.confidence == 1.0 for s in scores) and doc_confidence("invoice", scores) == 1.0


def test_scores_cover_scalars_and_item_fields():
    s = scores_by_field(clean_invoice_raw())
    assert "total" in s and "line_items.1.amount" in s and "line_items.0.description" in s
    assert s["total"].value == "111000.00" and s["invoice_date"].value == "2026-11-05"


def test_hard_rule_halves_involved_fields():
    raw = clean_invoice_raw()
    raw["total"] = "999.00"
    s = scores_by_field(raw)
    assert s["total"].confidence == 0.5 and s["subtotal"].confidence == 0.5
    assert s["seller_name"].confidence == 1.0 and "R06 failed" in s["total"].reasons


def test_soft_rule_penalty():
    raw = clean_invoice_raw()
    raw.update(tax_rate="0.10", tax_amount="10000.00", total="110000.00")
    assert scores_by_field(raw)["tax_rate"].confidence == 0.8


def test_invalid_npwp_is_format_penalty_only():
    raw = clean_invoice_raw()
    raw["seller_npwp"] = "123"
    s = scores_by_field(raw)
    assert s["seller_npwp"].confidence == 0.3


def test_disagreement_penalty():
    a = validate(clean_invoice_raw(), "invoice", TODAY)
    raw_b = clean_invoice_raw()
    raw_b["seller_name"] = "PT Lain"
    b = validate(raw_b, "invoice", TODAY)
    s = {x.field: x for x in score_fields("invoice", a, [b.draft])}
    assert s["seller_name"].confidence == 0.4 and "attempts disagree" in s["seller_name"].reasons
    assert doc_confidence("invoice", list(s.values())) == 0.4


def test_penalties_multiply():
    raw = clean_invoice_raw()
    raw["total"] = "999.00"
    other = validate(clean_invoice_raw(), "invoice", TODAY).draft
    s = scores_by_field(raw, [other])
    assert s["total"].confidence == 0.2  # 0.5 (R06) x 0.4 (disagree)


def test_missing_required_is_zero():
    raw = clean_invoice_raw()
    raw["invoice_number"] = None
    s = scores_by_field(raw)
    assert s["invoice_number"].confidence == 0.0


def test_receipt_subtotal_ignored_when_absent():
    out = validate({"items": [], "total": "5000"}, "receipt", TODAY)
    assert doc_confidence("receipt", score_fields("receipt", out, [])) == 1.0


def test_receipt_subtotal_counts_when_present():
    raw = {"items": [{"name": "Es Teh", "price": "10000"}], "subtotal": "10000", "total": "5000"}
    out = validate(raw, "receipt", TODAY)  # R22 soft fails: subtotal, total x0.8
    assert doc_confidence("receipt", score_fields("receipt", out, [])) == 0.8
