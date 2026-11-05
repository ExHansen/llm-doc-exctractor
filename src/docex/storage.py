"""DuckDB persistence for documents, runs, per-document results and reviews."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import duckdb

from docex.results import Decision, DocResult, FieldScore, RuleResult
from docex.schemas import DocumentMeta

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id VARCHAR PRIMARY KEY, doc_type VARCHAR, source VARCHAR, path VARCHAR,
    quality VARCHAR, template VARCHAR, injected_faults VARCHAR, gt_path VARCHAR,
    created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS runs (
    run_id VARCHAR PRIMARY KEY, provider VARCHAR, model VARCHAR, config VARCHAR,
    started_at TIMESTAMP, finished_at TIMESTAMP, n_docs INTEGER, status VARCHAR
);
CREATE TABLE IF NOT EXISTS extractions (
    run_id VARCHAR, doc_id VARCHAR, attempt INTEGER, status VARCHAR, data VARCHAR,
    error VARCHAR, latency_ms DOUBLE, input_tokens INTEGER, output_tokens INTEGER,
    cost_usd DOUBLE, simulated BOOLEAN
);
CREATE TABLE IF NOT EXISTS validations (
    run_id VARCHAR, doc_id VARCHAR, seq INTEGER, rule_id VARCHAR, severity VARCHAR,
    passed BOOLEAN, fields VARCHAR, message VARCHAR
);
CREATE TABLE IF NOT EXISTS field_scores (
    run_id VARCHAR, doc_id VARCHAR, seq INTEGER, field VARCHAR, value VARCHAR,
    confidence DOUBLE, reasons VARCHAR
);
CREATE TABLE IF NOT EXISTS decisions (
    run_id VARCHAR, doc_id VARCHAR, route VARCHAR, doc_confidence DOUBLE, reasons VARCHAR
);
CREATE TABLE IF NOT EXISTS reviews (
    run_id VARCHAR, doc_id VARCHAR, action VARCHAR, corrected_data VARCHAR,
    reviewed_at TIMESTAMP, PRIMARY KEY (run_id, doc_id)
);
"""


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _load(text: str | None) -> Any:
    return None if text is None else json.loads(text)


class Store:
    """A short-lived connection to the DuckDB file. Use it as a context manager."""

    def __init__(self, db_path: Path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(str(db_path))
        self._con.execute(SCHEMA)

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- documents ---

    def upsert_documents(self, metas: list[DocumentMeta]) -> None:
        now = datetime.now()
        rows = [
            (m.doc_id, m.doc_type, m.source, m.path, m.quality, m.template,
             _dump(list(m.injected_faults)), m.gt_path, now)
            for m in metas
        ]  # fmt: skip
        if rows:
            self._con.executemany(
                "INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
            )

    @staticmethod
    def _meta(row: tuple) -> DocumentMeta:
        doc_id, doc_type, source, path, quality, template, faults, gt_path = row
        return DocumentMeta(
            doc_id, doc_type, source, path, quality, template, tuple(_load(faults)), gt_path
        )

    _META_COLS = "doc_id, doc_type, source, path, quality, template, injected_faults, gt_path"

    def list_documents(
        self, source: str | None = None, limit: int | None = None
    ) -> list[DocumentMeta]:
        sql = f"SELECT {self._META_COLS} FROM documents"
        params: list[Any] = []
        if source is not None:
            sql += " WHERE source = ?"
            params.append(source)
        sql += " ORDER BY doc_id"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return [self._meta(r) for r in self._con.execute(sql, params).fetchall()]

    def get_document(self, doc_id: str) -> DocumentMeta | None:
        row = self._con.execute(
            f"SELECT {self._META_COLS} FROM documents WHERE doc_id = ?", [doc_id]
        ).fetchone()
        return None if row is None else self._meta(row)

    # --- runs ---

    def new_run_id(self, provider: str, now: datetime | None = None) -> str:
        base = f"{(now or datetime.now()):%Y%m%d-%H%M%S}-{provider}"
        candidate, n = base, 1
        while self._con.execute("SELECT 1 FROM runs WHERE run_id = ?", [candidate]).fetchone():
            n += 1
            candidate = f"{base}-{n}"
        return candidate

    def create_run(
        self, provider: str, model: str, config: dict, now: datetime | None = None
    ) -> str:
        run_id = self.new_run_id(provider, now)
        self._con.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, NULL, 0, 'running')",
            [run_id, provider, model, _dump(config), datetime.now()],
        )
        return run_id

    def finish_run(self, run_id: str, n_docs: int, status: str) -> None:
        self._con.execute(
            "UPDATE runs SET finished_at = ?, n_docs = ?, status = ? WHERE run_id = ?",
            [datetime.now(), n_docs, status, run_id],
        )

    def latest_run_id(self) -> str | None:
        row = self._con.execute(
            "SELECT run_id FROM runs ORDER BY started_at DESC, run_id DESC LIMIT 1"
        ).fetchone()
        return None if row is None else row[0]

    def list_runs(self) -> list[dict]:
        rows = self._con.execute(
            "SELECT run_id, provider, model, n_docs, status, started_at FROM runs "
            "ORDER BY started_at DESC, run_id DESC"
        ).fetchall()
        keys = ("run_id", "provider", "model", "n_docs", "status", "started_at")
        return [dict(zip(keys, r, strict=True)) for r in rows]

    def run_simulated(self, run_id: str) -> bool:
        row = self._con.execute(
            "SELECT bool_or(simulated) FROM extractions WHERE run_id = ?", [run_id]
        ).fetchone()
        return bool(row and row[0])

    # --- per-document results ---

    def save_doc_result(self, run_id: str, result: DocResult) -> None:
        doc_id = result.doc.doc_id
        self._con.executemany(
            "INSERT INTO extractions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (run_id, doc_id, i, e.status, None if e.data is None else _dump(e.data), e.error,
                 e.latency_ms, e.input_tokens, e.output_tokens, e.cost_usd, e.simulated)
                for i, e in enumerate(result.extractions, start=1)
            ],
        )  # fmt: skip
        if result.rules:
            self._con.executemany(
                "INSERT INTO validations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (run_id, doc_id, i, r.rule_id, r.severity, r.passed, _dump(list(r.fields)),
                     r.message)
                    for i, r in enumerate(result.rules)
                ],
            )  # fmt: skip
        if result.scores:
            self._con.executemany(
                "INSERT INTO field_scores VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (run_id, doc_id, i, s.field, _dump(s.value), s.confidence,
                     _dump(list(s.reasons)))
                    for i, s in enumerate(result.scores)
                ],
            )  # fmt: skip
        d = result.decision
        self._con.execute(
            "INSERT INTO decisions VALUES (?, ?, ?, ?, ?)",
            [run_id, doc_id, d.route, d.doc_confidence, _dump(list(d.reasons))],
        )

    def get_decisions(self, run_id: str) -> list[dict]:
        rows = self._con.execute(
            "SELECT doc_id, route, doc_confidence, reasons FROM decisions WHERE run_id = ? "
            "ORDER BY doc_id",
            [run_id],
        ).fetchall()
        return [
            {"doc_id": r[0], "route": r[1], "doc_confidence": r[2], "reasons": _load(r[3])}
            for r in rows
        ]

    def get_doc_detail(self, run_id: str, doc_id: str) -> dict:
        extractions = [
            {"attempt": r[0], "status": r[1], "data": _load(r[2]), "error": r[3],
             "latency_ms": r[4], "input_tokens": r[5], "output_tokens": r[6],
             "cost_usd": r[7], "simulated": r[8]}
            for r in self._con.execute(
                "SELECT attempt, status, data, error, latency_ms, input_tokens, output_tokens, "
                "cost_usd, simulated FROM extractions WHERE run_id = ? AND doc_id = ? "
                "ORDER BY attempt",
                [run_id, doc_id],
            ).fetchall()
        ]  # fmt: skip
        rules = [
            RuleResult(r[0], r[1], r[2], tuple(_load(r[3])), r[4])
            for r in self._con.execute(
                "SELECT rule_id, severity, passed, fields, message FROM validations "
                "WHERE run_id = ? AND doc_id = ? ORDER BY seq",
                [run_id, doc_id],
            ).fetchall()
        ]
        scores = [
            FieldScore(r[0], _load(r[1]), r[2], tuple(_load(r[3])))
            for r in self._con.execute(
                "SELECT field, value, confidence, reasons FROM field_scores "
                "WHERE run_id = ? AND doc_id = ? ORDER BY seq",
                [run_id, doc_id],
            ).fetchall()
        ]
        row = self._con.execute(
            "SELECT route, doc_confidence, reasons FROM decisions WHERE run_id = ? AND doc_id = ?",
            [run_id, doc_id],
        ).fetchone()
        decision = None if row is None else Decision(row[0], row[1], tuple(_load(row[2])))
        return {
            "doc": self.get_document(doc_id),
            "extractions": extractions,
            "rules": rules,
            "scores": scores,
            "decision": decision,
        }

    # --- reviews ---

    def save_review(
        self,
        run_id: str,
        doc_id: str,
        action: Literal["approve", "correct"],
        corrected_data: dict | None,
    ) -> None:
        self._con.execute(
            "INSERT OR REPLACE INTO reviews VALUES (?, ?, ?, ?, ?)",
            [run_id, doc_id, action, None if corrected_data is None else _dump(corrected_data),
             datetime.now()],
        )  # fmt: skip

    def get_reviews(self, run_id: str) -> dict[str, dict]:
        rows = self._con.execute(
            "SELECT doc_id, action, corrected_data, reviewed_at FROM reviews WHERE run_id = ?",
            [run_id],
        ).fetchall()
        return {
            r[0]: {"action": r[1], "corrected_data": _load(r[2]), "reviewed_at": r[3]} for r in rows
        }
