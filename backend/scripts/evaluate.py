"""Evaluate Kavach pipeline across clean samples and tampered variants."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.forensics.common import compute_iou  # noqa: E402
from app.models.schemas import AnalysisContext, AnalysisResult  # noqa: E402
from app.pipeline import AnalysisPipeline  # noqa: E402
from app.utils.pdf import render_document_pages  # noqa: E402
from app.utils.validation import detect_mime_from_magic_bytes  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
SAMPLES_DIR = REPO_ROOT / "samples"
TAMPERED_DIR = SAMPLES_DIR / "tampered"
EVAL_DOC_PATH = REPO_ROOT / "docs" / "evaluation.md"


def _run_file(
    pipeline: AnalysisPipeline,
    file_path: Path,
    doc_id: str,
    tmp_dir: Path,
) -> AnalysisResult:
    raw = file_path.read_bytes()
    mime = detect_mime_from_magic_bytes(raw)
    pages = render_document_pages(file_path, mime, tmp_dir / doc_id, dpi=200)
    ctx = AnalysisContext(doc_id=doc_id, file_bytes=raw, mime=mime, pages=pages)
    return pipeline.run(ctx)


def _best_iou(result: AnalysisResult, gt_bbox: list[float] | None) -> float | None:
    if gt_bbox is None or len(gt_bbox) != 4:
        return None
    target = (float(gt_bbox[0]), float(gt_bbox[1]), float(gt_bbox[2]), float(gt_bbox[3]))
    if not result.regions:
        return 0.0
    return round(max(compute_iou(r.bbox, target) for r in result.regions), 4)


def main() -> None:
    """Run evaluation on clean and tampered files and write docs/evaluation.md."""
    gt_path = TAMPERED_DIR / "ground_truth.json"
    gt_records: list[dict[str, Any]] = (
        json.loads(gt_path.read_text(encoding="utf-8")) if gt_path.is_file() else []
    )
    clean_files = sorted(
        p for p in SAMPLES_DIR.glob("*") if p.is_file() and not p.name.startswith(".")
    )

    pipeline = AnalysisPipeline()
    rows: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="kavach_eval_") as tmp_str:
        tmp_dir = Path(tmp_str)

        for idx, cpath in enumerate(clean_files, start=1):
            res = _run_file(pipeline, cpath, f"clean_{idx}", tmp_dir)
            failed = sum(1 for c in res.checks if c.status == "fail")
            top_finding = res.findings[0].title if res.findings else "(none)"
            rows.append(
                {
                    "file": cpath.name,
                    "kind": "clean",
                    "variant": "original",
                    "edit_description": "Clean original",
                    "doc_type": res.doc_type,
                    "risk_score": res.risk_score,
                    "risk_level": res.risk_level,
                    "failed_checks": failed,
                    "top_finding": top_finding,
                    "best_iou": None,
                    "signals": [f"{s.signal}:{s.contribution}" for s in res.score_breakdown],
                    "failed_check_names": [c.name for c in res.checks if c.status == "fail"],
                }
            )

        for idx, rec in enumerate(gt_records, start=1):
            tpath = TAMPERED_DIR / str(rec["file"])
            if not tpath.is_file():
                continue
            res = _run_file(pipeline, tpath, f"tamp_{idx}", tmp_dir)
            failed = sum(1 for c in res.checks if c.status == "fail")
            top_finding = res.findings[0].title if res.findings else "(none)"
            iou = _best_iou(res, rec.get("bbox"))
            rows.append(
                {
                    "file": tpath.name,
                    "kind": "tampered",
                    "variant": str(rec.get("variant", "original")),
                    "edit_description": str(rec["edit_description"]),
                    "doc_type": res.doc_type,
                    "risk_score": res.risk_score,
                    "risk_level": res.risk_level,
                    "failed_checks": failed,
                    "top_finding": top_finding,
                    "best_iou": iou,
                    "signals": [f"{s.signal}:{s.contribution}" for s in res.score_breakdown],
                    "failed_check_names": [c.name for c in res.checks if c.status == "fail"],
                }
            )

    clean_rows = [r for r in rows if r["kind"] == "clean"]
    tamp_rows = [r for r in rows if r["kind"] == "tampered"]
    orig_tamp = [r for r in tamp_rows if r["variant"] == "original"]
    wa_tamp = [r for r in tamp_rows if r["variant"] == "whatsapp"]

    def _det_rate(items: list[dict[str, Any]]) -> float:
        if not items:
            return 0.0
        hits = sum(1 for r in items if r["risk_level"] in {"MEDIUM", "HIGH"})
        return round(100.0 * hits / len(items), 1)

    def _mean_iou(items: list[dict[str, Any]]) -> float:
        vals = [float(r["best_iou"]) for r in items if r["best_iou"] is not None]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    fp_rate = _det_rate(clean_rows)
    det_rate = _det_rate(tamp_rows)
    mean_iou = _mean_iou(tamp_rows)

    misses = [r for r in tamp_rows if r["risk_level"] == "LOW"]
    false_positives = [r for r in clean_rows if r["risk_level"] in {"MEDIUM", "HIGH"}]

    md_lines: list[str] = [
        "# Kavach Evaluation Report",
        "",
        "## Results Table",
        "",
        "| File | Variant | Edit Description | Doc Type | Score | Level | Failed Checks | Top Finding | Best IoU |",
        "| :--- | :--- | :--- | :--- | ---: | :--- | ---: | :--- | ---: |",
    ]
    for r in rows:
        iou_str = f"{r['best_iou']:.3f}" if r["best_iou"] is not None else "—"
        md_lines.append(
            f"| `{r['file']}` | {r['variant']} | {r['edit_description']} | "
            f"{r['doc_type']} | {r['risk_score']} | {r['risk_level']} | "
            f"{r['failed_checks']} | {r['top_finding']} | {iou_str} |"
        )

    md_lines.extend(
        [
            "",
            "## Summary Metrics",
            "",
            f"- **Detection Rate (Tampered MEDIUM/HIGH)**: {det_rate}% ({sum(1 for r in tamp_rows if r['risk_level'] in {'MEDIUM', 'HIGH'})}/{len(tamp_rows)})",
            f"- **False-Positive Rate (Clean MEDIUM/HIGH)**: {fp_rate}% ({len(false_positives)}/{len(clean_rows)})",
            f"- **Mean IoU on Text Edits**: {mean_iou:.4f}",
            f"- **Original-Quality Tampered**: detection={_det_rate(orig_tamp)}%, mean IoU={_mean_iou(orig_tamp):.4f}",
            f"- **WhatsApp-Compressed Tampered**: detection={_det_rate(wa_tamp)}%, mean IoU={_mean_iou(wa_tamp):.4f}",
            "",
            "## Misses (Tampered Scored LOW)",
            "",
        ]
    )
    if not misses:
        md_lines.append("- None")
    else:
        for m in misses:
            md_lines.append(
                f"- `{m['file']}` ({m['edit_description']}): score={m['risk_score']}, "
                f"signals={m['signals']}, failed_checks={m['failed_check_names']}"
            )

    md_lines.extend(["", "## False Positives (Clean Scored MEDIUM/HIGH)", ""])
    if not false_positives:
        md_lines.append("- None")
    else:
        for fp in false_positives:
            md_lines.append(
                f"- `{fp['file']}`: score={fp['risk_score']} ({fp['risk_level']}), "
                f"signals={fp['signals']}, failed_checks={fp['failed_check_names']}"
            )

    report = "\n".join(md_lines) + "\n"
    EVAL_DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVAL_DOC_PATH.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
