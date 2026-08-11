"""Explicit pixel, camera-mm and machine-coordinate transformations."""
from dataclasses import dataclass

@dataclass
class CoordinateProfile:
    mm_per_pixel_x: float = 0.0
    mm_per_pixel_y: float = 0.0
    target_u: float = 0.0
    target_v: float = 0.0
    camera_to_spindle_x: float = 0.0
    camera_to_spindle_y: float = 0.0

    def pixel_to_camera_mm(self, u: float, v: float) -> tuple[float, float]:
        if self.mm_per_pixel_x <= 0 or self.mm_per_pixel_y <= 0:
            raise ValueError("Pixel/mm calibration is missing or invalid")
        return ((u - self.target_u) * self.mm_per_pixel_x,
                (self.target_v - v) * self.mm_per_pixel_y)

    def camera_mm_to_pixel(self, x: float, y: float) -> tuple[float, float]:
        if self.mm_per_pixel_x <= 0 or self.mm_per_pixel_y <= 0:
            raise ValueError("Pixel/mm calibration is missing or invalid")
        return (self.target_u + x / self.mm_per_pixel_x,
                self.target_v - y / self.mm_per_pixel_y)

    def camera_to_machine(self, camera_x: float, camera_y: float) -> tuple[float, float]:
        return (camera_x + self.camera_to_spindle_x,
                camera_y + self.camera_to_spindle_y)

    def machine_to_camera(self, machine_x: float, machine_y: float) -> tuple[float, float]:
        return (machine_x - self.camera_to_spindle_x,
                machine_y - self.camera_to_spindle_y)
