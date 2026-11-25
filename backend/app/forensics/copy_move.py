"""Copy-move / clone detection using ORB keypoints and RANSAC verification."""

from __future__ import annotations

import uuid

import cv2
import numpy as np

from app.forensics.common import load_page_bgr
from app.forensics.quality import scale_confidence
from app.models.schemas import PageImage, Region


def analyze_copy_move(
    page: PageImage,
    quality: float = 1.0,
    is_screenshot_like: bool = False,
) -> tuple[list[Region], float]:
    """Detect duplicated/cloned regions within a page via ORB + RANSAC."""
    bgr = load_page_bgr(page)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]

    orb = cv2.ORB.create(nfeatures=2000, fastThreshold=12)
    keypoints, descriptors = orb.detectAndCompute(gray, None)
    if descriptors is None or len(keypoints) < 12:
        return [], 0.0

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    knn_matches = matcher.knnMatch(descriptors, descriptors, k=4)

    min_spatial_dist = max(24.0, 0.04 * min(width, height))
    src_pts: list[tuple[float, float]] = []
    dst_pts: list[tuple[float, float]] = []

    for match_group in knn_matches:
        for m in match_group:
            if m.queryIdx == m.trainIdx or m.distance > 26:
                continue
            p1 = keypoints[m.queryIdx].pt
            p2 = keypoints[m.trainIdx].pt
            spatial_dist = float(np.hypot(p1[0] - p2[0], p1[1] - p2[1]))
            if spatial_dist >= min_spatial_dist:
                src_pts.append((float(p1[0]), float(p1[1])))
                dst_pts.append((float(p2[0]), float(p2[1])))
                break

    if len(src_pts) < 10:
        return [], 0.0

    src_arr = np.array(src_pts, dtype=np.float32)
    dst_arr = np.array(dst_pts, dtype=np.float32)
    _, inliers = cv2.estimateAffinePartial2D(
        src_arr, dst_arr, method=cv2.RANSAC, ransacReprojThreshold=4.0
    )
    if inliers is None:
        return [], 0.0

    inlier_mask = inliers.ravel().astype(bool)
    inlier_count = int(np.sum(inlier_mask))
    if inlier_count < 10:
        return [], 0.0

    raw_score = min(1.0, inlier_count / 24.0)
    scaled_score = scale_confidence(
        raw_score, quality, is_screenshot_like, screenshot_sensitive=True
    )

    regions: list[Region] = []
    for pts in (src_arr[inlier_mask], dst_arr[inlier_mask]):
        x0 = max(0.0, float(np.min(pts[:, 0]) - 16) / width)
        y0 = max(0.0, float(np.min(pts[:, 1]) - 16) / height)
        x1 = min(1.0, float(np.max(pts[:, 0]) + 16) / width)
        y1 = min(1.0, float(np.max(pts[:, 1]) + 16) / height)
        # Reject full-page degenerate boxes caused by repeating document borders/letters.
        if (x1 - x0) * (y1 - y0) > 0.35:
            continue
        regions.append(
            Region(
                id=uuid.uuid4().hex[:12],
                page=page.page,
                bbox=(round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)),
                score=scaled_score,
                reason="Keypoint matching indicates a potentially cloned or copy-moved region.",
            )
        )

    if not regions:
        return [], 0.0
    return regions, scaled_score
