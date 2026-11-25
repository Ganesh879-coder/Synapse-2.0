"""Tests for pipeline orchestration, timeout/fault isolation, and API endpoints."""

from __future__ import annotations

import io
import os
import time
from pathlib import Path

import pymupdf
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from app.models.schemas import AnalysisContext, AnalyzerOutput, CheckResult, PageImage
from app.pipeline import PIPELINE_ORDER, AnalysisPipeline
from app.utils.storage import TempDocumentStore


class _BrokenAnalyzer:
    name = "broken"

    def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        _ = ctx
        raise RuntimeError("simulated analyzer crash")


class _SlowAnalyzer:
    name = "slow"

    def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        _ = ctx
        time.sleep(0.5)
        return AnalyzerOutput(analyzer_name=self.name)


class _HealthyAnalyzer:
    name = "healthy"

    def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        _ = ctx
        return AnalyzerOutput(
            analyzer_name=self.name,
            checks=[CheckResult(name="healthy_check", status="pass", detail="ok")],
        )


def _make_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=(255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _make_pdf_bytes() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=72, height=72)
    page.insert_text((10, 36), "Test")
    data = bytes(doc.tobytes())
    doc.close()
    return data


def test_pipeline_order_is_fixed() -> None:
    assert PIPELINE_ORDER == ("ocr", "classify", "rules", "forensics", "scoring", "explain")
    default_pipeline = AnalysisPipeline()
    assert [a.name for a in default_pipeline.analyzers] == [
        "ocr",
        "classify",
        "rules",
        "forensics",
    ]


def test_pipeline_isolates_failing_and_timed_out_analyzers(tmp_path: Path) -> None:
    png_bytes = _make_png_bytes()
    page_img = tmp_path / "page_1.png"
    page_img.write_bytes(png_bytes)
    ctx = AnalysisContext(
        doc_id="doc123",
        file_bytes=png_bytes,
        mime="image/png",
        pages=[PageImage(page=1, image_path=page_img, width=64, height=64)],
        doc_type="invoice",
    )

    pipeline = AnalysisPipeline(
        analyzers=[_BrokenAnalyzer(), _SlowAnalyzer(), _HealthyAnalyzer()],
        timeout_seconds=0.05,
    )
    result = pipeline.run(ctx)

    assert result.doc_id == "doc123"
    assert result.risk_score == 0
    assert result.risk_level == "LOW"
    assert any(c.name == "analyzer:broken" and c.status == "skipped" for c in result.checks)
    assert any(c.name == "analyzer:slow" and c.status == "skipped" for c in result.checks)
    assert any(c.name == "healthy_check" and c.status == "pass" for c in result.checks)


def test_temp_store_deletes_expired_dirs(tmp_path: Path) -> None:
    store = TempDocumentStore(base_dir=tmp_path, retention_seconds=3600)
    old_dir = store.create_doc_dir("expired_doc")
    fresh_dir = store.create_doc_dir("fresh_doc")

    old_time = time.time() - 3700
    os.utime(old_dir, (old_time, old_time))

    removed = store.cleanup_expired()
    assert removed == 1
    assert not old_dir.exists()
    assert fresh_dir.exists()


def test_health_and_analyze_endpoints(tmp_path: Path) -> None:
    app = create_app(Settings(temp_dir=tmp_path))
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        png_resp = client.post(
            "/api/analyze",
            files={"file": ("sample.png", _make_png_bytes(), "image/png")},
            data={"doc_type": "invoice"},
        )
        assert png_resp.status_code == 200
        queued = png_resp.json()
        assert queued["status"] == "queued"
        assert "doc_id" in queued

        status_resp = client.get(f"/api/analysis/{queued['doc_id']}")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "done"
        assert status_resp.json()["result"]["risk_score"] == 0
        assert status_resp.json()["result"]["risk_level"] == "LOW"

        pdf_resp = client.post(
            "/api/analyze",
            files={"file": ("sample.pdf", _make_pdf_bytes(), "application/pdf")},
        )
        assert pdf_resp.status_code == 200
        assert pdf_resp.json()["status"] == "queued"

        bad_resp = client.post(
            "/api/analyze",
            files={"file": ("fake.png", b"NOT_A_REAL_PNG_FILE", "image/png")},
        )
        assert bad_resp.status_code == 415
