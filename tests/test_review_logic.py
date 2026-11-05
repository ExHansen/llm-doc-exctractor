from docex.groundtruth import read_ground_truth
from docex.review_logic import build_corrected, export_labels, form_values
from docex.schemas import DocumentMeta
from docex.storage import Store
from tests.helpers import clean_invoice_raw


def test_form_values_are_strings():
    scalars, items = form_values("invoice", clean_invoice_raw())
    assert scalars["total"] == "111000.00" and scalars["buyer_npwp"] == ""
    assert items[0]["quantity"] == "3" and set(items[0]) == {
        "description",
        "quantity",
        "unit_price",
        "amount",
    }


def test_form_values_for_missing_data():
    scalars, items = form_values("receipt", None)
    assert scalars["total"] == "" and items == []


def test_build_corrected_keeps_exact_decimals():  # Review Focus #5
    scalars, items = form_values("invoice", clean_invoice_raw())
    scalars["total"] = "Rp 1.234.567,00"
    data, errors = build_corrected("invoice", scalars, items)
    assert errors == [] and data["total"] == "1234567.00"


def test_build_corrected_reports_errors():
    scalars, items = form_values("invoice", clean_invoice_raw())
    scalars["invoice_date"] = "31/02/2026"
    scalars["seller_name"] = ""
    data, errors = build_corrected("invoice", scalars, items)
    assert data is None
    assert any("invoice_date" in e for e in errors) and any("seller_name" in e for e in errors)


def test_build_corrected_skips_blank_item_rows():
    scalars, items = form_values("invoice", clean_invoice_raw())
    items.append({"description": "", "quantity": "", "unit_price": "", "amount": ""})
    data, errors = build_corrected("invoice", scalars, items)
    assert errors == [] and len(data["line_items"]) == 2


def test_export_labels(tmp_path):
    meta = DocumentMeta(
        "inv-0001",
        "invoice",
        "synthetic",
        "documents/synthetic/inv-0001.pdf",
        "clean",
        "modern",
        (),
        "ground_truth/inv-0001.json",
    )
    corrected = build_corrected("invoice", *form_values("invoice", clean_invoice_raw()))[0]
    with Store(tmp_path / "d.duckdb") as st:
        st.upsert_documents([meta])
        st.save_review("r1", "inv-0001", "correct", corrected)
        st.save_review("r1", "inv-0002", "approve", None)
        paths = export_labels(st, "r1", tmp_path)
    assert paths == [tmp_path / "labels" / "inv-0001.json"]
    label = read_ground_truth(paths[0])
    assert label.data == corrected and label.source == "synthetic"
