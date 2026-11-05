"""Streamlit review queue. Launch with `docex review`."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from docex.config import Settings
from docex.imaging import render_first_page
from docex.review_logic import build_corrected, form_values
from docex.schemas import FIELD_KINDS, ITEM_FIELD_KINDS
from docex.storage import Store

st.set_page_config(page_title="docex review", layout="wide")
settings = Settings()


def store() -> Store:
    # A fresh connection per read/write, so `docex run` can use the database meanwhile.
    return Store(settings.resolved_db_path)


with store() as s:
    runs = s.list_runs()
if not runs:
    st.info("No runs yet. Run `docex run` first.")
    st.stop()

st.sidebar.title("docex review")
run_id = st.sidebar.selectbox("Run", [r["run_id"] for r in runs])
show = st.sidebar.radio("Show", ["needs_review", "auto_approved", "all"], horizontal=True)

with store() as s:
    decisions = s.get_decisions(run_id)
    reviews = s.get_reviews(run_id)
    config = s.get_run_config(run_id) or {}
threshold = float(config.get("review_threshold", settings.review_threshold))

queue = [d for d in decisions if d["route"] == "needs_review"]
c1, c2, c3 = st.columns(3)
c1.metric("Review queue", len(queue))
c2.metric("Reviewed", sum(1 for d in queue if d["doc_id"] in reviews))
automation = 1 - len(queue) / len(decisions) if decisions else 0.0
c3.metric("Automation rate", f"{automation:.0%}")

docs = sorted(
    (d for d in decisions if show == "all" or d["route"] == show),
    key=lambda d: (d["doc_confidence"], d["doc_id"]),
)
if not docs:
    st.success("Nothing to show for this filter.")
    st.stop()

if "advance_to" in st.session_state:
    st.session_state["doc_radio"] = st.session_state.pop("advance_to")
if st.session_state.get("doc_radio", 0) >= len(docs):
    st.session_state["doc_radio"] = 0


def doc_label(i: int) -> str:
    d = docs[i]
    mark = "✓ " if d["doc_id"] in reviews else ""
    return f"{mark}{d['doc_id']} ({d['doc_confidence']:.2f})"


index = st.sidebar.radio(
    "Documents", list(range(len(docs))), format_func=doc_label, key="doc_radio"
)
current = docs[index]
doc_id = current["doc_id"]
with store() as s:
    detail = s.get_doc_detail(run_id, doc_id)
doc = detail["doc"]

left, right = st.columns([5, 4])
with left:
    st.subheader(doc_id)
    st.caption(f"{doc.doc_type} · {doc.source} · quality: {doc.quality}")
    try:
        st.image(render_first_page(settings.data_dir / doc.path, dpi=110), width="stretch")
    except (FileNotFoundError, OSError) as exc:
        st.error(f"Cannot open document file: {exc}")

with right:
    decision = detail["decision"]
    route_text = decision.route.replace("_", " ")
    st.markdown(f"**Route:** {route_text} · **confidence** {decision.doc_confidence:.2f}")
    for reason in decision.reasons:
        st.markdown(f"- {reason}")
    failed_rules = [r for r in detail["rules"] if not r.passed]
    if failed_rules:
        with st.expander(f"Failed rules ({len(failed_rules)})", expanded=False):
            for r in failed_rules:
                st.markdown(f"- `{r.rule_id}` ({r.severity}): {r.message}")
    first = detail["extractions"][0] if detail["extractions"] else None
    if first is None or first["status"] != "ok":
        st.error(f"Extraction failed: {first['error'] if first else 'no extraction'}")

    review = reviews.get(doc_id)
    source_data = (review or {}).get("corrected_data") or (first or {}).get("data")
    scalars, items = form_values(doc.doc_type, source_data)
    scores = {sc.field: sc for sc in detail["scores"]}

    edited: dict[str, str] = {}
    for field in FIELD_KINDS[doc.doc_type]:
        score = scores.get(field)
        conf = f" · {score.confidence:.2f}" if score else ""
        flag = " ⚠" if score and score.confidence < threshold else ""
        edited[field] = st.text_input(
            f"{field}{conf}{flag}", value=scalars[field], key=f"{run_id}:{doc_id}:{field}"
        )
        if score and score.reasons:
            st.caption(", ".join(score.reasons))

    columns = list(ITEM_FIELD_KINDS[doc.doc_type])
    frame = pd.DataFrame(items, columns=columns, dtype="string")
    edited_items = st.data_editor(
        frame,
        num_rows="dynamic",
        key=f"{run_id}:{doc_id}:items",
        column_config={c: st.column_config.TextColumn(c) for c in columns},
        hide_index=True,
    )
    item_rows = edited_items.fillna("").astype(str).to_dict("records")

    approve_col, save_col = st.columns(2)
    approved = approve_col.button("Approve", type="primary")
    saved = save_col.button("Save corrections")

    if approved or saved:
        if approved:
            with store() as s:
                s.save_review(run_id, doc_id, "approve", None)
            ok = True
        else:
            corrected, errors = build_corrected(doc.doc_type, edited, item_rows)
            ok = corrected is not None
            if ok:
                with store() as s:
                    s.save_review(run_id, doc_id, "correct", corrected)
            else:
                st.error("Not saved:\n\n" + "\n".join(f"- {e}" for e in errors))
        if ok:
            st.session_state["advance_to"] = min(index + 1, len(docs) - 1)
            st.rerun()
