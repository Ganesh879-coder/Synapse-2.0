"""Production security, persistence, privacy, and reliability tests."""

from __future__ import annotations

import io
import logging
import time
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.api.jobs import AnalysisJobStore
from app.config import Settings
from app.main import create_app


def _png_bytes(text: str = "SECRET_PII_JOHN_DOE_9999") -> bytes:
    img = Image.new("RGB", (300, 120), color=(250, 250, 250))
    draw = ImageDraw.Draw(img)
    draw.text((20, 40), text, fill=(10, 10, 10))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_auth_security_headers_and_metrics(tmp_path: Path) -> None:
    app = create_app(
        Settings(temp_dir=tmp_path, data_dir=tmp_path, api_keys=("secret-key-123",))
    )
    with TestClient(app) as client:
        # /health is public and includes security headers
        h = client.get("/health")
        assert h.status_code == 200
        assert h.headers["X-Content-Type-Options"] == "nosniff"
        assert h.headers["X-Frame-Options"] == "DENY"
        assert h.headers["Referrer-Policy"] == "no-referrer"
        assert "script-src 'self'" in h.headers["Content-Security-Policy"]

        # Protected routes reject missing/invalid keys
        assert client.get("/ready").status_code == 401
        assert client.get("/api/metrics").status_code == 401
        assert (
            client.post(
                "/api/analyze",
                files={"file": ("a.png", _png_bytes(), "image/png")},
            ).status_code
            == 401
        )

        headers = {"X-Kavach-Key": "secret-key-123"}
        assert client.get("/ready", headers=headers).status_code == 200
        metrics_resp = client.get("/api/metrics", headers=headers)
        assert metrics_resp.status_code == 200
        assert "kavach_jobs_started_total" in metrics_resp.text


def test_rate_limit_oversized_malformed_and_path_traversal(tmp_path: Path) -> None:
    headers = {"X-Kavach-Key": "rl-key"}
    headers2 = {"X-Kavach-Key": "rl-key-2"}
    app = create_app(
        Settings(
            temp_dir=tmp_path,
            data_dir=tmp_path,
            api_keys=("rl-key", "rl-key-2"),
            rate_limit="2/minute",
            max_upload_bytes=1024,
        )
    )
    with TestClient(app) as client:
        # Oversized -> 413
        big = client.post(
            "/api/analyze",
            headers=headers,
            files={"file": ("big.png", b"\x89PNG\r\n\x1a\n" + b"0" * 2048, "image/png")},
        )
        assert big.status_code == 413

        # Malformed magic bytes -> 415
        bad = client.post(
            "/api/analyze",
            headers=headers,
            files={"file": ("bad.png", b"NOT_PNG", "image/png")},
        )
        assert bad.status_code == 415

        # Path traversal -> 400 or 404
        trav = client.get("/api/artifacts/abc123/..%2Fsecret.png", headers=headers)
        assert trav.status_code in {400, 404}

        # Rate limit -> 3rd valid request with a key returns 429
        buf = io.BytesIO()
        Image.new("RGB", (16, 16)).save(buf, format="PNG")
        tiny = buf.getvalue()
        r1 = client.post(
            "/api/analyze", headers=headers2, files={"file": ("1.png", tiny, "image/png")}
        )
        r2 = client.post(
            "/api/analyze", headers=headers2, files={"file": ("2.png", tiny, "image/png")}
        )
        r3 = client.post(
            "/api/analyze", headers=headers2, files={"file": ("3.png", tiny, "image/png")}
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 429


def test_encrypted_pdf_and_page_limit(tmp_path: Path) -> None:
    headers = {"X-Kavach-Key": "pdf-key"}
    app = create_app(
        Settings(temp_dir=tmp_path, data_dir=tmp_path, api_keys=("pdf-key",), max_pdf_pages=2)
    )
    # Create encrypted PDF
    doc = pymupdf.open()
    doc.new_page().insert_text((20, 20), "Secret")
    enc_bytes = bytes(
        doc.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="owner123",
            user_pw="user123",
        )
    )
    doc.close()

    with TestClient(app) as client:
        up = client.post(
            "/api/analyze",
            headers=headers,
            files={"file": ("enc.pdf", enc_bytes, "application/pdf")},
        )
        assert up.status_code == 200
        doc_id = up.json()["doc_id"]
        poll_body = {}
        for _ in range(100):
            poll = client.get(f"/api/analysis/{doc_id}", headers=headers)
            assert poll.status_code == 200
            poll_body = poll.json()
            if poll_body["status"] in {"done", "failed"}:
                break
            time.sleep(0.05)
        assert poll_body.get("status") == "failed"
        assert "encrypted" in (poll_body.get("error") or "").lower()


def test_delete_ttl_restart_recovery_and_no_pii_in_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db_path = tmp_path / "kavach.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    # Restart recovery: a job left in processing becomes failed on startup
    store1 = AnalysisJobStore(db_url=db_url, retention_seconds=60, uploads_dir=tmp_path)
    store1.create_queued("interrupted1")
    store1.set_stage("interrupted1", "reading")
    store2 = AnalysisJobStore(db_url=db_url, retention_seconds=60, uploads_dir=tmp_path)
    recovered = store2.recover_interrupted_jobs()
    assert recovered == 1
    status = store2.get("interrupted1")
    assert status is not None
    assert status.status == "failed"

    # TTL eviction removes expired rows
    assert store2.cleanup_expired(now=time.time() + 120) >= 1
    assert store2.get("interrupted1") is None

    # No document text in logs + DELETE /api/analysis/{id}
    headers = {"X-Kavach-Key": "priv-key"}
    app = create_app(
        Settings(temp_dir=tmp_path, data_dir=tmp_path, api_keys=("priv-key",))
    )
    caplog.set_level(logging.INFO, logger="kavach")
    with TestClient(app) as client:
        up = client.post(
            "/api/analyze",
            headers=headers,
            files={"file": ("pii.png", _png_bytes("SENSITIVE_PAN_ABCDE1234F"), "image/png")},
        )
        assert up.status_code == 200
        doc_id = up.json()["doc_id"]
        assert "SENSITIVE_PAN_ABCDE1234F" not in caplog.text
        del_resp = client.delete(f"/api/analysis/{doc_id}", headers=headers)
        assert del_resp.status_code == 200
        assert client.get(f"/api/analysis/{doc_id}", headers=headers).status_code == 404


def test_gitignore_and_dockerignore_exclude_sensitive_paths() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    gi = (repo_root / ".gitignore").read_text(encoding="utf-8")
    di = (repo_root / ".dockerignore").read_text(encoding="utf-8")
    for pattern in ("samples/", ".env", "*.db"):
        assert pattern in gi
        assert pattern in di
