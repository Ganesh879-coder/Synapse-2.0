"""API tests for queued -> done flow, page/heatmap artifacts, and ReportLab PDF."""

from __future__ import annotations

import io
import time
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.config import Settings
from app.main import create_app


def _make_sample_png() -> bytes:
    img = Image.new("RGB", (320, 180), color=(248, 248, 248))
    draw = ImageDraw.Draw(img)
    draw.text((20, 40), "Payment Receipt Receipt No PR-101 Amount 500.00", fill=(20, 20, 20))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_queued_to_done_flow_and_pdf_report(tmp_path: Path) -> None:
    headers = {"X-Kavach-Key": "test-key"}
    app = create_app(
        Settings(temp_dir=tmp_path, data_dir=tmp_path, api_keys=("test-key",))
    )
    with TestClient(app) as client:
        upload = client.post(
            "/api/analyze",
            headers=headers,
            files={"file": ("receipt.png", _make_sample_png(), "image/png")},
        )
        assert upload.status_code == 200
        queued = upload.json()
        assert queued["status"] == "queued"
        doc_id = queued["doc_id"]

        payload = {}
        for _ in range(100):
            poll = client.get(f"/api/analysis/{doc_id}", headers=headers)
            assert poll.status_code == 200
            payload = poll.json()
            if payload["status"] in {"done", "failed"}:
                break
            time.sleep(0.1)
        assert payload.get("status") == "done"
        result = payload["result"]
        assert result["doc_id"] == doc_id
        assert len(result["pages"]) == 1
        assert result["pages"][0]["image_url"] == f"/api/analysis/{doc_id}/page/1"
        assert result["summary"] is not None
        assert result["summary"]["disclaimer"]

        page_resp = client.get(f"/api/analysis/{doc_id}/page/1", headers=headers)
        assert page_resp.status_code == 200
        assert page_resp.headers["content-type"] == "image/png"

        heatmap_resp = client.get(f"/api/analysis/{doc_id}/heatmap/1", headers=headers)
        assert heatmap_resp.status_code == 200
        assert heatmap_resp.headers["content-type"] == "image/png"

        pdf_resp = client.get(f"/api/analysis/{doc_id}/report.pdf", headers=headers)
        assert pdf_resp.status_code == 200
        assert pdf_resp.headers["content-type"] == "application/pdf"
        assert pdf_resp.content.startswith(b"%PDF-")

        missing_resp = client.get("/api/analysis/doesnotexist123", headers=headers)
        assert missing_resp.status_code == 404
        assert "error" in missing_resp.json()
        assert "detail" in missing_resp.json()
