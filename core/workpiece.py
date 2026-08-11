"""Serializable workpiece results for downstream G-code generation."""
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path

def export_parameters(path: str | Path, *, zero=None, angle_deg=None, center=None, points=None, holes=None, dimensions=None, calibration_profile="") -> Path:
    payload = {"zero": zero or {}, "workpiece_angle_deg": angle_deg, "workpiece_center": center or {}, "points": points or {}, "holes": holes or [], "dimensions": dimensions or {}, "timestamp": datetime.now(timezone.utc).isoformat(), "calibration_profile": calibration_profile}
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return target
