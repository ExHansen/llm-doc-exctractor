from docex.evaluation.metrics import DocRecord, evaluate


def rec(
    doc_id,
    route,
    conf,
    correct,
    faults=(),
    hard_failed=False,
    failed=False,
    quality="clean",
    source="synthetic",
):
    return DocRecord(
        doc_id=doc_id,
        source=source,
        quality=quality,
        template="modern",
        faults=tuple(faults),
        route=route,
        doc_confidence=conf,
        failed=failed,
        hard_failed=hard_failed,
        field_correct={"total": correct},
        critical_correct=correct and not failed,
        field_conf={"total": conf},
        items_tp=1,
        items_fp=0,
        items_fn=0,
    )


def test_routing_metrics():
    recs = [
        rec("a", "auto_approved", 0.9, True),
        rec("b", "auto_approved", 0.8, False),
        rec("c", "needs_review", 0.3, False, faults=("total_mismatch",), hard_failed=True),
        rec("d", "needs_review", 0.5, True),
    ]
    r = evaluate(recs, "r1", True)
    assert r.n_docs == 4 and r.simulated
    assert r.automation_rate == 0.5 and r.auto_approved_accuracy == 0.5
    assert r.error_catch_rate == 0.5 and r.fault_catch_rate == 1.0
    assert r.fault_catch_by_type == {"total_mismatch": 1.0}
    assert r.doc_accuracy == 0.5 and r.field_accuracy == {"total": 0.5}
    t = {row["threshold"]: row for row in r.tradeoff}
    assert len(r.tradeoff) == 19
    assert t[0.85]["automation_rate"] == 0.25 and t[0.85]["auto_approved_accuracy"] == 1.0
    assert t[0.95]["automation_rate"] == 0.0 and t[0.95]["auto_approved_accuracy"] is None


def test_calibration_bins():
    recs = [
        rec("a", "auto_approved", 0.95, True),
        rec("b", "auto_approved", 0.92, False),
        rec("c", "needs_review", 0.31, False),
    ]
    cal = {row["bin_low"]: row for row in evaluate(recs, "r1", True).calibration}
    assert set(cal) == {0.3, 0.9}
    assert cal[0.9]["n"] == 2 and cal[0.9]["accuracy"] == 0.5
    assert cal[0.3]["mean_confidence"] == 0.31


def test_breakdown_and_items():
    recs = [
        rec("a", "auto_approved", 0.9, True, quality="clean"),
        rec("b", "needs_review", 0.2, False, quality="scan_heavy"),
    ]
    r = evaluate(recs, "r1", False)
    assert r.breakdown["quality"]["clean"] == {"n": 1, "automation_rate": 1.0, "doc_accuracy": 1.0}
    assert r.breakdown["quality"]["scan_heavy"]["automation_rate"] == 0.0
    assert r.item_precision == 1.0 and r.item_recall == 1.0 and r.item_f1 == 1.0


def test_empty_denominators_are_none():
    r = evaluate([rec("a", "needs_review", 0.1, True)], "r1", True)
    assert r.auto_approved_accuracy is None and r.fault_catch_rate is None
    assert r.error_catch_rate is None
