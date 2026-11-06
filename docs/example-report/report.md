# Extraction QC report: run `20261106-123332-mock`

> **Simulated extractor.** These numbers come from the offline mock provider, which returns ground truth with injected LLM/OCR-style errors. They measure the QC pipeline (validation, confidence, routing), not a real model.

## Headline

| Metric | Value | Meaning |
|---|---|---|
| Documents | 40 | Documents in the run. |
| Automation rate | 22.5% | Share of documents auto-approved. |
| Auto-approved accuracy | 100.0% | Share of auto-approved documents whose critical fields are all correct. |
| Error catch rate | 100.0% | Share of documents with a wrong critical field that were sent to review (failed extractions excluded: they always go to review). |
| Fault catch rate | 100.0% | Share of documents with a printed fault (wrong total, bad NPWP...) sent to review. |
| Document accuracy | 65.0% | Share of documents with every critical field correct. |
| Line-item F1 | 85.6% | Line items extracted with every field correct. |

Review threshold: **0.70** (document confidence).

## Field accuracy

![Field accuracy](field_accuracy.png)

| Field | Accuracy |
|---|---|
| `invoice.buyer_name` | 97.5% |
| `invoice.buyer_npwp` | 100.0% |
| `invoice.discount` | 95.0% |
| `invoice.due_date` | 87.5% |
| `invoice.invoice_date` | 85.0% |
| `invoice.invoice_number` | 90.0% |
| `invoice.seller_name` | 95.0% |
| `invoice.seller_npwp` | 92.5% |
| `invoice.subtotal` | 92.5% |
| `invoice.tax_amount` | 87.5% |
| `invoice.tax_base` | 95.0% |
| `invoice.tax_rate` | 90.0% |
| `invoice.total` | 95.0% |

## Fault catch rate by fault type

| Injected fault | Sent to review |
|---|---|
| `due_before_issue` | 100.0% |
| `invalid_npwp` | 100.0% |
| `line_amount_mismatch` | 100.0% |
| `total_mismatch` | 100.0% |

## Breakdown

![By quality](accuracy_by_quality.png)

### By quality

| quality | n | Automation | Auto-approved acc. | Error catch | Fault catch | Doc accuracy | Item F1 |
|---|---|---|---|---|---|---|---|
| clean | 25 | 32.0% | 100.0% | 100.0% | 100.0% | 68.0% | 88.8% |
| scan_heavy | 7 | 0.0% | n/a | 100.0% | 100.0% | 57.1% | 66.7% |
| scan_light | 8 | 12.5% | 100.0% | 100.0% | n/a | 62.5% | 92.3% |

### By source

| source | n | Automation | Auto-approved acc. | Error catch | Fault catch | Doc accuracy | Item F1 |
|---|---|---|---|---|---|---|---|
| synthetic | 40 | 22.5% | 100.0% | 100.0% | 100.0% | 65.0% | 85.6% |

### By template

| template | n | Automation | Auto-approved acc. | Error catch | Fault catch | Doc accuracy | Item F1 |
|---|---|---|---|---|---|---|---|
| klasik | 17 | 23.5% | 100.0% | 100.0% | n/a | 64.7% | 84.7% |
| minimal | 10 | 30.0% | 100.0% | 100.0% | 100.0% | 60.0% | 88.4% |
| modern | 13 | 15.4% | 100.0% | 100.0% | 100.0% | 69.2% | 84.6% |

## Threshold trade-off

Raising the threshold sends more documents to review and makes the auto-approved set more accurate.

![Threshold trade-off](threshold_tradeoff.png)

| Threshold | Automation rate | Auto-approved accuracy |
|---|---|---|
| 0.05 | 35.0% | 92.9% |
| 0.10 | 35.0% | 92.9% |
| 0.15 | 35.0% | 92.9% |
| 0.20 | 35.0% | 92.9% |
| 0.25 | 35.0% | 92.9% |
| 0.30 | 35.0% | 92.9% |
| 0.35 | 35.0% | 92.9% |
| 0.40 | 35.0% | 92.9% |
| 0.45 | 22.5% | 100.0% |
| 0.50 | 22.5% | 100.0% |
| 0.55 | 22.5% | 100.0% |
| 0.60 | 22.5% | 100.0% |
| 0.65 | 22.5% | 100.0% |
| 0.70 | 22.5% | 100.0% |
| 0.75 | 22.5% | 100.0% |
| 0.80 | 22.5% | 100.0% |
| 0.85 | 22.5% | 100.0% |
| 0.90 | 22.5% | 100.0% |
| 0.95 | 22.5% | 100.0% |

## Calibration

Do fields with confidence X turn out correct X% of the time?

![Calibration](calibration.png)

| Confidence bin | Fields | Mean confidence | Accuracy |
|---|---|---|---|
| 0.0-0.1 | 5 | 0.00 | 0.0% |
| 0.1-0.2 | 3 | 0.11 | 0.0% |
| 0.2-0.3 | 2 | 0.23 | 50.0% |
| 0.4-0.5 | 14 | 0.40 | 78.6% |
| 0.5-0.6 | 26 | 0.50 | 96.2% |
| 0.9-1.0 | 223 | 1.00 | 97.8% |
