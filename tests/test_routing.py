from docex.results import FieldScore, RuleResult
from docex.routing import route


def test_route_auto_when_confident():
    ok = route(None, [], [], 0.9, 0.7, "invoice")
    assert ok.route == "auto_approved" and ok.reasons == () and ok.doc_confidence == 0.9


def test_route_reasons_in_order():
    hard = RuleResult("R06", "hard", False, ("total",), "total mismatch")
    soft = RuleResult("R04", "soft", False, ("tax_base",), "dpp")
    low = FieldScore("seller_npwp", "1", 0.4, ())
    noncritical = FieldScore("buyer_name", "x", 0.1, ())
    d = route(None, [hard, soft], [low, noncritical], 0.4, 0.7, "invoice")
    assert d.route == "needs_review"
    assert d.reasons == ("R06 failed: total mismatch", "low confidence: seller_npwp=0.40")


def test_hard_failure_routes_even_when_confident():
    hard = RuleResult("R09", "hard", False, ("due_date",), "due before issue")
    assert route(None, [hard], [], 1.0, 0.7, "invoice").route == "needs_review"


def test_failed_extraction():
    d = route("boom", [], [], 1.0, 0.7, "invoice")
    assert d.route == "needs_review" and d.reasons[0] == "extraction failed: boom"
