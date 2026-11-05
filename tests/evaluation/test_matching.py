from docex.evaluation.matching import field_match, match_items


def test_field_match_rules():
    assert field_match("money", "1234567.00", "1.234.567")
    assert not field_match("money", "1234.567", "1234567.00")
    assert not field_match("money", "12a.000", "12000.00")
    assert field_match("text", "PT Maju Jaya Tbk", "PT. Maju Jaya Tbk")
    assert not field_match("text", "PT Maju", "CV Sinar Abadi")
    assert not field_match("id", "INV/2026/11/00123", "INV/2026/11/00132")
    assert field_match("npwp", "01.234.567.8-901.000", "012345678901000")
    assert field_match("rate", "11%", "0.11")
    assert field_match("date", None, None) and not field_match("date", "2026-11-05", None)
    assert field_match("date", "05/11/2026", "2026-11-05")


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


def test_match_items_dropped_and_extra():
    gt = [
        {"name": "Es Teh", "quantity": "2", "price": "10000"},
        {"name": "Nasi Goreng", "quantity": "1", "price": "25000"},
    ]
    assert match_items("receipt", gt[:1], gt) == (1, 0, 1)
    assert match_items("receipt", gt + [{"name": "Kerupuk", "price": "2000"}], gt) == (2, 1, 0)
    assert match_items("receipt", [], []) == (0, 0, 0)
