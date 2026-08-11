"""Small deterministic OpenCV measurement primitives."""
from __future__ import annotations
from dataclasses import dataclass
import cv2
import numpy as np

@dataclass
class CircleDetection:
    center_px: tuple[float, float]
    radius_px: float
    confidence: float
    residual_px: float
    geometry: str = "circle"

def detect_circle(frame: np.ndarray, roi=None) -> CircleDetection | None:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame.copy()
    if roi:
        x, y, w, h = roi
        crop, origin = gray[y:y+h, x:x+w], (x, y)
    else:
        crop, origin = gray, (0, 0)
    if crop.size == 0:
        return None
    blur = cv2.medianBlur(crop, 5)
    circles = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT, 1.2, max(10, min(crop.shape)//8), param1=100, param2=28, minRadius=3, maxRadius=max(4, min(crop.shape)//2))
    if circles is None:
        return None
    x, y, r = max(circles[0], key=lambda c: c[2])
    edges = cv2.Canny(crop, 50, 150)
    yy, xx = np.where(edges > 0)
    residual = float(np.mean(np.abs(np.hypot(xx-x, yy-y)-r))) if len(xx) else float(r)
    confidence = float(max(0.0, min(1.0, 1.0 - residual / max(r, 1.0))) )
    return CircleDetection((float(x+origin[0]), float(y+origin[1])), float(r), confidence, residual)
