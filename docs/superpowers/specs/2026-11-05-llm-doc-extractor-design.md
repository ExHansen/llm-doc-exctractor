# llm-doc-extractor — Desain (Fase 1: mode offline/mock)

- **Tanggal:** 2026-11-05
- **Status:** Menunggu review
- **Tujuan proyek:** Proyek portofolio untuk CV Data/AI Engineer, yang menjembatani pengalaman Data Quality Control ke AI Engineering.

---

## 1. Ringkasan

`llm-doc-extractor` adalah pipeline yang mengubah dokumen tak terstruktur (PDF faktur Indonesia dan foto struk belanja) menjadi data terstruktur. Hasilnya **divalidasi**, **diberi skor confidence**, lalu **dirutekan**: lolos otomatis atau masuk antrean *human review*. Setelah itu kualitasnya **diukur** terhadap jawaban benar (*ground truth*).

Fase 1 berjalan **100% offline** tanpa LLM sungguhan. Ekstraksi memakai provider `mock` yang meniru kesalahan khas LLM/OCR secara deterministik (dengan *seed*). Fokus fase ini adalah semua yang ada di sekitar model: data, validasi, confidence, routing, review, dan evaluasi. LLM sungguhan (lokal maupun cloud) ditambahkan di fase berikutnya lewat antarmuka provider yang sudah disiapkan.

### Yang disampaikan pengguna
- Ingin proyek "ekstraksi dokumen dengan LLM + validasi" untuk CV Data/AI Engineer, di folder baru.
- Data: faktur PDF sintetis plus struk asli dari dataset CORD.
- Provider harus mudah diganti nanti.
- Tidak mau memakai layanan AI cloud yang bukan miliknya. Mulai dari **mode offline/mock**, LLM menyusul.
- Pendekatan A (Python + Streamlit + DuckDB), README berbahasa Inggris, repo Git lokal.

### Asumsi
- Laptop pengguna: Windows 11, Python 3.11, uv, Git. Ada Docker tapi tidak dipakai di fase 1. CPU Ryzen 5 3500U dan RAM 22 GB tanpa GPU diskrit, jadi fase 1 harus ringan.
- Reviewer atau rekruter harus bisa menjalankan demo dengan `uv sync` lalu `uv run docex demo` tanpa API key dan tanpa internet. Pengecualiannya `fetch-cord`, yang opsional.

### Kriteria sukses
1. `uv run docex demo` pada clone baru selesai dalam kurang dari 3 menit untuk sekitar 40 dokumen. Hasilnya laporan Markdown dan grafik di `reports/<run_id>/`.
2. `uv run pytest` lulus semua. CI GitHub Actions (ruff + pytest) hijau.
3. UI review Streamlit bisa membuka antrean, menampilkan dokumen dan field, serta menyimpan *approve* atau koreksi ke DuckDB.
4. Laporan memuat: akurasi per field, F1 item baris, metrik routing (tingkat otomatisasi, akurasi dokumen lolos otomatis, *error catch rate*, *fault catch rate*), kurva trade-off ambang, diagram kalibrasi, serta rincian per kualitas dokumen dan sumber.
5. README (Inggris) memuat diagram arsitektur, quickstart, hasil, keputusan desain, keterbatasan, dan roadmap. README harus **jujur bahwa angka fase 1 berasal dari extractor simulasi**.

---

## 2. Arsitektur dan alur data

```
 docex generate  ─► PDF faktur sintetis + ground truth (.json) + metadata
 docex fetch-cord ─► gambar struk CORD + ground truth ternormalisasi   (opsional)
                                   │
                                   ▼
             data/documents/   data/ground_truth/   (tabel documents di DuckDB)
                                   │
 docex run ──────────────────────────────────────────────────────────────────┐
   extract   Provider (mock | ... nanti) ─► data terparse per attempt        │
   validate  skema Pydantic + aturan bisnis ─► hasil per aturan              │
   score     confidence per field + per dokumen                              │
   route     auto_approved | needs_review (+ alasan)                         │
 ────────────────────────────────────────────────────────────────────────────┘
                                   │  (semua tersimpan di DuckDB per run_id)
                                   ▼
 docex review  ─► Streamlit: dokumen vs field, approve / koreksi ─► tabel reviews
 docex eval    ─► reports/<run_id>/report.md + grafik PNG
 docex export-labels ─► koreksi reviewer menjadi ground truth baru
 docex demo    ─► generate → run → eval sekaligus
```

Setiap unit punya satu tanggung jawab dan berkomunikasi lewat tipe data yang jelas (model Pydantic dan dataclass), sehingga bisa dites terpisah.

---

## 3. Model data

### 3.1 Skema dokumen (`schemas.py`, Pydantic v2)

Nilai uang memakai `Decimal` (2 desimal, IDR). Tanggal memakai `datetime.date`.

```python
class InvoiceLineItem(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal

class Invoice(BaseModel):
    doc_type: Literal["invoice"] = "invoice"
    invoice_number: str
    invoice_date: date
    due_date: date | None = None
    seller_name: str
    seller_npwp: str | None = None
    buyer_name: str
    buyer_npwp: str | None = None
    currency: Literal["IDR"] = "IDR"
    line_items: list[InvoiceLineItem]
    subtotal: Decimal
    discount: Decimal = Decimal("0")
    tax_base: Decimal          # DPP
    tax_rate: Decimal          # 0.11 atau 0.12
    tax_amount: Decimal        # PPN
    total: Decimal

class ReceiptItem(BaseModel):
    name: str
    quantity: Decimal | None = None
    price: Decimal | None = None      # harga total baris

class Receipt(BaseModel):
    doc_type: Literal["receipt"] = "receipt"
    items: list[ReceiptItem]
    subtotal: Decimal | None = None
    discount: Decimal | None = None
    service_charge: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    cash: Decimal | None = None
    change: Decimal | None = None
```

**Field kritis**, dipakai untuk confidence dokumen dan status "dokumen benar penuh":
- Invoice: `invoice_number, invoice_date, seller_name, seller_npwp, subtotal, tax_amount, total`
- Receipt: `total, subtotal`, hanya field yang ada di ground truth.

### 3.2 Metadata dokumen

```python
@dataclass(frozen=True)
class DocumentMeta:
    doc_id: str                 # mis. "inv-0007", "cord-0012"
    doc_type: Literal["invoice", "receipt"]
    source: Literal["synthetic", "cord"]
    path: Path                  # PDF atau gambar
    quality: Literal["clean", "scan_light", "scan_heavy", "photo"]
    template: str | None        # nama template sintetis
    injected_faults: tuple[str, ...]   # kesalahan yang sengaja ada DI DOKUMEN
    gt_path: Path
```

Ground truth menyimpan **nilai yang tercetak di dokumen**, bukan nilai yang "seharusnya". Contohnya, jika dokumen sengaja memuat total yang salah hitung, ground truth `total` adalah angka salah yang tercetak itu. Validasi kemudian bertugas menandai inkonsistensinya.

---

## 4. Komponen

### 4.1 Generator faktur sintetis (`synthetic/`)
- **Data palsu:** Faker `id_ID` untuk nama perusahaan (PT/CV), alamat, dan orang. Katalog produk/jasa Indonesia meliputi ATK, jasa logistik, sembako, dan jasa IT. Faktur berisi 1–8 item supaya muat di satu halaman.
- **3 template ReportLab:** `modern` (tabel bergrid), `klasik` (label Indonesia: "Faktur", "Kepada Yth."), dan `minimal` (campuran label Inggris/Indonesia).
- **Variasi format:**
  - Nomor faktur: `INV/2026/11/00123`, `FK-000123`, `2026.11.0042`.
  - Tanggal: `05 November 2026`, `05/11/2026`, `2026-11-05`, `5 Nov 2026`.
  - Angka: `Rp 1.234.567`, `1.234.567,00`, `IDR 1,234,567`.
- **Pajak, dua skema yang realistis:**
  - (a) PPN 11% dengan `tax_base = subtotal − discount`;
  - (b) "DPP Nilai Lain" dengan `tax_base = (subtotal − discount) × 11/12` dan `tax_rate = 12%`.
  - Pembulatan ke rupiah penuh.
- **NPWP:** format 15 digit (`01.234.567.8-901.000`) atau 16 digit. Hanya formatnya yang valid; tidak ada checksum resmi yang diklaim.
- **Fault injection** (`--faulty-rate`, default 0,15), tiap dokumen bisa mendapat satu fault:
  - `total_mismatch`: total ≠ subtotal − diskon + PPN
  - `tax_mismatch`: PPN ≠ DPP × tarif
  - `line_amount_mismatch`: qty × harga ≠ jumlah pada satu baris
  - `invalid_npwp`: panjang digit salah
  - `due_before_issue`: jatuh tempo sebelum tanggal faktur
- **Degradasi "hasil scan"** (`--scan-rate`, default 0,3):
  - PDF dirender ke gambar dengan `pypdfium2` pada 150 dpi;
  - diberi rotasi ±1,5°, noise Gauss, blur, kompresi JPEG, dan grayscale;
  - disimpan sebagai PDF berisi gambar dengan kualitas `scan_light` atau `scan_heavy`.
- **Deterministik:** *seed* yang sama menghasilkan dokumen dan ground truth yang identik byte demi byte untuk JSON. Untuk PDF cukup kontennya yang identik.

### 4.2 Loader CORD (`datasets/cord.py`)
- **Sumber:** Hugging Face `naver-clova-ix/cord-v2` (lisensi CC-BY-4.0, atribusi ditulis di README). Yang diunduh hanya file parquet split `test` lewat `huggingface_hub`, lalu dibaca dengan DuckDB.
- **Output:** `--n` sampel (default 50) disimpan sebagai gambar di `data/documents/cord/`. Ground truth `gt_parse` (`menu`, `sub_total`, `total`) dinormalisasi ke skema `Receipt`.
- **Nilai yang tidak bisa dinormalisasi** menjadi `None` dan dicatat di `gt_issues` di file ground truth. Field tersebut dikecualikan dari evaluasi dokumen itu.
- **Kualitas dokumen:** `photo`, tanpa fault injection.
- **Kalau gagal** (offline atau rate limit): muncul pesan jelas dan perintah selesai dengan kode ≠ 0. Pipeline tetap bisa jalan dengan data sintetis saja.

### 4.3 Provider (`providers/`)

```python
class ExtractionProvider(Protocol):
    name: str
    def extract(self, doc: DocumentMeta, schema: type[BaseModel], attempt: int) -> ExtractionResult: ...

@dataclass
class ExtractionResult:
    status: Literal["ok", "failed"]
    data: dict | None            # output mentah sebelum validasi skema
    error: str | None
    latency_ms: float
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    simulated: bool
```

- **`registry.py`:** pemetaan `nama → kelas provider`. Menambah provider baru cukup satu file plus satu baris registrasi.
- **`mock.py` (satu-satunya provider di fase 1):**
  - **Cara kerja dasar:** membaca ground truth dokumen, lalu menerapkan *error model*. RNG di-*seed* oleh `(seed, doc_id, attempt)`.
  - **Peluang error per field:** `p = base_error_rate × quality_multiplier`. Defaultnya `base_error_rate = 0,03`; multiplier untuk `clean` = 1,0, `scan_light` = 1,5, `scan_heavy` = 3,0, `photo` = 2,0.
  - **Operator error menurut tipe field:**
    - angka: `digit_swap`, `thousand_sep` (÷1000), `drop_digit`, `null`;
    - tanggal: `day_month_swap` (jika hari ≤ 12), `year_off_by_one`, `null`;
    - teks: `typo`, `truncate`, `null`;
    - NPWP: `digit_swap`, `drop_digit`;
    - item baris: `drop_item`, ditambah error angka per field item;
    - field opsional yang `None` di ground truth: `hallucinate` dengan peluang `p/3`.
  - **Korelasi antar-attempt:** `consistency_correlation` (default 0,5) adalah peluang attempt ke-2 mengulang error attempt ke-1 di field yang sama. Ini meniru LLM yang konsisten salah.
  - **Kegagalan total:** `failure_rate` (default 0,01) adalah peluang mengembalikan `status="failed"`.
  - **Metrik simulasi:** latensi dan token disimulasikan (token ≈ karakter JSON ÷ 4), `cost_usd = 0.0`, dan `simulated = True`.

### 4.4 Normalisasi (`validation/normalize.py`)
- **Angka Indonesia/Inggris:** `Rp 1.234.567,00`, `1,234,567`, `1.234.567`, `@15.000`, dan `x2` diubah menjadi `Decimal`. Heuristik pemisahnya: jika ada `,` dan `.`, yang terakhir adalah desimal. Jika hanya `.` dengan grup 3 digit, itu pemisah ribuan.
- **Tanggal:** format-format di §4.1 plus nama bulan Indonesia dan Inggris (Januari/January, Agu/Aug, dst.) diubah menjadi `date`.
- **NPWP:** digit saja. Validitas format: 15 atau 16 digit.
- **Teks untuk perbandingan:** casefold, spasi dirapikan, tanda baca di ujung dibuang.

### 4.5 Validasi (`validation/rules.py`)
- **Langkah 1:** output provider dinormalisasi ke model *draft* (`InvoiceDraft`/`ReceiptDraft`, semua field opsional), supaya field yang valid tetap tersimpan walaupun field lain rusak.
  - **R00_parse (hard):** nilai ada tetapi tipe/formatnya tidak bisa diparse, misalnya tanggal `31/02/2026` atau angka `12a.000`.
  - **R01 (hard):** field wajib kosong.
  - Skema ketat (`Invoice`/`Receipt`) dipakai untuk memvalidasi ground truth dan koreksi reviewer.
- **Langkah 2:** aturan bisnis. Setiap aturan punya `rule_id`, `severity` (`hard`/`soft`), `fields`, `passed`, dan `message`.
- **Toleransi:** 1 rupiah per suku pembulatan. Untuk penjumlahan, toleransinya `n_item` rupiah.

| ID | Dokumen | Aturan | Severity |
|---|---|---|---|
| R01 | invoice | field wajib terisi | hard |
| R02 | invoice | `quantity × unit_price ≈ amount` per item | hard |
| R03 | invoice | `subtotal ≈ Σ amount` | hard |
| R04 | invoice | `tax_base ∈ {subtotal−discount, (subtotal−discount)×11/12}` | soft |
| R05 | invoice | `tax_amount ≈ tax_base × tax_rate` | hard |
| R06 | invoice | `total ≈ subtotal − discount + tax_amount` | hard |
| R07 | invoice | format NPWP penjual valid (pembeli: soft) | hard |
| R08 | invoice | tahun faktur ∈ [2015, tahun berjalan + 1] | soft |
| R09 | invoice | `due_date ≥ invoice_date` | soft |
| R10 | invoice | `tax_rate ∈ {0.11, 0.12}` | soft |
| R11 | semua | nilai uang ≥ 0 | hard |
| R20 | receipt | `total` terisi | hard |
| R21 | receipt | `Σ price ≈ subtotal` (jika keduanya ada) | soft |
| R22 | receipt | `total ≈ subtotal − discount + service_charge + tax` | soft |
| R23 | receipt | `change ≈ cash − total` | soft |

Aturan struk dibuat *soft* karena struk asli CORD sering tidak konsisten. Kalau dibuat *hard*, hampir semua struk akan masuk antrean review.

### 4.6 Confidence (`scoring.py`)
- **Nilai awal** confidence setiap field adalah 1,0, lalu dikalikan sesuai kondisi:
  - field wajib kosong: 0,0;
  - format tidak bisa dinormalisasi atau tidak valid: × 0,3;
  - terlibat aturan *hard* yang gagal: × 0,5;
  - terlibat aturan *soft* yang gagal: × 0,8;
  - jika `consistency_runs = 2` dan nilai antar-attempt berbeda: × 0,4.
- **Self-consistency:** default `consistency_runs = 2`, karena gratis di mode mock. Attempt ke-1 adalah hasil utama.
- **Confidence dokumen** = minimum confidence field kritis yang ada di ground truth/skema.
- **Alasan:** setiap pengurangan menyimpan alasannya (`reasons`), dan alasan inilah yang ditampilkan di UI.

### 4.7 Routing (`routing.py`)
- **`needs_review`** jika ekstraksi `failed`, ATAU ada aturan *hard* yang gagal, ATAU confidence dokumen < `review_threshold` (default 0,7).
- **`auto_approved`** untuk selain itu.
- **Alasan routing** disimpan sebagai daftar, misalnya `["R06 total mismatch", "low confidence: seller_npwp=0.40"]`.

### 4.8 Penyimpanan (`storage.py`, DuckDB `data/docex.duckdb`)

| Tabel | Kolom utama |
|---|---|
| `documents` | doc_id (PK), doc_type, source, path, quality, template, injected_faults (JSON), gt_path, created_at |
| `runs` | run_id (PK), provider, model, config (JSON), started_at, finished_at, n_docs, status |
| `extractions` | run_id, doc_id, attempt, status, data (JSON), error, latency_ms, input_tokens, output_tokens, cost_usd, simulated |
| `validations` | run_id, doc_id, rule_id, severity, passed, fields (JSON), message |
| `field_scores` | run_id, doc_id, field, value (JSON), confidence, reasons (JSON) |
| `decisions` | run_id, doc_id, route, doc_confidence, reasons (JSON) |
| `reviews` | run_id, doc_id, action (`approve`/`correct`), corrected_data (JSON), reviewed_at |

- **Pembuatan tabel:** semua tabel dibuat dengan `CREATE TABLE IF NOT EXISTS` saat koneksi dibuka.
- **`run_id`:** dibentuk dari `YYYYMMDD-HHMMSS-<provider>`, sehingga run baru tidak menimpa run lama.
- **Batasan koneksi:** DuckDB hanya mengizinkan satu proses penulis. Streamlit membuka koneksi per aksi lalu menutupnya, supaya `docex run` dan UI review tidak saling mengunci dalam penggunaan normal.

### 4.9 Pipeline (`pipeline.py`)
Untuk setiap dokumen: `extract` (×`consistency_runs`), `validate`, `score`, `route`, lalu simpan.
- Kegagalan satu dokumen (exception apa pun) ditangkap, dicatat sebagai `failed` beserta pesannya, dan diarahkan ke `needs_review`. Batch tetap lanjut.
- Ringkasan akhir run ditampilkan di terminal dengan `rich`: jumlah dokumen, jumlah auto-approved, jumlah needs_review, dan jumlah failed.

### 4.10 Evaluasi (`evaluation/`)

**Pencocokan field:**
- angka: |pred − gt| ≤ 1;
- tanggal: harus sama persis;
- ID (`invoice_number`, NPWP sebagai digit saja): harus sama persis setelah normalisasi;
- nama/teks: skor `rapidfuzz.fuzz.ratio` ≥ 90 setelah normalisasi;
- `None` vs `None` dihitung benar.

**Item baris:**
- Pencocokan *greedy* berdasarkan kemiripan deskripsi dan jumlah.
- Satu item dihitung benar jika semua field-nya cocok.
- Dihitung precision, recall, dan F1.

**Metrik:**
- akurasi per field;
- akurasi dokumen penuh (semua field kritis benar);
- F1 item baris;
- **tingkat otomatisasi** = % `auto_approved`;
- **akurasi dokumen lolos otomatis** = % dokumen `auto_approved` yang semua field kritisnya benar;
- ***error catch rate*** = di antara dokumen yang ekstraksinya salah di field kritis, % yang masuk `needs_review`;
- ***fault catch rate*** = di antara dokumen ber-`injected_faults`, % yang masuk `needs_review`;
- semua metrik di atas dirinci per `quality`, `source`, dan `template`.

**Kurva dan grafik:**
- **Trade-off ambang:** ambang 0,05–0,95 terhadap tingkat otomatisasi dan akurasi lolos otomatis. Contoh narasi untuk CV: "pada ambang X, 70% dokumen otomatis dengan akurasi 99%".
- **Diagram kalibrasi:** bin confidence terhadap akurasi aktual.

**Output** di `reports/<run_id>/`:
- `report.md` (tabel metrik + gambar);
- `field_accuracy.png`, `accuracy_by_quality.png`, `threshold_tradeoff.png`, `calibration.png`;
- `metrics.json`.

Semua angka diberi label **"simulated extractor"** jika `simulated = True`.

### 4.11 UI review (`src/docex/review_app.py`, Streamlit)
- **Sidebar:** pilih `run_id`, filter route (needs_review/auto_approved/semua). Daftar dokumen diurutkan dari confidence terendah, dengan penanda dokumen yang sudah direview.
- **Kolom kiri:** gambar dokumen. PDF dirender dengan `pypdfium2`, gambar CORD ditampilkan langsung.
- **Kolom kanan:** form field terisi hasil ekstraksi. Field dengan confidence < ambang ditandai beserta alasannya. Daftar aturan yang gagal ditampilkan, dan item baris bisa diedit dengan `st.data_editor`.
- **Aksi:**
  - **Approve:** simpan `action = approve`.
  - **Simpan koreksi:** validasi ulang ke skema Pydantic. Jika valid, simpan `action = correct` beserta `corrected_data`; jika tidak valid, tampilkan error tanpa menyimpan.
  - Setelah aksi, lanjut ke dokumen berikutnya.
- **Header:** ukuran antrean, jumlah yang sudah direview, dan tingkat otomatisasi run.
- **Peluncuran:** dijalankan dengan `docex review`, yang memanggil `streamlit run` pada path `review_app.py` (diambil dari `__file__` package, sehingga bekerja dari folder mana pun).

### 4.12 Konfigurasi (`config.py`)
- **Mekanisme:** `pydantic-settings` dengan prefiks env `DOCEX_` dan file `.env` opsional. Flag CLI menimpa env.
- **Kunci:** `data_dir` (`data`), `db_path` (`data/docex.duckdb`), `reports_dir` (`reports`), `provider` (`mock`), `seed` (42), `consistency_runs` (2), `review_threshold` (0,7), `mock_base_error_rate` (0,03), `mock_consistency_correlation` (0,5), `mock_failure_rate` (0,01).
- **`.env.example`:** ikut di-commit.

### 4.13 CLI (`cli.py`, Typer, entry point `docex`)

| Perintah | Fungsi |
|---|---|
| `docex generate --n 100 --seed 42 --faulty-rate 0.15 --scan-rate 0.3` | Membuat faktur sintetis dan mendaftarkannya ke `documents` |
| `docex fetch-cord --n 50` | Mengunduh dan mendaftarkan sampel CORD (butuh internet) |
| `docex run --provider mock [--source synthetic\|cord\|all] [--limit N]` | Menjalankan pipeline dan mencetak `run_id` |
| `docex eval --run <run_id>` (default: run terakhir) | Membuat laporan |
| `docex review` | Membuka UI review |
| `docex export-labels --run <run_id>` | Menulis koreksi reviewer ke `data/labels/<doc_id>.json` |
| `docex demo` | `generate --n 40` (jika belum ada), lalu `run`, lalu `eval`, lalu ringkasan dan path laporan |

---

## 5. Penanganan error
- **Satu dokumen gagal:** run tidak dihentikan (§4.9).
- **File dokumen atau ground truth hilang/rusak:** dicatat `failed` dengan pesan yang jelas.
- **Error skema:** dipetakan ke field dan tampil di UI.
- **CORD gagal diunduh:** perintahnya keluar dengan pesan dan saran. Perintah lain tidak terpengaruh.
- **Koreksi di UI tidak valid:** tidak disimpan, dan error ditampilkan.
- **Perintah `eval` tanpa run:** muncul pesan "jalankan `docex run` dulu", dengan exit code 1.

## 6. Testing
- **Pendekatan:** TDD dengan pytest. Tes tidak butuh internet; tes CORD memakai fixture parquet kecil buatan sendiri.
- **Unit:**
  - normalisasi (angka, tanggal, NPWP);
  - setiap aturan validasi (lulus/gagal/toleransi);
  - operator error mock dan determinisme *seed*;
  - korelasi antar-attempt;
  - skor confidence;
  - routing;
  - pencocokan field;
  - F1 item baris;
  - metrik routing;
  - trade-off ambang.
- **Generator:**
  - *seed* sama menghasilkan ground truth identik;
  - faktur bersih lolos semua aturan *hard*;
  - setiap jenis fault memicu aturan yang sesuai;
  - degradasi scan menghasilkan PDF yang bisa dibuka.
- **Integrasi:** `generate(10)`, lalu `run(mock)`, lalu `eval` di `tmp_path`. Laporan dan semua PNG harus terbentuk, dan angka-angkanya konsisten dengan isi DuckDB.
- **UI:** *smoke test* `streamlit.testing.v1.AppTest`, yaitu halaman terbuka tanpa exception dengan DB berisi 1 run.
- **CLI:** `typer.testing.CliRunner` untuk `generate`, `run`, `eval`, `demo` dengan `--n` kecil.
- **CI:** `.github/workflows/ci.yml` di ubuntu-latest menjalankan `astral-sh/setup-uv`, `uv sync`, `uv run ruff check`, `uv run ruff format --check`, lalu `uv run pytest`.

## 7. Struktur repo

```
llm-doc-extractor/
├─ src/docex/
│  ├─ __init__.py  cli.py  config.py  schemas.py  storage.py
│  ├─ pipeline.py  scoring.py  routing.py  review_app.py
│  ├─ providers/     __init__.py  base.py  mock.py  registry.py
│  ├─ synthetic/     __init__.py  catalog.py  generator.py  templates.py  degrade.py
│  ├─ datasets/      __init__.py  cord.py
│  ├─ validation/    __init__.py  normalize.py  rules.py
│  └─ evaluation/    __init__.py  matching.py  metrics.py  report.py
├─ tests/  (mencerminkan struktur src/ + tests/integration/)
├─ docs/superpowers/specs/  docs/superpowers/plans/
├─ data/      (gitignored; dibuat otomatis)
├─ reports/   (gitignored, kecuali satu contoh laporan untuk README)
├─ .github/workflows/ci.yml
├─ pyproject.toml  uv.lock  .env.example  .gitignore  README.md  LICENSE (MIT)
```

**Dependensi:** `pydantic`, `pydantic-settings`, `typer`, `rich`, `faker`, `reportlab`, `pypdfium2`, `pillow`, `numpy`, `duckdb`, `streamlit`, `matplotlib`, `rapidfuzz`, `huggingface_hub`. **Dev:** `pytest`, `ruff`.

## 8. Di luar cakupan fase 1
- **Provider LLM sungguhan:** Ollama lokal, Claude, atau cloud lain.
- **OCR/ekstraksi teks:** keduanya baru dibutuhkan saat ada LLM sungguhan.
- **Infrastruktur dan fitur tambahan:** endpoint FastAPI, Docker, autentikasi UI, multi-user, faktur multi-halaman, dan e-Faktur resmi DJP (QR/validasi online).

## 9. Roadmap setelah fase 1 (informatif, bukan bagian implementasi ini)
1. **Fase 2, LLM lokal offline:** provider `ollama` dengan alur RapidOCR → model teks kecil (mis. `qwen2.5:3b`) dan output JSON yang dikunci skema. Dibandingkan dengan mock dan baseline aturan.
2. **Fase 3:** provider cloud opsional (milik pengguna sendiri), perbandingan biaya/akurasi/latensi antar-model, dan endpoint FastAPI.
