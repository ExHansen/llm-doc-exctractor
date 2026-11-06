from decimal import Decimal

import pytest

from docex.validation.rules import build_draft, validate
from tests.helpers import TODAY, clean_invoice_raw


def failed(outcome):
    return {r.rule_id for r in outcome.results if not r.passed}


def test_clean_invoice_passes_everything():
    assert failed(validate(clean_invoice_raw(), "invoice", TODAY)) == set()


@pytest.mark.parametrize(
    "mutate,rule",
    [
        (lambda d: d.update(total="999.00"), "R06"),
        (lambda d: d.update(tax_amount="12000.00"), "R05"),
        (lambda d: d["line_items"][0].update(amount="46000.00"), "R02"),
        (
            lambda d: d.update(
                subtotal="90000.00", tax_base="90000.00", tax_amount="9900.00", total="99900.00"
            ),
            "R03",
        ),
        (lambda d: d.update(seller_npwp="01.234.567.8-901.00"), "R07"),
        (lambda d: d.update(seller_npwp=None), "R01"),
        (lambda d: d.update(buyer_npwp="123"), "R07B"),
        (lambda d: d.update(invoice_date="2014-01-02", due_date=None), "R08"),
        (lambda d: d.update(due_date="2026-10-01"), "R09"),
        (lambda d: d.update(tax_rate="0.10", tax_amount="10000.00", total="110000.00"), "R10"),
        (
            lambda d: d.update(
                discount="-5000.00", total="116000.00", tax_base="105000.00", tax_amount="11550.00"
            ),
            "R11",
        ),
        (lambda d: d.update(invoice_date="31/02/2026"), "R00_parse"),
        (lambda d: d.update(invoice_number=None), "R01"),
        (lambda d: d.update(line_items=[]), "R01"),
    ],
)
def test_each_rule_fires(mutate, rule):
    raw = clean_invoice_raw()
    mutate(raw)
    assert rule in failed(validate(raw, "invoice", TODAY))


def test_dpp_nilai_lain_scheme_passes():
    raw = clean_invoice_raw()
    raw.update(tax_base="91667.00", tax_rate="0.12", tax_amount="11000.00", total="111000.00")
    assert failed(validate(raw, "invoice", TODAY)) == set()


def test_discount_is_subtracted_before_tax():
    raw = clean_invoice_raw()
    raw.update(discount="10000.00", tax_base="90000.00", tax_amount="9900.00", total="99900.00")
    assert failed(validate(raw, "invoice", TODAY)) == set()


def test_r09_is_hard_and_r04_is_soft():
    raw = clean_invoice_raw()
    raw.update(due_date="2026-10-01", tax_base="95000.00", tax_amount="10450.00", total="110450.00")
    sev = {r.rule_id: r.severity for r in validate(raw, "invoice", TODAY).results if not r.passed}
    assert sev == {"R09": "hard", "R04": "soft"}


def test_r02_reports_line_and_fields():
    raw = clean_invoice_raw()
    raw["line_items"][1]["amount"] = "56000.00"
    r02 = [
        r for r in validate(raw, "invoice", TODAY).results if r.rule_id == "R02" and not r.passed
    ]
    assert len(r02) == 1 and r02[0].message.startswith("line 2:")
    assert "line_items.1.amount" in r02[0].fields


def test_unparseable_value_keeps_other_fields():
    raw = clean_invoice_raw()
    raw["total"] = "12a.000"
    out = validate(raw, "invoice", TODAY)
    assert out.draft.total is None and out.draft.subtotal == Decimal("100000.00")
    parse = [r for r in out.results if r.rule_id == "R00_parse"]
    assert parse[0].fields == ("total",) and parse[0].severity == "hard"


def test_build_draft_parses_indonesian_formats():
    raw = clean_invoice_raw()
    raw.update(total="Rp 111.000,00", invoice_date="05 November 2026", tax_rate="11%")
    draft, results = build_draft(raw, "invoice")
    assert results == []
    assert draft.total == Decimal("111000.00") and draft.tax_rate == Decimal("0.11")


def test_none_input_gives_empty_draft():
    out = validate(None, "invoice", TODAY)
    r01 = [r for r in out.results if r.rule_id == "R01"][0]
    assert not r01.passed and "invoice_number" in r01.fields and "line_items" in r01.fields


def test_receipt_rules_are_soft_except_total():
    raw = {
        "items": [{"name": "Es Teh", "quantity": "2", "price": "10000"}],
        "subtotal": "10000",
        "total": "11000",
        "cash": "20000",
        "change": "8000",
    }
    res = {r.rule_id: r for r in validate(raw, "receipt", TODAY).results}
    assert not res["R22"].passed and res["R22"].severity == "soft"
    assert not res["R23"].passed and res["R21"].passed
    assert validate({"items": []}, "receipt", TODAY).results[0].rule_id in {"R01", "R20"}


def test_receipt_missing_total_is_hard():
    res = [r for r in validate({"items": []}, "receipt", TODAY).results if not r.passed]
    assert {r.rule_id for r in res} >= {"R20"} and all(r.severity == "hard" for r in res)


def test_receipt_negative_item_price_is_not_r11():
    raw = {"items": [{"name": "Diskon", "price": "-5000"}], "total": "0"}
    assert "R11" not in failed(validate(raw, "receipt", TODAY))


def test_missing_seller_npwp_is_reported_as_missing():
    raw = clean_invoice_raw()
    raw["seller_npwp"] = None
    results = [r for r in validate(raw, "invoice", TODAY).results if not r.passed]
    assert [r.rule_id for r in results] == ["R01"] and results[0].fields == ("seller_npwp",)


def test_receipts_use_r20_not_r01():
    ids = {r.rule_id for r in validate({"items": []}, "receipt", TODAY).results}
    assert "R20" in ids and "R01" not in ids
