from docex.groundtruth import GroundTruth, read_ground_truth, write_ground_truth


def test_ground_truth_roundtrip(tmp_path):
    gt = GroundTruth("inv-0001", "invoice", "synthetic", {"total": "1000.00"}, ("total_mismatch",))
    write_ground_truth(tmp_path / "g.json", gt)
    assert read_ground_truth(tmp_path / "g.json") == gt


def test_ground_truth_file_is_stable(tmp_path):
    gt = GroundTruth("inv-0001", "invoice", "synthetic", {"b": 1, "a": 2})
    write_ground_truth(tmp_path / "g.json", gt)
    text = (tmp_path / "g.json").read_text(encoding="utf-8")
    assert text.endswith("\n") and text.index('"a"') < text.index('"b"')
