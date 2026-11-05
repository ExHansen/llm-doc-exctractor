from pathlib import Path

from docex.groundtruth import read_ground_truth
from docex.synthetic.generator import generate_dataset


def test_generate_dataset_files_and_determinism(tmp_path):
    a = generate_dataset(6, 42, 0.5, 0.5, tmp_path / "a")
    b = generate_dataset(6, 42, 0.5, 0.5, tmp_path / "b")
    assert [m.doc_id for m in a] == [f"inv-{i:04d}" for i in range(1, 7)]
    for m in a:
        assert (tmp_path / "a" / m.path).exists() and not Path(m.path).is_absolute()
        assert "\\" not in m.path and "\\" not in m.gt_path
        assert (tmp_path / "a" / m.gt_path).read_bytes() == (
            tmp_path / "b" / m.gt_path
        ).read_bytes()
    assert {m.quality for m in a} <= {"clean", "scan_light", "scan_heavy"}
    assert a == b


def test_ground_truth_matches_meta(tmp_path):
    metas = generate_dataset(4, 42, 1.0, 0.0, tmp_path)
    for m in metas:
        gt = read_ground_truth(tmp_path / m.gt_path)
        assert gt.doc_id == m.doc_id and gt.injected_faults == m.injected_faults
        assert gt.source == "synthetic" and gt.doc_type == "invoice" and len(m.injected_faults) == 1
    assert not list((tmp_path / "documents" / "synthetic").glob("*.clean.pdf"))
