"""Tests for synthetic tamper dataset generation and ground_truth.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from make_tampered import _discover_samples, generate_tampered_dataset  # noqa: E402

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "samples"


def test_make_tampered_creates_expected_files_and_valid_bboxes(tmp_path: Path) -> None:
    discovered = _discover_samples(SAMPLES_DIR)
    if not discovered:
        pytest.skip("No sample documents present in samples/")

    out_dir = tmp_path / "tampered"
    records = generate_tampered_dataset(samples_dir=SAMPLES_DIR, tampered_dir=out_dir)
    assert len(records) >= 2

    gt_file = out_dir / "ground_truth.json"
    assert gt_file.is_file()
    loaded = json.loads(gt_file.read_text(encoding="utf-8"))
    assert len(loaded) == len(records)

    for rec in loaded:
        assert (out_dir / rec["file"]).is_file()
        x0, y0, x1, y1 = rec["bbox"]
        assert 0.0 <= x0 < x1 <= 1.0
        assert 0.0 <= y0 < y1 <= 1.0
