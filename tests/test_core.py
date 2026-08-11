import json
import numpy as np
import cv2
from core.coordinates import CoordinateProfile
from core.vision import detect_circle
from core.workpiece import export_parameters

def test_coordinate_roundtrip_and_spindle_offset():
    p = CoordinateProfile(.1, .2, 100, 80, 35, -18)
    x, y = p.pixel_to_camera_mm(110, 70)
    assert (x, y) == (1.0, 2.0)
    assert p.camera_mm_to_pixel(x, y) == (110, 70)
    assert p.camera_to_machine(x, y) == (36, -16)

def test_detect_circle():
    image = np.zeros((240, 320), dtype=np.uint8)
    cv2.circle(image, (160, 120), 35, 255, 3)
    result = detect_circle(image)
    assert result is not None
    assert abs(result.center_px[0] - 160) < 4
    assert abs(result.center_px[1] - 120) < 4
    assert result.confidence >= 0

def test_export_parameters(tmp_path):
    path = export_parameters(tmp_path / "params.json", zero={"x": 1, "y": 2}, angle_deg=-1.2)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["zero"]["x"] == 1
    assert data["workpiece_angle_deg"] == -1.2
