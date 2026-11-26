"""Regression test uploading every document in samples/ via POST /api/analyze."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "samples"
IGNORED_FILES = {".gitkeep", "README.md"}


def _sample_files() -> list[Path]:
    if not SAMPLES_DIR.exists():
        return []
    return sorted(
        p for p in SAMPLES_DIR.iterdir() if p.is_file() and p.name not in IGNORED_FILES
    )


def test_upload_each_sample_completes_as_done(tmp_path: Path) -> None:
    files = _sample_files()
    if not files:
        pytest.skip("No sample documents present in samples/")

    headers = {"X-Kavach-Key": "test-key"}
    app = create_app(
        Settings(temp_dir=tmp_path, data_dir=tmp_path, api_keys=("test-key",))
    )
    with TestClient(app) as client:
        for sample_path in files:
            resp = client.post(
                "/api/analyze",
                headers=headers,
                files={
                    "file": (
                        sample_path.name,
                        sample_path.read_bytes(),
                        "application/octet-stream",
                    )
                },
            )
            assert resp.status_code == 200
            queued = resp.json()
            assert queued["status"] == "queued"
            doc_id = queued["doc_id"]

            final_status = None
            for _ in range(300):
                poll = client.get(f"/api/analysis/{doc_id}", headers=headers)
                assert poll.status_code == 200
                body = poll.json()
                if body["status"] in {"done", "failed"}:
                    final_status = body
                    break
                time.sleep(0.2)

            assert final_status is not None
            assert final_status["status"] == "done"
            assert final_status["result"] is not None
