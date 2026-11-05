# llm-doc-extractor Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline document-extraction QC pipeline (synthetic Indonesian invoices + CORD receipts → mock extractor → validation → confidence → routing → Streamlit review → evaluation report), runnable with `uv run docex demo`.

**Architecture:** A `src/docex` Python package with small single-purpose modules that pass shared dataclasses (`results.py`) and Pydantic models (`schemas.py`). DuckDB stores every run under its own `run_id`; a Typer CLI drives each stage; a Streamlit app reads and writes the same DuckDB file. The only provider is `mock`, behind an `ExtractionProvider` protocol and a registry.

**Tech Stack:** Python 3.11, uv, Pydantic v2, pydantic-settings, Typer, Rich, Faker, ReportLab, pypdfium2, Pillow, NumPy, DuckDB, Streamlit, Matplotlib, RapidFuzz, huggingface_hub, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-11-05-llm-doc-extractor-design.md`

## Global Constraints

- Python `>=3.11`; `.python-version` = `3.11`; dependency management with uv only (`uv add`, `uv sync`, `uv run`).
- No network and no API keys at test or demo time. Only `docex fetch-cord` uses the network. The only provider in phase 1 is `mock`.
- Money is `Decimal` quantized to `Decimal("0.01")`, currency `IDR`. Dates are `datetime.date`. JSON stores Decimal as string and dates as ISO `YYYY-MM-DD` (Pydantic `model_dump(mode="json")`).
- Everything is deterministic given `seed` (default `42`). Use `random.Random(f"{seed}:{doc_id}:{attempt}")`-style string seeds, never the global `random`.
- Paths stored in DuckDB and in `DocumentMeta` are POSIX strings relative to `data_dir`.
- Data layout: `data/documents/synthetic/inv-0001.pdf`, `data/documents/cord/cord-0001.png`, `data/ground_truth/<doc_id>.json`, `data/labels/<doc_id>.json`, `data/docex.duckdb`; reports go to `reports/<run_id>/`.
- `run_id` = `YYYYMMDD-HHMMSS-<provider>`, with suffix `-2`, `-3`, … if it already exists.
- Every metric computed from a run whose extractions are `simulated` is labeled "simulated extractor" in the CLI output and the report.
- Code, docstrings, CLI text, and README are in English. The spec stays in Indonesian.
- Must work on Windows (the dev machine) and ubuntu-latest (CI): use `pathlib`, and no shell-specific calls except `sys.executable -m streamlit`.
- Commit after every task. Local commits only, never push. Every commit message ends with a blank line and then `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Before writing any chart code (Task 10), load the `dataviz` skill and follow it.

## Review Focus

1. **Re-running `docex generate` with the same seed:** must overwrite the same files and leave the `documents` row count at `n`, with no duplicates. *Test in Task 9:* `test_generate_twice_is_idempotent`.
2. **A Streamlit session open while `docex run` writes:** `Store` must not keep a DuckDB connection open after `close()`/context exit, so a second process can open the file. *Test in Task 6:* `test_store_releases_file_after_close`.
3. **Clean invoices across both tax schemes, with discounts and rounding:** must never fail a hard rule. If they did, the review queue would be full of false alarms. *Test in Task 4:* `test_clean_invoices_pass_all_hard_rules` with 300 invoices.
4. **`docex run` or `docex eval` on an empty database:** both must print a clear next step and exit with code 1 instead of a traceback. *Tests in Task 9 and Task 10:* `test_run_without_documents_exits_1` and `test_eval_without_runs_exits_1`.
5. **Large rupiah amounts edited in the review UI:** must round-trip exactly, with no float conversion, so `Rp 1.234.567,00` stays `1234567.00`. Use text inputs, not `st.number_input`. *Test in Task 12:* `test_build_corrected_keeps_exact_decimals`.

---

## File Map

| File | Responsibility | Task |
|---|---|---|
| `pyproject.toml`, `.python-version`, `.gitignore`, `.gitattributes`, `.env.example`, `LICENSE` | Project setup | 1 |
| `src/docex/schemas.py` | Pydantic document models, draft models, field kinds, required/critical fields, `DocumentMeta` | 1 |
| `src/docex/groundtruth.py` | `GroundTruth` dataclass, read/write JSON | 1 |
| `src/docex/config.py` | `Settings` (pydantic-settings) | 1 |
| `src/docex/validation/normalize.py` | Parse Indonesian/English numbers, dates, NPWP, rates, text | 2 |
| `src/docex/results.py` | Shared result dataclasses | 3 |
| `src/docex/validation/rules.py` | Draft building (R00/R01) and business rules R02–R23 | 3 |
| `src/docex/synthetic/catalog.py` | Product catalog, invoice-number and format choices | 4 |
| `src/docex/synthetic/generator.py` | `make_invoice` (data plus faults); `generate_dataset` (files) | 4, 5 |
| `src/docex/synthetic/templates.py` | Amount/date formatting and 3 ReportLab templates | 5 |
| `src/docex/imaging.py` | Render the first page of a PDF or an image to PIL | 5 |
| `src/docex/synthetic/degrade.py` | "Scanned" degradation to an image-only PDF | 5 |
| `src/docex/storage.py` | DuckDB `Store` | 6 |
| `src/docex/providers/base.py`, `mock.py`, `registry.py` | Provider protocol, mock error model, registry | 7 |
| `src/docex/scoring.py`, `src/docex/routing.py` | Field and document confidence; route decision | 8 |
| `src/docex/pipeline.py`, `src/docex/cli.py` | Run orchestration; Typer CLI | 9 (CLI grows in 10–12) |
| `src/docex/evaluation/matching.py`, `metrics.py`, `report.py` | Field matching, metrics, Markdown and PNG report | 10 |
| `src/docex/datasets/cord.py` | CORD download, normalization, materialization | 11 |
| `src/docex/review_logic.py`, `src/docex/review_app.py` | Review form logic (testable); Streamlit UI | 12 |
| `README.md`, `.github/workflows/ci.yml`, `docs/example-report/` | Docs, CI, sample report | 13 |

---

### Task 1: Project scaffold, schemas, ground-truth I/O, settings

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.gitignore`, `.gitattributes`, `.env.example`, `LICENSE`, `src/docex/__init__.py`, `src/docex/schemas.py`, `src/docex/groundtruth.py`, `src/docex/config.py`
- Test: `tests/test_schemas.py`, `tests/test_groundtruth.py`, `tests/test_config.py`

**Interfaces:**
- Produces (`schemas.py`):
  - `DocType = Literal["invoice", "receipt"]`
  - `Quality = Literal["clean", "scan_light", "scan_heavy", "photo"]`
  - `FieldKind = Literal["money", "quantity", "rate", "date", "id", "npwp", "text"]`
  - `InvoiceLineItem`, `Invoice`, `ReceiptItem`, `Receipt`: exactly as spec §3.1.
  - Draft models `InvoiceLineItemDraft`, `InvoiceDraft`, `ReceiptItemDraft`, `ReceiptDraft`: same fields, every field `X | None = None`. List fields default to `[]`, and `doc_type` keeps its literal default.
  - `SCHEMAS: dict[DocType, type[BaseModel]]` and `DRAFTS: dict[DocType, type[BaseModel]]`.
  - `ITEMS_KEY: dict[DocType, str] = {"invoice": "line_items", "receipt": "items"}`.
  - `FIELD_KINDS: dict[DocType, dict[str, FieldKind]]`: scalar fields only, excluding `doc_type` and `currency`.
    - Invoice: `invoice_number:id, invoice_date:date, due_date:date, seller_name:text, seller_npwp:npwp, buyer_name:text, buyer_npwp:npwp, subtotal:money, discount:money, tax_base:money, tax_rate:rate, tax_amount:money, total:money`.
    - Receipt: `subtotal, discount, service_charge, tax, total, cash, change`, all `money`.
  - `ITEM_FIELD_KINDS: dict[DocType, dict[str, FieldKind]]`:
    - Invoice: `description:text, quantity:quantity, unit_price:money, amount:money`.
    - Receipt: `name:text, quantity:quantity, price:money`.
  - `REQUIRED_FIELDS`:
    - Invoice: `("invoice_number","invoice_date","seller_name","buyer_name","subtotal","tax_base","tax_rate","tax_amount","total")`.
    - Receipt: `("total",)`.
  - `CRITICAL_FIELDS`:
    - Invoice: `("invoice_number","invoice_date","seller_name","seller_npwp","subtotal","tax_amount","total")`.
    - Receipt: `("total","subtotal")`.
  - `@dataclass(frozen=True) DocumentMeta(doc_id: str, doc_type: DocType, source: Literal["synthetic","cord"], path: str, quality: Quality, template: str | None, injected_faults: tuple[str, ...], gt_path: str)`, where paths are relative POSIX.
- Produces (`groundtruth.py`):
  - `@dataclass(frozen=True) GroundTruth(doc_id: str, doc_type: DocType, source: str, data: dict, injected_faults: tuple[str, ...] = (), gt_issues: tuple[str, ...] = ())`
  - `write_ground_truth(path: Path, gt: GroundTruth) -> None`: UTF-8, `indent=2`, `sort_keys=True`, trailing newline.
  - `read_ground_truth(path: Path) -> GroundTruth`
- Produces (`config.py`):
  - `Settings(BaseSettings)` with `env_prefix="DOCEX_"`, `env_file=".env"`, `extra="ignore"`. Fields and defaults from spec §4.12: `data_dir=Path("data")`, `db_path: Path | None = None`, `reports_dir=Path("reports")`, `provider="mock"`, `seed=42`, `consistency_runs=2`, `review_threshold=0.7`, `mock_base_error_rate=0.03`, `mock_consistency_correlation=0.5`, `mock_failure_rate=0.01`.
  - Property `resolved_db_path -> Path`, which is `db_path or data_dir / "docex.duckdb"`.

- [ ] **Step 1: Scaffold the project**

Write `pyproject.toml` with:
- `[project] name="llm-doc-extractor"`, `version="0.1.0"`, `requires-python=">=3.11"`, `[project.scripts] docex="docex.cli:app"`;
- hatchling build with `[tool.hatch.build.targets.wheel] packages=["src/docex"]`;
- `[tool.ruff] line-length=100`, `target-version="py311"`, `[tool.ruff.lint] select=["E","F","I","UP","B"]`;
- `[tool.pytest.ini_options] testpaths=["tests"]`.

Then run:
`uv add pydantic pydantic-settings typer rich faker reportlab pypdfium2 pillow numpy duckdb streamlit matplotlib rapidfuzz huggingface_hub`
`uv add --dev pytest ruff`

Remaining setup files:
- `.gitignore`: `.venv/`, `__pycache__/`, `data/`, `reports/`, `.env`, `.pytest_cache/`, `.ruff_cache/`.
- `.gitattributes`: `* text=auto eol=lf`, `*.png binary`, `*.pdf binary`.
- `.env.example`: one commented line per Settings field.
- `LICENSE`: MIT, "Copyright (c) 2026 Hansen Vernandez".
- `src/docex/__init__.py`: contains `__version__ = "0.1.0"`.

Expected: `uv sync` succeeds.

- [ ] **Step 2: Write failing tests**

```python
# tests/test_schemas.py
def test_invoice_requires_line_items_and_totals():
    with pytest.raises(ValidationError):
        Invoice(
            invoice_number="INV/1",
            invoice_date=date(2026, 11, 5),
            seller_name="PT A",
            buyer_name="PT B",
            line_items=[],
            subtotal=Decimal("0"),
        )  # missing tax/total


def test_draft_accepts_partial_data():
    d = InvoiceDraft(total=Decimal("1000.00"))
    assert d.invoice_number is None and d.line_items == [] and d.doc_type == "invoice"


def test_field_kinds_cover_required_and_critical():
    for t in ("invoice", "receipt"):
        assert set(REQUIRED_FIELDS[t]) <= set(FIELD_KINDS[t])
        assert set(CRITICAL_FIELDS[t]) <= set(FIELD_KINDS[t])


# tests/test_groundtruth.py
def test_ground_truth_roundtrip(tmp_path):
    gt = GroundTruth("inv-0001", "invoice", "synthetic", {"total": "1000.00"}, ("total_mismatch",))
    write_ground_truth(tmp_path / "g.json", gt)
    assert read_ground_truth(tmp_path / "g.json") == gt


# tests/test_config.py
def test_settings_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCEX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DOCEX_REVIEW_THRESHOLD", "0.8")
    s = Settings()
    assert s.review_threshold == 0.8
    assert s.resolved_db_path == tmp_path / "docex.duckdb"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'docex.schemas'` (or similar).

- [ ] **Step 4: Implement `schemas.py`, `groundtruth.py`, `config.py`** per Interfaces.

- [ ] **Step 5: Run tests and lint**

Run: `uv run pytest -v; uv run ruff check; uv run ruff format --check`
Expected: all PASS, no lint errors.

- [ ] **Step 6: Commit**

`git add -A; git commit` with message `feat: scaffold project with schemas, ground-truth I/O and settings`.

---

### Task 2: Normalization of Indonesian formats

**Files:**
- Create: `src/docex/validation/__init__.py`, `src/docex/validation/normalize.py`
- Test: `tests/validation/test_normalize.py`

**Interfaces:**
- Produces:
  - `class ParseError(ValueError)`
  - `parse_number(value: str | int | float | Decimal | None) -> Decimal | None`: returns `None` for `None` or blank, and raises `ParseError` when unparseable. Not quantized; callers quantize money.
  - `parse_rate(value) -> Decimal | None`: `"11%"`, `"0.11"`, `11`, and `"12 %"` all become `Decimal("0.11")`/`Decimal("0.12")`. Values above 1 are treated as percentages.
  - `parse_date(value: str | date | None) -> date | None`: raises `ParseError`.
  - `npwp_digits(value: str | None) -> str | None`: strips everything except digits; returns `None` if the input is `None` or blank.
  - `is_valid_npwp(digits: str | None) -> bool`: `True` iff the value is 15 or 16 digits.
  - `normalize_text(value: str | None) -> str`: casefold, collapse whitespace, strip leading/trailing punctuation. `None` becomes `""`.

Number algorithm:

```text
strip currency words/symbols (Rp, IDR, @, x, ×) and spaces; keep leading '-'
if both ',' and '.': the LAST one is the decimal separator, the other is thousands
elif only '.': thousands if every group after the first has exactly 3 digits, else decimal
elif only ',': same rule with ','
any leftover non-digit (other than one decimal point) -> ParseError
```

Date formats to accept:
- `YYYY-MM-DD`;
- `DD/MM/YYYY` and `DD-MM-YYYY` (day first, Indonesian);
- `D Month YYYY` and `D Mon YYYY` with Indonesian or English month names, full or 3-letter, case-insensitive (`Januari/January/Jan`, `Februari/February/Feb`, `Maret/March/Mar`, `April/Apr`, `Mei/May`, `Juni/June/Jun`, `Juli/July/Jul`, `Agustus/August/Agu/Aug`, `September/Sep`, `Oktober/October/Okt/Oct`, `November/Nov`, `Desember/December/Des/Dec`).

Invalid calendar dates raise `ParseError`.

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Rp 1.234.567,00", "1234567.00"),
        ("1.234.567", "1234567"),
        ("1,234,567", "1234567"),
        ("IDR 1,234,567.50", "1234567.50"),
        ("@15.000", "15000"),
        ("x2", "2"),
        ("12.5", "12.5"),
        ("1,5", "1.5"),
        ("-5,000", "-5000"),
        (1500, "1500"),
        ("", None),
        (None, None),
    ],
)
def test_parse_number(raw, expected):
    assert parse_number(raw) == (Decimal(expected) if expected else None)


@pytest.mark.parametrize("raw", ["12a.000", "1.2.3,4,5", "abc"])
def test_parse_number_rejects_garbage(raw):
    with pytest.raises(ParseError):
        parse_number(raw)


@pytest.mark.parametrize(
    "raw",
    ["05 November 2026", "05/11/2026", "2026-11-05", "5 Nov 2026", "5 nov 2026", "05-11-2026"],
)
def test_parse_date_variants(raw):
    assert parse_date(raw) == date(2026, 11, 5)


def test_parse_date_indonesian_month():
    assert parse_date("17 Agustus 2026") == date(2026, 8, 17)
    assert parse_date("3 Okt 2026") == date(2026, 10, 3)


def test_parse_date_invalid_calendar():
    with pytest.raises(ParseError):
        parse_date("31/02/2026")


def test_rates():
    assert parse_rate("11%") == Decimal("0.11") and parse_rate("0.12") == Decimal("0.12")
    assert parse_rate(12) == Decimal("0.12")


def test_npwp():
    assert npwp_digits("01.234.567.8-901.000") == "012345678901000"
    assert is_valid_npwp("012345678901000") and is_valid_npwp("0123456789012345")
    assert not is_valid_npwp("01234567890100")


def test_normalize_text():
    assert normalize_text("  PT.  Maju   Jaya, ") == "pt. maju jaya"
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/validation/test_normalize.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement `normalize.py`** per Interfaces and algorithm.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/validation/test_normalize.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

Message: `feat: parse Indonesian number, date, rate and NPWP formats`.

---

### Task 3: Shared result types and validation rules

**Files:**
- Create: `src/docex/results.py`, `src/docex/validation/rules.py`
- Test: `tests/validation/test_rules.py`

**Interfaces:**
- Produces (`results.py`):
  - `@dataclass(frozen=True) RuleResult(rule_id: str, severity: Literal["hard","soft"], passed: bool, fields: tuple[str, ...], message: str)`
  - `@dataclass ExtractionResult(status: Literal["ok","failed"], data: dict | None, error: str | None, latency_ms: float, input_tokens: int | None, output_tokens: int | None, cost_usd: float | None, simulated: bool)`
  - `@dataclass(frozen=True) FieldScore(field: str, value: Any, confidence: float, reasons: tuple[str, ...])`: `value` is JSON-native.
  - `@dataclass(frozen=True) Decision(route: Literal["auto_approved","needs_review"], doc_confidence: float, reasons: tuple[str, ...])`
  - `@dataclass DocResult(doc: DocumentMeta, extractions: list[ExtractionResult], rules: list[RuleResult], scores: list[FieldScore], decision: Decision)`
- Produces (`rules.py`):
  - `@dataclass ValidationOutcome(draft: BaseModel, results: list[RuleResult])`
  - `build_draft(raw: dict | None, doc_type: DocType) -> tuple[BaseModel, list[RuleResult]]`: parses each scalar and item field with the Task 2 parser for its `FieldKind`. Money is quantized to 0.01. `id` and `text` are stripped `str`. `npwp` is kept as the raw string (format is checked by R07).
    - An unparseable value is set to `None` and emits `RuleResult("R00_parse","hard",False,(path,),msg)`.
    - Item paths look like `line_items.0.amount` / `items.1.price`.
  - `validate(raw: dict | None, doc_type: DocType, today: date) -> ValidationOutcome`: runs `build_draft`, then R01 plus the doc-type rules.
- Rule rules:
  - Emit a `RuleResult` only for rules whose inputs are all non-`None`. R01 always runs.
  - R02 is emitted once per line item, with message `"line 1: 3 x 15000.00 != 46000.00"`-style.
  - Severities, formulas, and the R11 field scope follow spec §4.5 exactly. R09 is **hard**.
  - R01 also fails when `line_items` is empty (field `line_items`). Fields of R01 = the missing field names.
  - R07: seller `seller_npwp` missing or `not is_valid_npwp(npwp_digits(...))` gives a hard fail with `fields=("seller_npwp",)`.
  - R07B: buyer NPWP present and invalid gives a soft fail.
  - Field tuples:
    - R03: `("subtotal", *all line amount paths)`
    - R04: `("tax_base",)`
    - R05: `("tax_base","tax_rate","tax_amount")`
    - R06: `("subtotal","discount","tax_amount","total")`
    - R08: `("invoice_date",)`
    - R09: `("invoice_date","due_date")`
    - R10: `("tax_rate",)`
    - R11: the negative fields
    - R20: `("total",)`
    - R21: `("subtotal", *item price paths)`
    - R22: `("subtotal","discount","service_charge","tax","total")`
    - R23: `("cash","change","total")`
  - Tolerances: 1 rupiah, except sums (R03, R21), which allow `n_items` rupiah.
  - R04 accepts `tax_base` within 1 of `net` or of `round(net*11/12)`, where `net = subtotal - discount`.
  - R22/R23: treat `None` among the optional addends (`discount`, `service_charge`, `tax`) as 0, but require `subtotal` and `total` present (R22) or `cash`, `change`, `total` present (R23).

- [ ] **Step 1: Write failing tests**

Build a helper `clean_invoice_raw()` in the test module:
- 2 items: `3 x 15000.00 = 45000.00` and `1 x 55000.00 = 55000.00`;
- `subtotal 100000.00`, `discount 0.00`, `tax_base 100000.00`, `tax_rate "0.11"`, `tax_amount 11000.00`, `total 111000.00`;
- `seller_npwp "01.234.567.8-901.000"`, `invoice_date "2026-11-05"`, `due_date "2026-12-05"`.

```python
TODAY = date(2026, 11, 5)


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
        (lambda d: d.update(due_date="2026-10-01"), "R09"),
        (lambda d: d.update(tax_rate="0.10", tax_amount="10000.00", total="110000.00"), "R10"),
        (lambda d: d.update(invoice_date="31/02/2026"), "R00_parse"),
        (lambda d: d.update(invoice_number=None), "R01"),
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


def test_r09_is_hard_and_r04_is_soft():
    raw = clean_invoice_raw()
    raw.update(due_date="2026-10-01", tax_base="95000.00", tax_amount="10450.00", total="110450.00")
    sev = {r.rule_id: r.severity for r in validate(raw, "invoice", TODAY).results if not r.passed}
    assert sev == {"R09": "hard", "R04": "soft"}


def test_unparseable_value_keeps_other_fields():
    raw = clean_invoice_raw()
    raw["total"] = "12a.000"
    out = validate(raw, "invoice", TODAY)
    assert out.draft.total is None and out.draft.subtotal == Decimal("100000.00")


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
    assert not res["R23"].passed
    assert validate({"items": []}, "receipt", TODAY).results[0].rule_id in {"R01", "R20"}


def test_receipt_negative_item_price_is_not_r11():
    raw = {"items": [{"name": "Diskon", "price": "-5000"}], "total": "0"}
    assert "R11" not in failed(validate(raw, "receipt", TODAY))
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/validation/test_rules.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement `results.py` and `rules.py`** per Interfaces.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/validation -v`
Expected: PASS.

- [ ] **Step 5: Commit**

Message: `feat: add validation rules R00-R23 with shared result types`.

---

### Task 4: Synthetic invoice data and fault injection

**Files:**
- Create: `src/docex/synthetic/__init__.py`, `src/docex/synthetic/catalog.py`, `src/docex/synthetic/generator.py` (data part only)
- Test: `tests/synthetic/test_generator_data.py`

**Interfaces:**
- Consumes: `Invoice`, `validate` (Task 3).
- Produces (`catalog.py`):
  - `PRODUCTS: tuple[tuple[str, int, int], ...]`: (description, min_price, max_price) in rupiah. At least 30 Indonesian items across ATK, logistics services, sembako, and IT services, e.g. `("Kertas HVS A4 80gsm (rim)", 45000, 65000)`.
  - `TEMPLATES = ("modern", "klasik", "minimal")`
  - `DATE_FORMATS = ("long_id", "dmy_slash", "iso", "short_en")`, which render as `05 November 2026`, `05/11/2026`, `2026-11-05`, `5 Nov 2026`.
  - `NUMBER_STYLES = ("rp_dot", "dot_comma", "idr_comma")`, which render as `Rp 1.234.567`, `1.234.567,00`, `IDR 1,234,567`.
  - `INVOICE_NUMBER_FORMATS = ("INV/{y}/{m:02d}/{n:05d}", "FK-{n:06d}", "{y}.{m:02d}.{n:04d}")`
- Produces (`generator.py`):
  - `FAULT_TYPES = ("total_mismatch","tax_mismatch","line_amount_mismatch","invalid_npwp","due_before_issue")`
  - `FAULT_RULE = {"total_mismatch":"R06","tax_mismatch":"R05","line_amount_mismatch":"R02","invalid_npwp":"R07","due_before_issue":"R09"}`
  - `@dataclass(frozen=True) InvoiceLayout(template: str, date_format: str, number_style: str)`
  - `@dataclass(frozen=True) SyntheticInvoice(doc_id: str, invoice: Invoice, layout: InvoiceLayout, tax_scheme: Literal["ppn11","dpp_nilai_lain"], faults: tuple[str, ...])`
  - `make_invoice(seed: int, index: int, faulty: bool) -> SyntheticInvoice`
    - `doc_id=f"inv-{index:04d}"`;
    - RNG `random.Random(f"{seed}:inv:{index}")`; `Faker("id_ID")` with `seed_instance(hash of the same string via zlib.crc32)`;
    - 1–8 items; quantities 1–20; prices rounded to 500;
    - `invoice_date` between 2025-01-01 and 2026-10-31; `due_date = invoice_date + 14|30|45` days, or `None` with 20% probability;
    - `discount` = 0, or 5%/10% of subtotal rounded to rupiah (30% probability);
    - tax scheme 50/50;
    - seller NPWP always present (15- or 16-digit, 50/50); buyer NPWP present with 60% probability;
    - when `faulty`, exactly one fault from `FAULT_TYPES` is chosen and applied **after** computing correct values, so the printed value is wrong;
    - `due_before_issue` forces a `due_date` 1–10 days before `invoice_date`.
    - `invalid_npwp` always prints a **14-digit** seller NPWP (one digit removed), so a mock `drop_digit` can never turn it valid.

- [ ] **Step 1: Write failing tests**

```python
TODAY = date(2026, 11, 5)


def hard_failures(si):
    out = validate(si.invoice.model_dump(mode="json"), "invoice", TODAY)
    return {r.rule_id for r in out.results if not r.passed and r.severity == "hard"}


def test_deterministic():
    assert make_invoice(42, 7, False) == make_invoice(42, 7, False)
    assert make_invoice(42, 7, False) != make_invoice(43, 7, False)


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


def test_variety():
    sis = [make_invoice(42, i, False) for i in range(200)]
    assert {s.tax_scheme for s in sis} == {"ppn11", "dpp_nilai_lain"}
    assert {s.layout.template for s in sis} == set(TEMPLATES)
    assert all(1 <= len(s.invoice.line_items) <= 8 for s in sis)
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/synthetic/test_generator_data.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `catalog.py` and `make_invoice`** per Interfaces.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/synthetic -v`
Expected: PASS.

- [ ] **Step 5: Commit**

Message: `feat: generate synthetic Indonesian invoices with fault injection`.

---

### Task 5: PDF rendering, scan degradation, dataset files

**Files:**
- Create: `src/docex/synthetic/templates.py`, `src/docex/synthetic/degrade.py`, `src/docex/imaging.py`
- Modify: `src/docex/synthetic/generator.py` (add `generate_dataset`)
- Test: `tests/synthetic/test_templates.py`, `tests/synthetic/test_dataset.py`

**Interfaces:**
- Consumes: `SyntheticInvoice`, `make_invoice` (Task 4); `GroundTruth`, `write_ground_truth`, `DocumentMeta` (Task 1); `parse_number`, `parse_date` (Task 2).
- Produces:
  - `format_amount(value: Decimal, style: str) -> str`
  - `format_date(d: date, fmt: str) -> str`: `long_id` uses Indonesian month names.
  - `render_invoice_pdf(si: SyntheticInvoice, path: Path) -> None`: ReportLab, A4, one page. Each template uses its own labels:
    - `klasik`: "FAKTUR", "Kepada Yth.", "No. Faktur", "Tanggal", "Jatuh Tempo", "DPP", "PPN", "Total".
    - `modern`/`minimal`: English or mixed labels. Show "DPP Nilai Lain" when `tax_scheme == "dpp_nilai_lain"`.
    - Prints every field of the `Invoice` using its layout's formats.
  - `render_first_page(path: Path, dpi: int = 150) -> PIL.Image.Image` (`imaging.py`): uses pypdfium2 for `.pdf` (`page.render(scale=dpi/72).to_pil()`) and PIL for images. Always returns RGB.
  - `degrade_pdf(src: Path, dst: Path, level: Literal["scan_light","scan_heavy"], rng: random.Random) -> None`
    - render at 150 dpi, then grayscale;
    - rotate by uniform ±0.7° (light) or ±1.5° (heavy) with white fill;
    - add Gaussian noise σ=6 (light) or 14 (heavy) via NumPy;
    - apply `GaussianBlur` radius 0.4 or 1.0;
    - JPEG quality 70 or 40 round-trip;
    - save as a single-page PDF via PIL `save(dst, "PDF", resolution=150)`.
  - `generate_dataset(n: int, seed: int, faulty_rate: float, scan_rate: float, data_dir: Path) -> list[DocumentMeta]`
    - For index `1..n`, RNG `random.Random(f"{seed}:dataset")` decides `faulty` (p=`faulty_rate`) and quality: `clean`, or `scan_light`/`scan_heavy` (p=`scan_rate`, split 50/50).
    - Renders to `data/documents/synthetic/<doc_id>.pdf`; degraded documents overwrite that same path, rendering to a temp file first.
    - Writes `GroundTruth(doc_id,"invoice","synthetic", invoice.model_dump(mode="json"), faults)` to `data/ground_truth/<doc_id>.json`.
    - Returns metas with relative POSIX paths.

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.parametrize("style", NUMBER_STYLES)
@pytest.mark.parametrize("value", ["0.00", "500.00", "1234567.00", "91667.00"])
def test_amount_roundtrip(style, value):
    assert parse_number(format_amount(Decimal(value), style)) == Decimal(value)


@pytest.mark.parametrize("fmt", DATE_FORMATS)
def test_date_roundtrip(fmt):
    for d in (date(2026, 11, 5), date(2025, 8, 17), date(2026, 1, 31)):
        assert parse_date(format_date(d, fmt)) == d


def test_rendered_pdf_contains_invoice_number(tmp_path):
    si = make_invoice(42, 1, False)
    render_invoice_pdf(si, tmp_path / "a.pdf")
    pdf = pypdfium2.PdfDocument(tmp_path / "a.pdf")
    assert len(pdf) == 1
    text = pdf[0].get_textpage().get_text_range()
    assert si.invoice.invoice_number in text


def test_degraded_pdf_is_image_only(tmp_path):
    render_invoice_pdf(make_invoice(42, 1, False), tmp_path / "a.pdf")
    degrade_pdf(tmp_path / "a.pdf", tmp_path / "b.pdf", "scan_heavy", random.Random(1))
    pdf = pypdfium2.PdfDocument(tmp_path / "b.pdf")
    assert pdf[0].get_textpage().get_text_range().strip() == ""
    assert render_first_page(tmp_path / "b.pdf").mode == "RGB"


def test_generate_dataset_files_and_determinism(tmp_path):
    a = generate_dataset(6, 42, 0.5, 0.5, tmp_path / "a")
    b = generate_dataset(6, 42, 0.5, 0.5, tmp_path / "b")
    assert [m.doc_id for m in a] == [f"inv-{i:04d}" for i in range(1, 7)]
    for m in a:
        assert (tmp_path / "a" / m.path).exists() and not Path(m.path).is_absolute()
        assert (tmp_path / "a" / m.gt_path).read_bytes() == (
            tmp_path / "b" / m.gt_path
        ).read_bytes()
    assert {m.quality for m in a} <= {"clean", "scan_light", "scan_heavy"}
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/synthetic -v`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement `templates.py`, `imaging.py`, `degrade.py`, `generate_dataset`** per Interfaces.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/synthetic -v`
Expected: PASS.

- [ ] **Step 5: Visual check**

Run: `uv run python -c "from pathlib import Path; from docex.synthetic.generator import generate_dataset; generate_dataset(3, 42, 0, 1, Path('data/_preview'))"`.
Then open one clean and one scanned PDF in `data/_preview/documents/synthetic/` and confirm both look like an invoice. `data/` is gitignored.

- [ ] **Step 6: Commit**

Message: `feat: render invoice PDFs in 3 templates with scan degradation`.

---

### Task 6: DuckDB storage

**Files:**
- Create: `src/docex/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: `DocumentMeta` (Task 1); `DocResult` and friends (Task 3).
- Produces: `class Store` with these members:
  - `__init__(self, db_path: Path)`: creates the parent dir and all tables from spec §4.8 (`CREATE TABLE IF NOT EXISTS`). JSON columns are `VARCHAR` holding `json.dumps(..., sort_keys=True)`.
  - `close()`, `__enter__`, `__exit__`.
  - `upsert_documents(metas: list[DocumentMeta]) -> None`: `INSERT OR REPLACE` by `doc_id`.
  - `list_documents(source: str | None = None, limit: int | None = None) -> list[DocumentMeta]`: ordered by `doc_id`.
  - `new_run_id(provider: str, now: datetime | None = None) -> str`: follows the Global Constraints format with collision suffix.
  - `create_run(provider: str, model: str, config: dict, now: datetime | None = None) -> str`
  - `finish_run(run_id: str, n_docs: int, status: str) -> None`
  - `save_doc_result(run_id: str, result: DocResult) -> None`: writes extractions (attempt numbers from 1), validations, field_scores, and decisions.
  - `latest_run_id() -> str | None`, by `started_at` descending.
  - `list_runs() -> list[dict]`: keys `run_id, provider, model, n_docs, status, started_at`.
  - `run_simulated(run_id) -> bool`
  - `get_decisions(run_id) -> list[dict]`: keys `doc_id, route, doc_confidence, reasons` (a list).
  - `get_doc_detail(run_id, doc_id) -> dict`: keys `doc` (DocumentMeta), `extractions` (list of dict), `rules` (list of `RuleResult`), `scores` (list of `FieldScore`), `decision` (`Decision`).
  - `save_review(run_id, doc_id, action: Literal["approve","correct"], corrected_data: dict | None) -> None`: one row per (run_id, doc_id); the latest write wins.
  - `get_reviews(run_id) -> dict[str, dict]`: doc_id → `{action, corrected_data, reviewed_at}`.

- [ ] **Step 1: Write failing tests**

```python
def sample_result(
    doc,
) -> DocResult:  # helper: 1 ok extraction, 1 failed rule, 2 scores, review route
    ...


def test_documents_roundtrip(tmp_path):
    with Store(tmp_path / "d.duckdb") as s:
        s.upsert_documents([META])
        s.upsert_documents([META])
        assert s.list_documents() == [META]


def test_run_ids_unique_within_same_second(tmp_path):
    now = datetime(2026, 11, 5, 9, 30, 0)
    with Store(tmp_path / "d.duckdb") as s:
        a = s.create_run("mock", "mock-v1", {}, now)
        b = s.create_run("mock", "mock-v1", {}, now)
    assert a == "20261105-093000-mock" and b == "20261105-093000-mock-2"


def test_doc_result_roundtrip(tmp_path):
    with Store(tmp_path / "d.duckdb") as s:
        s.upsert_documents([META])
        rid = s.create_run("mock", "mock-v1", {})
        s.save_doc_result(rid, sample_result(META))
        d = s.get_doc_detail(rid, META.doc_id)
        assert d["decision"].route == "needs_review" and d["rules"][0].rule_id == "R06"
        assert s.get_decisions(rid)[0]["reasons"] == list(d["decision"].reasons)


def test_review_latest_wins(tmp_path):
    with Store(tmp_path / "d.duckdb") as s:
        s.save_review("r1", "inv-0001", "approve", None)
        s.save_review("r1", "inv-0001", "correct", {"total": "1.00"})
        assert s.get_reviews("r1")["inv-0001"]["action"] == "correct"


def test_store_releases_file_after_close(tmp_path):  # Review Focus #2
    p = tmp_path / "d.duckdb"
    with Store(p) as s:
        s.upsert_documents([META])
    with Store(p) as s2:
        assert len(s2.list_documents()) == 1
    p.unlink()  # fails on Windows if a handle is still open
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_storage.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `Store`** per Interfaces (`duckdb.connect(str(db_path))`, with parameterized queries only).

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_storage.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

Message: `feat: persist documents, runs, results and reviews in DuckDB`.

---

### Task 7: Provider protocol, mock error model, registry

**Files:**
- Create: `src/docex/providers/__init__.py`, `base.py`, `mock.py`, `registry.py`
- Test: `tests/providers/test_mock.py`, `tests/providers/test_registry.py`

**Interfaces:**
- Consumes: `DocumentMeta`, `FIELD_KINDS`, `ITEM_FIELD_KINDS`, `ITEMS_KEY` (Task 1); `read_ground_truth` (Task 1); `ExtractionResult` (Task 3); `Settings` (Task 1).
- Produces (`base.py`):
  - `class ExtractionProvider(Protocol)` with attributes `name: str`, `model: str` and method `extract(self, doc: DocumentMeta, schema: type[BaseModel], attempt: int) -> ExtractionResult`.
- Produces (`mock.py`):
  - `QUALITY_MULTIPLIER = {"clean": 1.0, "scan_light": 1.5, "scan_heavy": 3.0, "photo": 2.0}`
  - `class MockProvider` with `name = "mock"`, `model = "mock-v1"`.
    - `__init__(self, data_dir: Path, seed: int = 42, base_error_rate: float = 0.03, consistency_correlation: float = 0.5, failure_rate: float = 0.01)`
    - `extract(doc, schema, attempt) -> ExtractionResult`: `simulated=True`, `cost_usd=0.0`, `input_tokens=1500`, `output_tokens=len(json.dumps(data))//4`, `latency_ms=900 + 2*output_chars + rng.uniform(0, 400)` (no sleeping).
  - `corrupt(data: dict, doc_type: DocType, p: float, rng: random.Random) -> tuple[dict, set[str]]`: returns the corrupted copy and the set of corrupted field paths.

Error model:
- **Per-field probability:** `p = base_error_rate * QUALITY_MULTIPLIER[quality]`, applied independently to every scalar field and every item field path. Each item is also dropped with probability `p` (`drop_item`, path `line_items.<i>`).
- **Field-level operators:**
  - Fields whose ground-truth value is `None` get `hallucinate` with probability `p/3` instead:
    - date → `invoice_date + 30 days`;
    - npwp → 15 random digits;
    - money → a random amount between 1000 and 100000.
  - Otherwise, pick uniformly among the operators valid for the field's kind:
    - money/quantity/rate: `digit_swap` (swap two adjacent digits that differ), `thousand_sep` (value / 1000), `drop_digit`, `null`;
    - date: `day_month_swap` (only if day ≤ 12 and day ≠ month), `year_off_by_one`, `null`;
    - id/text: `typo` (replace one alphanumeric char), `truncate` (drop the last 30%, keeping at least 1 char), `null`;
    - npwp: `digit_swap`, `drop_digit`.
- **Attempts:**
  - Attempt 1 uses RNG `random.Random(f"{seed}:{doc_id}:1")`.
  - Attempt `k > 1`: first recompute attempt 1. For each path corrupted in attempt 1, use RNG `random.Random(f"{seed}:{doc_id}:corr:{k}")` to copy attempt 1's value with probability `consistency_correlation`. Every other path is corrupted independently with RNG `f"{seed}:{doc_id}:{k}"`.
  - Item drops are decided on attempt 1 only and reused.
- **Failure:** decided first with RNG `f"{seed}:{doc_id}:{attempt}:fail"`. With probability `failure_rate` the result is `status="failed"`, `data=None`, `error="simulated provider failure"`.
- **Missing ground-truth file:** gives `status="failed"` with `error` naming the path, without raising.

Produces (`registry.py`):
- `PROVIDERS: dict[str, Callable[[Settings], ExtractionProvider]] = {"mock": lambda s: MockProvider(s.data_dir, s.seed, s.mock_base_error_rate, s.mock_consistency_correlation, s.mock_failure_rate)}`
- `get_provider(name: str, settings: Settings) -> ExtractionProvider`: raises `ValueError("Unknown provider 'x'. Available: mock")`.

- [ ] **Step 1: Write failing tests**

Fixture `invoice_doc(tmp_path, quality)`: writes `make_invoice(42, 1, False)` ground truth and returns its `DocumentMeta`.

```python
def test_zero_error_returns_ground_truth(tmp_path):
    doc = invoice_doc(tmp_path, "clean")
    r = MockProvider(tmp_path, base_error_rate=0, failure_rate=0).extract(doc, Invoice, 1)
    assert (
        r.status == "ok"
        and r.simulated
        and r.data == read_ground_truth(tmp_path / doc.gt_path).data
    )


def test_deterministic(tmp_path):
    doc = invoice_doc(tmp_path, "scan_heavy")
    m = MockProvider(tmp_path, base_error_rate=0.3)
    assert m.extract(doc, Invoice, 1).data == m.extract(doc, Invoice, 1).data


def test_error_rate_scales_with_quality():
    rng = random.Random(0)
    gt = make_invoice(42, 1, False).invoice.model_dump(mode="json")
    clean = sum(len(corrupt(gt, "invoice", 0.03 * 1.0, rng)[1]) for _ in range(400))
    heavy = sum(len(corrupt(gt, "invoice", 0.03 * 3.0, rng)[1]) for _ in range(400))
    assert heavy > 2 * clean > 0


def test_correlation_one_repeats_errors(tmp_path):
    doc = invoice_doc(tmp_path, "scan_heavy")
    m = MockProvider(tmp_path, base_error_rate=0.3, consistency_correlation=1.0, failure_rate=0)
    a1, a2 = m.extract(doc, Invoice, 1).data, m.extract(doc, Invoice, 2).data
    gt = read_ground_truth(tmp_path / doc.gt_path).data
    for k, v in a1.items():
        if k != "line_items" and v != gt.get(k):
            assert a2[k] == v


def test_correlation_zero_differs_somewhere(tmp_path):
    docs = [invoice_doc_n(tmp_path, i, "scan_heavy") for i in range(1, 11)]
    m = MockProvider(tmp_path, base_error_rate=0.3, consistency_correlation=0.0, failure_rate=0)
    assert any(m.extract(d, Invoice, 1).data != m.extract(d, Invoice, 2).data for d in docs)


def test_failure_and_missing_gt(tmp_path):
    doc = invoice_doc(tmp_path, "clean")
    assert MockProvider(tmp_path, failure_rate=1.0).extract(doc, Invoice, 1).status == "failed"
    (tmp_path / doc.gt_path).unlink()
    r = MockProvider(tmp_path, failure_rate=0).extract(doc, Invoice, 1)
    assert r.status == "failed" and doc.gt_path.split("/")[-1] in r.error


def test_registry(tmp_path):
    assert get_provider("mock", Settings(data_dir=tmp_path)).name == "mock"
    with pytest.raises(ValueError, match="Available: mock"):
        get_provider("ollama", Settings(data_dir=tmp_path))
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/providers -v`
Expected: FAIL.

- [ ] **Step 3: Implement `base.py`, `mock.py`, `registry.py`** per Interfaces and error model.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/providers -v`
Expected: PASS.

- [ ] **Step 5: Commit**

Message: `feat: add provider protocol and mock extractor with LLM-like error model`.

---

### Task 8: Confidence scoring and routing

**Files:**
- Create: `src/docex/scoring.py`, `src/docex/routing.py`
- Test: `tests/test_scoring.py`, `tests/test_routing.py`

**Interfaces:**
- Consumes: `ValidationOutcome`, `build_draft` (Task 3); `RuleResult`, `FieldScore`, `Decision` (Task 3); `REQUIRED_FIELDS`, `CRITICAL_FIELDS`, `FIELD_KINDS`, `ITEM_FIELD_KINDS`, `ITEMS_KEY` (Task 1).
- Produces (`scoring.py`):
  - `FORMAT_RULES = frozenset({"R00_parse", "R07", "R07B"})`
  - `score_fields(doc_type: DocType, primary: ValidationOutcome, other_drafts: list[BaseModel]) -> list[FieldScore]`
    - Scores every scalar field in `FIELD_KINDS[doc_type]` plus every item field path of the primary draft. `value` comes from `primary.draft` serialized JSON-native.
    - Start at 1.0, then for each failed rule touching the field apply exactly one multiplier:
      - `R01` sets the field to 0.0 (`reason "missing required"`);
      - `FORMAT_RULES` ×0.3 (`"invalid format (R07)"`);
      - other hard rules ×0.5 (`"R06 failed"`);
      - soft rules ×0.8.
    - For each draft in `other_drafts` whose value at that path differs from primary, apply ×0.4 once (`"attempts disagree"`).
    - Round to 4 decimals.
  - `doc_confidence(doc_type: DocType, scores: list[FieldScore]) -> float`
    - Minimum over `CRITICAL_FIELDS[doc_type]`, where receipt `subtotal` counts only if its value is not `None`.
    - Returns 0.0 if no critical field is scored.
- Produces (`routing.py`):
  - `route(failed_extraction: str | None, rules: list[RuleResult], scores: list[FieldScore], doc_conf: float, threshold: float, doc_type: DocType) -> Decision`
    - `needs_review` if `failed_extraction` is not None, any hard rule failed, or `doc_conf < threshold`.
    - Reasons, in order:
      - `"extraction failed: <msg>"`;
      - `"<rule_id> failed: <message>"` per failed hard rule;
      - `"low confidence: <field>=<conf:.2f>"` for each critical field below threshold.

- [ ] **Step 1: Write failing tests**

```python
def test_clean_doc_scores_one():
    out = validate(clean_invoice_raw(), "invoice", TODAY)
    scores = score_fields("invoice", out, [out.draft])
    assert all(s.confidence == 1.0 for s in scores) and doc_confidence("invoice", scores) == 1.0


def test_hard_rule_halves_involved_fields():
    raw = clean_invoice_raw()
    raw["total"] = "999.00"
    s = {x.field: x for x in score_fields("invoice", validate(raw, "invoice", TODAY), [])}
    assert s["total"].confidence == 0.5 and s["subtotal"].confidence == 0.5
    assert s["seller_name"].confidence == 1.0 and "R06 failed" in s["total"].reasons


def test_invalid_npwp_is_format_penalty_only():
    raw = clean_invoice_raw()
    raw["seller_npwp"] = "123"
    s = {x.field: x for x in score_fields("invoice", validate(raw, "invoice", TODAY), [])}
    assert s["seller_npwp"].confidence == 0.3


def test_disagreement_penalty():
    a = validate(clean_invoice_raw(), "invoice", TODAY)
    raw_b = clean_invoice_raw()
    raw_b["seller_name"] = "PT Lain"
    b = validate(raw_b, "invoice", TODAY)
    s = {x.field: x for x in score_fields("invoice", a, [b.draft])}
    assert s["seller_name"].confidence == 0.4 and doc_confidence("invoice", list(s.values())) == 0.4


def test_missing_required_is_zero():
    raw = clean_invoice_raw()
    raw["invoice_number"] = None
    s = {x.field: x for x in score_fields("invoice", validate(raw, "invoice", TODAY), [])}
    assert s["invoice_number"].confidence == 0.0


def test_receipt_subtotal_ignored_when_absent():
    out = validate({"items": [], "total": "5000"}, "receipt", TODAY)
    assert doc_confidence("receipt", score_fields("receipt", out, [])) == 1.0


# tests/test_routing.py
def test_route_auto_and_reasons():
    ok = route(None, [], [], 0.9, 0.7, "invoice")
    assert ok.route == "auto_approved" and ok.reasons == ()
    hard = RuleResult("R06", "hard", False, ("total",), "total mismatch")
    low = FieldScore("seller_npwp", "1", 0.4, ())
    d = route(None, [hard], [low], 0.4, 0.7, "invoice")
    assert d.route == "needs_review"
    assert d.reasons == ("R06 failed: total mismatch", "low confidence: seller_npwp=0.40")
    assert route("boom", [], [], 1.0, 0.7, "invoice").reasons[0] == "extraction failed: boom"
```

Move `clean_invoice_raw` and `TODAY` into `tests/conftest.py` (or a `tests/helpers.py` imported by both test modules) so Tasks 3 and 8 share it.

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_scoring.py tests/test_routing.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `scoring.py` and `routing.py`** per Interfaces.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

Message: `feat: score field confidence and route documents to review`.

---

### Task 9: Pipeline and CLI (`generate`, `run`)

**Files:**
- Create: `src/docex/pipeline.py`, `src/docex/cli.py`
- Test: `tests/test_pipeline.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above. `get_provider` (Task 7), `Store` (Task 6), `validate` (Task 3), `score_fields`, `doc_confidence`, `route` (Task 8), `generate_dataset` (Task 5), `Settings` (Task 1).
- Produces (`pipeline.py`):
  - `@dataclass RunSummary(run_id: str, n_docs: int, n_auto: int, n_review: int, n_failed: int, simulated: bool)`
  - `process_document(doc: DocumentMeta, provider: ExtractionProvider, settings: Settings, today: date) -> DocResult`
    - Runs `settings.consistency_runs` attempts.
    - The primary attempt is attempt 1. If attempt 1 failed, the result is a failed decision with an empty rules/scores list.
    - Other drafts come from `ok` attempts ≥ 2.
    - Any exception becomes a failed `DocResult`, with `ExtractionResult(status="failed", error=f"{type(e).__name__}: {e}", …, simulated=True)`, and routes to `needs_review`.
  - `run_pipeline(store: Store, provider: ExtractionProvider, docs: list[DocumentMeta], settings: Settings, today: date | None = None) -> RunSummary`
    - Run config stored = `settings.model_dump(mode="json")`.
    - `today` defaults to `date.today()`.
- Produces (`cli.py`):
  - `app = typer.Typer(no_args_is_help=True)`; every command builds `Settings()` and opens `Store(settings.resolved_db_path)`.
  - `generate(n: int = 100, seed: int | None = None, faulty_rate: float = 0.15, scan_rate: float = 0.3)`: calls `generate_dataset` and `upsert_documents`, then prints the count.
  - `run(provider: str | None = None, source: str = "all", limit: int | None = None)`
    - If no documents: prints `"No documents found. Run `docex generate` first."` and exits 1.
    - Otherwise prints a Rich table of the summary. When `simulated`, it adds the line `"Results come from a simulated extractor (mock provider)."`, then prints `run_id`.

- [ ] **Step 1: Write failing tests**

```python
def test_pipeline_end_to_end(tmp_path):
    s = Settings(data_dir=tmp_path, mock_base_error_rate=0.2)
    docs = generate_dataset(10, 42, 0.3, 0.3, tmp_path)
    with Store(s.resolved_db_path) as st:
        st.upsert_documents(docs)
        summary = run_pipeline(st, get_provider("mock", s), docs, s, date(2026, 11, 5))
        assert summary.n_docs == 10 and summary.n_auto + summary.n_review == 10
        assert summary.simulated and len(st.get_decisions(summary.run_id)) == 10


def test_perfect_extractor_routes_exactly_the_faulty_docs(tmp_path):
    s = Settings(data_dir=tmp_path, mock_base_error_rate=0.0, mock_failure_rate=0.0)
    docs = generate_dataset(20, 42, 0.3, 0.3, tmp_path)
    with Store(s.resolved_db_path) as st:
        st.upsert_documents(docs)
        rid = run_pipeline(st, get_provider("mock", s), docs, s, date(2026, 11, 5)).run_id
        routes = {d["doc_id"]: d["route"] for d in st.get_decisions(rid)}
    assert any(d.injected_faults for d in docs)
    assert routes == {
        d.doc_id: ("needs_review" if d.injected_faults else "auto_approved") for d in docs
    }


def test_exception_in_one_doc_does_not_stop_run(tmp_path, monkeypatch):
    ...
    # monkeypatch provider.extract to raise for doc #2 -> that doc failed+needs_review, others processed


# tests/test_cli.py (CliRunner, env DOCEX_DATA_DIR=tmp_path)
def test_generate_twice_is_idempotent(tmp_path, monkeypatch):  # Review Focus #1
    runner.invoke(app, ["generate", "--n", "5"])
    runner.invoke(app, ["generate", "--n", "5"])
    with Store(tmp_path / "docex.duckdb") as st:
        assert len(st.list_documents()) == 5


def test_run_without_documents_exits_1(tmp_path, monkeypatch):  # Review Focus #4
    r = runner.invoke(app, ["run"])
    assert r.exit_code == 1 and "docex generate" in r.output


def test_run_prints_run_id_and_simulated_notice(tmp_path, monkeypatch):
    runner.invoke(app, ["generate", "--n", "4"])
    r = runner.invoke(app, ["run"])
    assert r.exit_code == 0 and "-mock" in r.output and "simulated extractor" in r.output
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_pipeline.py tests/test_cli.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `pipeline.py` and `cli.py`** (`generate`, `run`) per Interfaces.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -v`
Expected: all PASS. Then run `uv run docex generate --n 20` and `uv run docex run` by hand. Expected: a summary table and a run_id.

- [ ] **Step 5: Commit**

Message: `feat: orchestrate extraction runs with generate and run CLI commands`.

---

### Task 10: Evaluation, report, CLI (`eval`, `demo`)

**Files:**
- Create: `src/docex/evaluation/__init__.py`, `matching.py`, `metrics.py`, `report.py`
- Modify: `src/docex/cli.py` (add `eval`, `demo`)
- Test: `tests/evaluation/test_matching.py`, `tests/evaluation/test_metrics.py`, `tests/evaluation/test_report.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `Store` (Task 6), `read_ground_truth` (Task 1), the normalize functions (Task 2), the kind maps (Task 1).
- Produces (`matching.py`):
  - `field_match(kind: FieldKind, pred: Any, gt: Any) -> bool`
    - `None`/`None` counts as `True`. Parse failures count as `False`.
    - money/quantity/rate: |Δ| ≤ 1 (rate: |Δ| ≤ 0.001).
    - date: equal.
    - id: `normalize_text` equal.
    - npwp: digits equal.
    - text: `rapidfuzz.fuzz.ratio(normalize_text(p), normalize_text(g)) >= 90`.
  - `match_items(doc_type: DocType, pred: list[dict], gt: list[dict]) -> tuple[int, int, int]` returns (tp, fp, fn).
    - Greedy: for each gt item in order, pick the unmatched pred item with the highest name/description ratio among those with ratio ≥ 60.
    - The pair is a TP iff every item field matches. `fp = len(pred) - tp`, `fn = len(gt) - tp`.
- Produces (`metrics.py`):
  - `@dataclass DocRecord(doc_id, source, quality, template, faults: tuple[str, ...], route, doc_confidence: float, failed: bool, hard_failed: bool, field_correct: dict[str, bool], critical_correct: bool, field_conf: dict[str, float], items_tp: int, items_fp: int, items_fn: int)`
    - `field_correct` covers the scalar fields present in the GT data, excluding those listed in `gt_issues`.
    - `critical_correct` = all critical fields in `field_correct` are True, and `failed` is False.
  - `build_records(store: Store, run_id: str, data_dir: Path) -> list[DocRecord]`: prediction = attempt 1 data (empty dict if failed).
  - `@dataclass EvalResult(run_id: str, simulated: bool, n_docs: int, field_accuracy: dict[str, float], doc_accuracy: float, item_precision: float, item_recall: float, item_f1: float, automation_rate: float, auto_approved_accuracy: float | None, error_catch_rate: float | None, fault_catch_rate: float | None, fault_catch_by_type: dict[str, float], breakdown: dict[str, dict[str, dict[str, float]]], tradeoff: list[dict], calibration: list[dict])`
    - `breakdown` keys are `"quality"`, `"source"`, `"template"`, each mapping group → {`n`, `automation_rate`, `doc_accuracy`}.
    - `tradeoff` has rows `{threshold, automation_rate, auto_approved_accuracy}` for thresholds `[round(0.05 * k, 2) for k in range(1, 20)]`. A document is auto iff `not failed and not hard_failed and doc_confidence >= t`.
    - `calibration` covers critical fields, using bins `[0,0.1) … [0.9,1.0]` with rows `{bin_low, bin_high, n, mean_confidence, accuracy}`. Empty bins are skipped.
    - Rates with an empty denominator are `None`.
  - `evaluate(records: list[DocRecord], run_id: str, simulated: bool) -> EvalResult`
- Produces (`report.py`):
  - `write_report(result: EvalResult, out_dir: Path) -> Path`, returning the path to `report.md`.
  - Writes `metrics.json` (`dataclasses.asdict`), `field_accuracy.png`, `accuracy_by_quality.png`, `threshold_tradeoff.png`, `calibration.png` (Matplotlib `Agg`, styled per the `dataviz` skill).
  - `report.md` has, in order:
    - a title;
    - a bold "Simulated extractor" banner when `simulated`;
    - a headline table (automation rate, auto-approved accuracy, error catch rate, fault catch rate, doc accuracy, item F1);
    - per-field accuracy;
    - fault catch by type;
    - breakdowns;
    - the four images.
- Produces (`cli.py`):
  - `eval(run: str | None = None)`
    - Defaults to `latest_run_id()`. With no runs: prints `"No runs found. Run `docex run` first."` and exits 1.
    - Otherwise writes to `settings.reports_dir / run_id` and prints the headline metrics and the report path.
  - `demo(n: int = 40)`: generates if there are no synthetic documents, then `run` over all documents, then `eval`, then prints the summary.

- [ ] **Step 1: Load the `dataviz` skill** before touching chart code.

- [ ] **Step 2: Write failing tests**

```python
# matching
def test_field_match_rules():
    assert field_match("money", "1234567.00", "1.234.567")
    assert not field_match("money", "1234.567", "1234567.00")
    assert field_match("text", "PT Maju Jaya Tbk", "PT. Maju Jaya Tbk")
    assert not field_match("id", "INV/2026/11/00123", "INV/2026/11/00132")
    assert field_match("npwp", "01.234.567.8-901.000", "012345678901000")
    assert field_match("date", None, None) and not field_match("date", "2026-11-05", None)


def test_match_items_counts():
    gt = [
        {
            "description": "Kertas A4",
            "quantity": "2",
            "unit_price": "50000.00",
            "amount": "100000.00",
        },
        {"description": "Tinta", "quantity": "1", "unit_price": "75000.00", "amount": "75000.00"},
    ]
    pred = [gt[0], {**gt[1], "amount": "7500.00"}]
    assert match_items("invoice", pred, gt) == (1, 1, 1)


# metrics: hand-built records
def test_routing_metrics():
    recs = [
        rec("a", route="auto_approved", conf=0.9, correct=True),
        rec("b", route="auto_approved", conf=0.8, correct=False),
        rec(
            "c",
            route="needs_review",
            conf=0.3,
            correct=False,
            faults=("total_mismatch",),
            hard_failed=True,
        ),
        rec("d", route="needs_review", conf=0.5, correct=True),
    ]
    r = evaluate(recs, "r1", True)
    assert r.automation_rate == 0.5 and r.auto_approved_accuracy == 0.5
    assert r.error_catch_rate == 0.5 and r.fault_catch_rate == 1.0
    t = {row["threshold"]: row for row in r.tradeoff}
    assert t[0.85]["automation_rate"] == 0.25 and t[0.85]["auto_approved_accuracy"] == 1.0


def test_empty_denominators_are_none():
    r = evaluate([rec("a", route="needs_review", conf=0.1, correct=True)], "r1", True)
    assert r.auto_approved_accuracy is None and r.fault_catch_rate is None


# report + CLI
def test_report_files(tmp_path):
    path = write_report(evaluate([...], "r1", True), tmp_path)
    for f in (
        "report.md",
        "metrics.json",
        "field_accuracy.png",
        "accuracy_by_quality.png",
        "threshold_tradeoff.png",
        "calibration.png",
    ):
        assert (tmp_path / f).exists()
    assert "Simulated extractor" in path.read_text(encoding="utf-8")


def test_eval_without_runs_exits_1(tmp_path, monkeypatch):  # Review Focus #4
    r = runner.invoke(app, ["eval"])
    assert r.exit_code == 1 and "docex run" in r.output


def test_demo_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCEX_REPORTS_DIR", str(tmp_path / "reports"))
    r = runner.invoke(app, ["demo", "--n", "8"])
    assert r.exit_code == 0 and list((tmp_path / "reports").glob("*/report.md"))
```

- [ ] **Step 3: Run to verify fail**

Run: `uv run pytest tests/evaluation tests/test_cli.py -v`
Expected: the new tests FAIL.

- [ ] **Step 4: Implement `matching.py`, `metrics.py`, `report.py`, and the `eval`/`demo` commands.**

- [ ] **Step 5: Run to verify pass, and check the timing budget**

Run: `uv run pytest -v`
Expected: all PASS.

Then run `Measure-Command { uv run docex demo }` in a fresh temp data dir (`$env:DOCEX_DATA_DIR`). Expected: under 3 minutes (spec success criterion 1). Open `reports/<run_id>/report.md` and the PNGs and check them visually.

- [ ] **Step 6: Commit**

Message: `feat: evaluate runs with routing metrics, calibration and threshold report`.

---

### Task 11: CORD receipts loader and `fetch-cord`

**Files:**
- Create: `src/docex/datasets/__init__.py`, `src/docex/datasets/cord.py`
- Modify: `src/docex/cli.py` (add `fetch-cord`)
- Test: `tests/datasets/test_cord.py`

**Interfaces:**
- Consumes: `GroundTruth`, `write_ground_truth`, `DocumentMeta`, `Receipt` (Task 1); `parse_number` (Task 2); `Store.upsert_documents` (Task 6).
- Produces:
  - `CORD_REPO = "naver-clova-ix/cord-v2"`
  - `normalize_cord_gt(gt_parse: dict) -> tuple[dict, list[str]]` returns a Receipt JSON dict and a list of issues. Mapping:
    - `menu` (a dict or a list of dicts): `nm` → `name`, `cnt` → `quantity`, `price` → `price`;
    - `sub_total`: `subtotal_price` → `subtotal`, `discount_price` → `discount` (absolute value), `service_price` → `service_charge`, `tax_price` → `tax`;
    - `total`: `total_price` → `total`, `cashprice` → `cash`, `changeprice` → `change`;
    - any value given as a list takes its first element and records issue `"<field>: multiple values"`;
    - a value `parse_number` rejects becomes `None` with issue `"<field>: unparseable '<raw>'"`.
    - The result must validate as `ReceiptDraft`.
  - `download_cord_test_split() -> Path`: `huggingface_hub.list_repo_files(CORD_REPO, repo_type="dataset")`, then the first file starting with `data/test-` and ending in `.parquet`, then `hf_hub_download(...)`.
  - `load_cord_rows(parquet: Path, n: int) -> list[tuple[bytes, dict]]`: DuckDB `SELECT image.bytes, ground_truth FROM read_parquet(?) LIMIT ?`; `ground_truth` is JSON-decoded and its `gt_parse` returned.
  - `materialize_cord(rows: list[tuple[bytes, dict]], data_dir: Path) -> list[DocumentMeta]`
    - Writes `data/documents/cord/cord-0001.png` (re-encoded as PNG via PIL) and the ground truth with `gt_issues`.
    - Metas use `doc_type="receipt"`, `source="cord"`, `quality="photo"`, `template=None`, `injected_faults=()`.
  - CLI `fetch-cord(n: int = 50)`: download, load, materialize, upsert, print the count plus a CC-BY-4.0 attribution line. Any exception from download/load gives the message `"Could not download CORD (<error>). Check your internet connection and retry; the synthetic dataset still works."` and exit 1.
- Also confirm `MockProvider`, `validate`, `score_fields`, and `build_records` handle `doc_type="receipt"`. Covered by the integration test below.

- [ ] **Step 1: Write failing tests**

Fixture `cord_parquet(tmp_path)`: build 2 rows with DuckDB, e.g. `COPY (SELECT {'bytes': ?::BLOB, 'path': 'a.png'} AS image, ? AS ground_truth UNION ALL …) TO '<p>' (FORMAT parquet)`.
- Images are tiny PIL PNGs.
- Ground truth for row 1 has `menu` as a list with `price "60.000"`, `cnt "2"`, plus `sub_total.discount_price "-5,000"`.
- Row 2 has `menu` as a dict and `total.total_price ["10.000", "10.000"]`.

```python
def test_normalize_cord_gt():
    data, issues = normalize_cord_gt(
        {
            "menu": {"nm": "Es Teh", "cnt": "2", "price": "10.000"},
            "total": {"total_price": ["10.000", "10.000"]},
        }
    )
    assert data["items"][0] == {"name": "Es Teh", "quantity": "2", "price": "10000.00"}
    assert data["total"] == "10000.00" and issues == ["total: multiple values"]


def test_unparseable_value_is_issue():
    data, issues = normalize_cord_gt({"menu": [], "total": {"total_price": "abc"}})
    assert data["total"] is None and issues == ["total: unparseable 'abc'"]


def test_discount_is_absolute():
    data, _ = normalize_cord_gt({"menu": [], "sub_total": {"discount_price": "-5,000"}})
    assert data["discount"] == "5000.00"


def test_materialize_and_run(tmp_path, cord_parquet):
    metas = materialize_cord(load_cord_rows(cord_parquet, 2), tmp_path)
    assert [m.doc_id for m in metas] == ["cord-0001", "cord-0002"]
    s = Settings(data_dir=tmp_path)
    with Store(s.resolved_db_path) as st:
        st.upsert_documents(metas)
        summary = run_pipeline(st, get_provider("mock", s), metas, s, date(2026, 11, 5))
        assert summary.n_docs == 2
        assert len(build_records(st, summary.run_id, tmp_path)) == 2


def test_fetch_cord_offline_message(tmp_path, monkeypatch):
    monkeypatch.setattr(
        cord, "download_cord_test_split", lambda: (_ for _ in ()).throw(OSError("offline"))
    )
    r = runner.invoke(app, ["fetch-cord", "--n", "2"])
    assert r.exit_code == 1 and "synthetic dataset still works" in r.output
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/datasets -v`
Expected: FAIL.

- [ ] **Step 3: Implement `cord.py` and the `fetch-cord` command.**

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -v`
Expected: all PASS.

- [ ] **Step 5: Real download check (network)**

Run: `uv run docex fetch-cord --n 50`, then `uv run docex run --source cord`, then `uv run docex eval`.
Expected: 50 receipts are registered, and the report shows a `source: cord` breakdown. If the network blocks it, record that in the task notes and continue (the tests cover the logic).

- [ ] **Step 6: Commit**

Message: `feat: load CORD receipts as real-world documents`.

---

### Task 12: Review UI, review logic, `review` and `export-labels`

**Files:**
- Create: `src/docex/review_logic.py`, `src/docex/review_app.py`
- Modify: `src/docex/cli.py` (add `review`, `export-labels`)
- Test: `tests/test_review_logic.py`, `tests/test_review_app.py`

**Interfaces:**
- Consumes: `Store` (Task 6), `SCHEMAS`, `FIELD_KINDS`, `ITEMS_KEY`, `ITEM_FIELD_KINDS` (Task 1), `render_first_page` (Task 5), `Settings` (Task 1).
- Produces (`review_logic.py`):
  - `form_values(doc_type: DocType, data: dict | None) -> tuple[dict[str, str], list[dict[str, str]]]`: turns extraction data into a scalar-field dict and an item rows list, every value a `str` (`""` for `None`).
  - `build_corrected(doc_type: DocType, scalars: dict[str, str], items: list[dict[str, str]]) -> tuple[dict | None, list[str]]`
    - `""` becomes `None`.
    - Strings are parsed with the Task 2 parser for each kind.
    - The result is validated against the strict `SCHEMAS[doc_type]`.
    - Returns `(model_dump(mode="json"), [])` on success, or `(None, ["<loc>: <msg>", ...])` on error.
  - `export_labels(store: Store, run_id: str, data_dir: Path) -> list[Path]`: for every review with `action == "correct"`, writes the `GroundTruth` to `data/labels/<doc_id>.json`, keeping `source` and `doc_type` from the document.
- Produces (`review_app.py`): a Streamlit script implementing spec §4.11.
  - Opens `Store(Settings().resolved_db_path)` inside a `with` for every read and write, so no connection is held between reruns.
  - Uses `st.text_input` for every scalar field (no `number_input`).
  - Uses `st.data_editor` for items.
  - A confidence badge shows next to each field label, with reasons in `st.caption`.
  - Buttons: "Approve" and "Save corrections". Save calls `build_corrected`, and on errors calls `st.error` and does not save.
  - If there are no runs: `st.info("No runs yet. Run `docex run` first.")`.
- Produces (`cli.py`):
  - `review()`: `subprocess.run([sys.executable, "-m", "streamlit", "run", str(Path(review_app.__file__)), "--server.headless", "false"], env=os.environ | {...})`.
  - `export-labels(run: str | None = None)`: prints the number of labels written.

- [ ] **Step 1: Write failing tests**

```python
def test_build_corrected_keeps_exact_decimals():  # Review Focus #5
    scalars, items = form_values("invoice", clean_invoice_raw())
    scalars["total"] = "Rp 1.234.567,00"
    data, errors = build_corrected("invoice", scalars, items)
    # (total no longer matches arithmetic: rules are not this function's job)
    assert errors == [] and data["total"] == "1234567.00"


def test_build_corrected_reports_errors():
    scalars, items = form_values("invoice", clean_invoice_raw())
    scalars["invoice_date"] = "31/02/2026"
    scalars["seller_name"] = ""
    data, errors = build_corrected("invoice", scalars, items)
    assert (
        data is None
        and any("invoice_date" in e for e in errors)
        and any("seller_name" in e for e in errors)
    )


def test_export_labels(tmp_path):
    # store with one doc + review action=correct -> data/labels/<doc_id>.json equals corrected_data
    ...


def test_review_app_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCEX_DATA_DIR", str(tmp_path))
    runner.invoke(app, ["generate", "--n", "3"])
    runner.invoke(app, ["run"])
    at = AppTest.from_file(str(Path(review_app.__file__)), default_timeout=60).run()
    assert not at.exception and at.button  # Approve / Save rendered


def test_review_app_without_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCEX_DATA_DIR", str(tmp_path))
    at = AppTest.from_file(str(Path(review_app.__file__)), default_timeout=60).run()
    assert not at.exception and "No runs yet" in at.info[0].value
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_review_logic.py tests/test_review_app.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `review_logic.py`, `review_app.py`, and the CLI commands.**

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -v`
Expected: all PASS.

- [ ] **Step 5: Manual UI check**

Run `uv run docex review` (or start it via the browser preview). Then:
- open a `needs_review` document;
- confirm the page image and flagged fields show;
- correct one field and save;
- confirm the queue advances;
- run `uv run docex export-labels` and confirm one file is written.

- [ ] **Step 6: Commit**

Message: `feat: add Streamlit review queue with corrections and label export`.

---

### Task 13: README, CI, example report

**Files:**
- Create: `README.md`, `.github/workflows/ci.yml`, `docs/example-report/` (copied from a `docex demo` run with seed 42)
- Test: CI config verified locally by running the same commands

**Interfaces:**
- Consumes: the CLI (Tasks 9–12) and the report output (Task 10).

- [ ] **Step 1: Write `.github/workflows/ci.yml`**

On `push` and `pull_request`, job `test` on `ubuntu-latest`:
- `actions/checkout@v4`;
- `astral-sh/setup-uv@v6` with `python-version: "3.11"`;
- `uv sync --locked`;
- `uv run ruff check`;
- `uv run ruff format --check`;
- `uv run pytest -q`.

- [ ] **Step 2: Produce the example report**

Run `uv run docex demo` with a fresh `DOCEX_DATA_DIR`. Copy `reports/<run_id>/` to `docs/example-report/`, and rewrite the image links in the copied `report.md` if needed so they stay relative.

- [ ] **Step 3: Write `README.md` (English)**

Sections, in order:
1. Title + one-line pitch + CI badge (`ExHansen/llm-doc-exctractor`).
2. **Why:** from data QC to AI engineering — extraction is easy, *trust* is the hard part.
3. **What it does:** the stage list.
4. **Architecture:** a Mermaid flowchart mirroring spec §2.
5. **Quickstart:** `uv sync`, `uv run docex demo`, `uv run docex review`, optional `uv run docex fetch-cord`.
6. **Results:** the headline table and two images from `docs/example-report/`, under a bold note that phase-1 numbers come from a **simulated extractor** and measure the QC pipeline, not a model.
7. **Design decisions:**
   - draft vs strict schemas;
   - hard vs soft rules;
   - confidence formula;
   - self-consistency;
   - ground truth = printed values;
   - why routing never sees ground truth.
8. **Validation rules** table (R00–R23).
9. **Adding a provider:** implement `ExtractionProvider.extract`, register in `PROVIDERS`, select with `--provider`/`DOCEX_PROVIDER`. Include a 15-line skeleton.
10. **Data:** synthetic generator details (Indonesian formats, PPN 11% vs DPP Nilai Lain); CORD attribution (CC-BY-4.0, Park et al., 2019, link to `naver-clova-ix/cord-v2`).
11. **Limitations.**
12. **Roadmap:** spec §9.
13. **License.**

- [ ] **Step 4: Run the full local verification**

Run: `uv sync --locked; uv run ruff check; uv run ruff format --check; uv run pytest -q`
Expected: no errors and every test passing.

- [ ] **Step 5: Commit**

Message: `docs: add README, CI workflow and example report`.

---

## Self-Review Notes

- **Spec coverage:**

  | Spec section | Task(s) |
  |---|---|
  | §3 | 1 |
  | §4.1 | 4, 5 |
  | §4.2 | 11 |
  | §4.3 | 7 |
  | §4.4 | 2 |
  | §4.5 | 3 |
  | §4.6 | 8 |
  | §4.7 | 8 |
  | §4.8 | 6 |
  | §4.9 | 9 |
  | §4.10 | 10 |
  | §4.11 | 12 |
  | §4.12 | 1 |
  | §4.13 | 9–12 |
  | §5 | 7, 9, 10, 11, 12 |
  | §6 | every task + 13 |
  | §7 | the File Map |
  | Success criteria 1–5 | 10 (timing), 13 (CI), 12 (UI), 10 (report), 13 (README) |

- **Spec amendments** made while planning, already applied to the spec:
  - R09 is hard;
  - R11 receipt scope;
  - receipt critical fields don't use ground truth;
  - fault catch rate by type;
  - helper modules `results.py`, `groundtruth.py`, `imaging.py`, `review_logic.py`.
