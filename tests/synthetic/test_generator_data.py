from docex.synthetic.catalog import PRODUCTS, TEMPLATES
from docex.synthetic.generator import FAULT_RULE, FAULT_TYPES, make_invoice
from docex.validation.normalize import npwp_digits
from docex.validation.rules import validate
from tests.helpers import TODAY


def hard_failures(si):
    out = validate(si.invoice.model_dump(mode="json"), "invoice", TODAY)
    return {r.rule_id for r in out.results if not r.passed and r.severity == "hard"}


def test_deterministic():
    assert make_invoice(42, 7, False) == make_invoice(42, 7, False)
    assert make_invoice(42, 7, False) != make_invoice(43, 7, False)


def test_doc_id_format():
    assert make_invoice(42, 7, False).doc_id == "inv-0007"


def test_clean_invoices_pass_all_hard_rules():  # Review Focus #3
    bad = [i for i in range(300) if hard_failures(make_invoice(42, i, False))]
    assert bad == []


def test_each_fault_triggers_its_rule():
    seen = set()
    for i in range(300):
        si = make_invoice(42, i, True)
        (fault,) = si.faults
        assert FAULT_RULE[fault] in hard_failures(si), (i, fault)
        seen.add(fault)
    assert seen == set(FAULT_TYPES)


def test_invalid_npwp_is_14_digits():
    for i in range(300):
        si = make_invoice(42, i, True)
        if si.faults == ("invalid_npwp",):
            assert len(npwp_digits(si.invoice.seller_npwp)) == 14
            return
    raise AssertionError("no invalid_npwp fault generated")


def test_variety():
    sis = [make_invoice(42, i, False) for i in range(200)]
    assert {s.tax_scheme for s in sis} == {"ppn11", "dpp_nilai_lain"}
    assert {s.layout.template for s in sis} == set(TEMPLATES)
    assert all(1 <= len(s.invoice.line_items) <= 8 for s in sis)
    assert any(s.invoice.discount > 0 for s in sis)
    assert any(s.invoice.due_date is None for s in sis)
    assert any(s.invoice.buyer_npwp is None for s in sis)


def test_catalog_size():
    assert len(PRODUCTS) >= 30
