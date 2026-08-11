"""Vision overlays, mouse tools, and camera calibration for ProbeCAM CNC."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QLabel, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem


class VisionCalibrationController(QObject):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window
        root = window.root_widget
        self.preview: QLabel = root.findChild(QLabel, "previewLabel")
        self.result_label: QLabel = root.findChild(QLabel, "visionResultLabel")
        self.calibration_label: QLabel = root.findChild(QLabel, "calibrationInfoLabel")
        self.samples_label: QLabel = root.findChild(QLabel, "calibrationSamplesLabel")
        self.canny_low: QSpinBox = root.findChild(QSpinBox, "cannyLowSpin")
        self.canny_high: QSpinBox = root.findChild(QSpinBox, "cannyHighSpin")
        self.min_area: QSpinBox = root.findChild(QSpinBox, "minAreaSpin")
        self.board_cols: QSpinBox = root.findChild(QSpinBox, "boardColsSpin")
        self.board_rows: QSpinBox = root.findChild(QSpinBox, "boardRowsSpin")
        self.square_size: QDoubleSpinBox = root.findChild(QDoubleSpinBox, "squareSizeSpin")
        self.reference_length: QDoubleSpinBox = root.findChild(QDoubleSpinBox, "referenceLengthSpin")
        self.show_edges: QCheckBox = root.findChild(QCheckBox, "showEdgesCheck")
        self.show_contours: QCheckBox = root.findChild(QCheckBox, "showContoursCheck")
        self.mouse_roi: QCheckBox = root.findChild(QCheckBox, "mouseRoiCheck")
        self.mouse_line: QCheckBox = root.findChild(QCheckBox, "mouseLineCheck")
        self.mouse_point: QCheckBox = root.findChild(QCheckBox, "mousePointCheck")
        self.fisheye_model: QCheckBox = root.findChild(QCheckBox, "fisheyeCalibrationCheck")
        self.apply_undistort: QCheckBox = root.findChild(QCheckBox, "applyUndistortCheck")
        self.points_table: QTableWidget = root.findChild(QTableWidget, "measurementPointsTable")
        self.roi: Optional[tuple[int, int, int, int]] = None
        self.manual_line: Optional[tuple[int, int, int, int]] = None
        self.selected_contour: Optional[np.ndarray] = None
        self.measurement_points: list[dict] = []
        self.drag_start: Optional[tuple[int, int]] = None
        self.drag_current: Optional[tuple[int, int]] = None
        self.object_points: list[np.ndarray] = []
        self.image_points: list[np.ndarray] = []
        self.image_size: Optional[tuple[int, int]] = None
        self.calibration_data: dict = {}
        self.calibration_path = window.app_dir / "data" / "camera_calibration.json"
        if not all((self.preview, self.result_label, self.calibration_label)):
            raise RuntimeError("Vision/Calibration widgets are missing from main_window.ui")
        self.preview.setMouseTracking(True)
        self.preview.installEventFilter(self)
        self.mouse_roi.toggled.connect(lambda checked: self._exclusive_mode(self.mouse_roi, self.mouse_line, checked))
        self.mouse_line.toggled.connect(lambda checked: self._exclusive_mode(self.mouse_line, self.mouse_roi, checked))
        self.mouse_point.toggled.connect(self._point_mode_changed)
        bindings = {
            "processButton": self.process_current_frame,
            "detectEdgesButton": self.detect_edges,
            "detectContourButton": self.detect_contour_angle,
            "selectRoiButton": lambda: self.mouse_roi.setChecked(True),
            "selectLineButton": lambda: self.mouse_line.setChecked(True),
            "checkerboardButton": self.capture_checkerboard,
            "charucoButton": self.capture_charuco,
            "pixelMmButton": self.calculate_pixel_mm,
            "calibrateCameraButton": self.calculate_camera_calibration,
            "saveCalibrationButton": self.save_calibration,
            "loadCalibrationButton": self.load_calibration,
            "fitRoiContourButton": self.fit_contour_to_roi,
            "deletePointButton": self.delete_selected_point,
            "clearPointsButton": self.clear_points,
            "cancelSelectionButton": self.cancel_selection,
        }
        for name, handler in bindings.items():
            button = root.findChild(QPushButton, name)
            if button is None:
                raise RuntimeError(f"{name} is missing from main_window.ui")
            button.clicked.connect(handler)
        self.points_table.horizontalHeader().setStretchLastSection(True)
        self.points_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.points_table.installEventFilter(self)

    def _exclusive_mode(self, active: QCheckBox, other: QCheckBox, checked: bool) -> None:
        if checked:
            other.setChecked(False)
            self.mouse_point.setChecked(False)
            active.setText(active.text().split(" [")[0] + " [АКТИВНО]")
        else:
            active.setText(active.text().split(" [")[0])

    def _point_mode_changed(self, checked: bool) -> None:
        if checked:
            self.mouse_roi.setChecked(False)
            self.mouse_line.setChecked(False)
            self.mouse_point.setText("Додавати точки мишею [АКТИВНО]")
        else:
            self.mouse_point.setText("Додавати точки мишею")

    def calibration_status(self) -> str:
        return (
            "Калібрування об’єктива: укажіть внутрішні стовпці/рядки шахівниці та розмір квадрата. "
            "Покажіть усю шахівницю в різних місцях і під різними кутами, зробіть 8–15 зразків, "
            "потім розрахуйте калібрування камери. «Риб’яче око» вмикайте лише для відповідного об’єктива.\n"
            "Калібрування масштабу: покладіть у площині деталі лінійку або еталон відомої довжини. "
            "У вкладці «Технічний зір» увімкніть «Малювати лінію мишею» та проведіть лінію точно між "
            "двома мітками. Тут введіть реальну довжину в мм і натисніть «Розрахувати піксель/мм».\n"
            "Після перевірки збережіть калібрування. Воно автоматично завантажиться з камерою."
        )

    def frame_gray(self) -> Optional[np.ndarray]:
        frame = self.window.latest_frame
        if frame is None:
            self.window.log("Vision: no camera frame available")
            self.result_label.setText("Запустіть камеру перед аналізом або калібруванням.")
            return None
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    def eventFilter(self, watched, event):
        if watched is self.points_table and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Delete:
            self.delete_selected_point()
            return True
        if watched is self.preview and (self.mouse_roi.isChecked() or self.mouse_line.isChecked() or self.mouse_point.isChecked()):
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self.drag_start = self._label_to_image(event.position().x(), event.position().y())
                self.drag_current = self.drag_start
                if self.mouse_point.isChecked():
                    self.add_measurement_point(*self.drag_start)
                    self.drag_start = None
                    self.drag_current = None
                return True
            if event.type() == QEvent.MouseMove and self.drag_start is not None:
                self.drag_current = self._label_to_image(event.position().x(), event.position().y())
                return True
            if event.type() == QEvent.MouseButtonRelease and self.drag_start is not None:
                end = self._label_to_image(event.position().x(), event.position().y())
                x1, y1 = self.drag_start
                x2, y2 = end
                if self.mouse_roi.isChecked():
                    self.roi = (min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
                    self.result_label.setText(f"ROI: x={self.roi[0]}, y={self.roi[1]}, w={self.roi[2]}, h={self.roi[3]}")
                    self.fit_contour_to_roi()
                else:
                    self.manual_line = (x1, y1, x2, y2)
                    angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
                    self.result_label.setText(f"Кут ручної лінії: {angle:.3f}°")
                self.drag_start = None
                self.drag_current = None
                return True
        return super().eventFilter(watched, event)

    def cancel_selection(self) -> None:
        self.mouse_roi.setChecked(False)
        self.mouse_line.setChecked(False)
        self.mouse_point.setChecked(False)
        self.drag_start = None
        self.drag_current = None
        self.roi = None
        self.manual_line = None
        self.selected_contour = None
        self.result_label.setText("Виділення та накладання очищено")

    def _label_to_image(self, lx: float, ly: float) -> tuple[int, int]:
        frame = self.window.latest_frame
        if frame is None:
            return 0, 0
        ih, iw = frame.shape[:2]
        lw, lh = max(1, self.preview.width()), max(1, self.preview.height())
        scale = min(lw / iw, lh / ih)
        draw_w, draw_h = iw * scale, ih * scale
        ox, oy = (lw - draw_w) / 2, (lh - draw_h) / 2
        return (int(np.clip((lx - ox) / scale, 0, iw - 1)), int(np.clip((ly - oy) / scale, 0, ih - 1)))

    def overlay_frame(self, frame: np.ndarray) -> np.ndarray:
        output = self.undistort_frame(frame) if self.apply_undistort.isChecked() else frame.copy()
        frame = output
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        low, high = self.canny_low.value(), max(self.canny_low.value() + 1, self.canny_high.value())
        edges = cv2.Canny(gray, low, high)
        if self.show_edges.isChecked():
            output[edges > 0] = (0, 255, 255)
        if self.show_contours.isChecked():
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            valid = [c for c in contours if cv2.contourArea(c) >= self.min_area.value()]
            cv2.drawContours(output, valid, -1, (0, 255, 0), 2)
            if valid:
                contour = max(valid, key=cv2.contourArea)
                rect = cv2.minAreaRect(contour)
                box = np.int32(cv2.boxPoints(rect))
                cv2.polylines(output, [box], True, (255, 128, 0), 2)
                cv2.putText(output, f"{rect[2]:.2f} deg", tuple(box[0]), cv2.FONT_HERSHEY_SIMPLEX, .65, (255, 128, 0), 2)
        if self.roi:
            x, y, w, h = self.roi
            cv2.rectangle(output, (x, y), (x + w, y + h), (255, 0, 255), 2)
        if self.manual_line:
            x1, y1, x2, y2 = self.manual_line
            cv2.line(output, (x1, y1), (x2, y2), (0, 0, 255), 2)
        if self.selected_contour is not None:
            cv2.drawContours(output, [self.selected_contour], -1, (255, 0, 255), 3)
        for index, point in enumerate(self.measurement_points, 1):
            p = (int(point["pixel_x"]), int(point["pixel_y"]))
            cv2.circle(output, p, 5, (0, 0, 255), -1)
            cv2.putText(output, f"P{index}", (p[0] + 7, p[1] - 7), cv2.FONT_HERSHEY_SIMPLEX, .55, (0, 0, 255), 2)
        for first, second in zip(self.measurement_points, self.measurement_points[1:]):
            cv2.line(output, (int(first["pixel_x"]), int(first["pixel_y"])), (int(second["pixel_x"]), int(second["pixel_y"])), (0, 128, 255), 2)
        if self.drag_start and self.drag_current:
            if self.mouse_roi.isChecked():
                cv2.rectangle(output, self.drag_start, self.drag_current, (255, 0, 255), 2)
            else:
                cv2.line(output, self.drag_start, self.drag_current, (0, 0, 255), 2)
        return output

    def undistort_frame(self, frame: np.ndarray) -> np.ndarray:
        if "camera_matrix" not in self.calibration_data or "distortion" not in self.calibration_data:
            return frame.copy()
        matrix = np.asarray(self.calibration_data["camera_matrix"], dtype=np.float64)
        distortion = np.asarray(self.calibration_data["distortion"], dtype=np.float64)
        if self.calibration_data.get("model") == "fisheye":
            return cv2.fisheye.undistortImage(frame, matrix, distortion, Knew=matrix)
        return cv2.undistort(frame, matrix, distortion)

    def process_current_frame(self) -> None:
        self.detect_contour_angle()

    def detect_edges(self) -> None:
        gray = self.frame_gray()
        if gray is None:
            return
        edges = cv2.Canny(gray, self.canny_low.value(), self.canny_high.value())
        self.show_edges.setChecked(True)
        self.result_label.setText(f"Краї: {cv2.countNonZero(edges)} пікселів; пороги {self.canny_low.value()}/{self.canny_high.value()}")

    def detect_contour_angle(self) -> None:
        gray = self.frame_gray()
        if gray is None:
            return
        edges = cv2.Canny(gray, self.canny_low.value(), self.canny_high.value())
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        valid = [c for c in contours if cv2.contourArea(c) >= self.min_area.value()]
        if not valid:
            self.result_label.setText("Не знайдено контуру більшого за мінімальну площу")
            return
        contour = max(valid, key=cv2.contourArea)
        area = cv2.contourArea(contour)
        angle = cv2.minAreaRect(contour)[2]
        confidence = min(1.0, area / max(1.0, gray.size * .20))
        self.result_label.setText(f"Контурів: {len(valid)}; площа={area:.1f} пкс²; кут={angle:.3f}°; достовірність={confidence:.3f}")

    def fit_contour_to_roi(self) -> None:
        gray = self.frame_gray()
        if gray is None or self.roi is None:
            self.result_label.setText("Спочатку виділіть прямокутник ROI")
            return
        x, y, w, h = self.roi
        if w < 5 or h < 5:
            self.result_label.setText("ROI надто малий")
            return
        margin = max(8, int(max(w, h) * 0.15))
        x0, y0 = max(0, x - margin), max(0, y - margin)
        x1, y1 = min(gray.shape[1], x + w + margin), min(gray.shape[0], y + h + margin)
        crop = gray[y0:y1, x0:x1]
        edges = cv2.Canny(crop, self.canny_low.value(), self.canny_high.value())
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = [c for c in contours if cv2.contourArea(c) >= self.min_area.value()]
        if not contours:
            self.selected_contour = None
            self.result_label.setText("Біля ROI контур не знайдено")
            return
        contour = max(contours, key=cv2.contourArea).copy()
        contour[:, 0, 0] += x0
        contour[:, 0, 1] += y0
        self.selected_contour = contour
        rect = cv2.minAreaRect(contour)
        width_px, height_px = rect[1]
        ppm = float(self.calibration_data.get("pixel_per_mm", 0.0))
        if ppm > 0:
            dimensions = f"{width_px / ppm:.3f} x {height_px / ppm:.3f} mm"
        else:
            dimensions = f"{width_px:.1f} x {height_px:.1f} px (calibrate pixel/mm for mm)"
        self.result_label.setText(f"Контур у ROI: розмір={dimensions}; кут={rect[2]:.3f}°")

    def add_measurement_point(self, pixel_x: int, pixel_y: int) -> None:
        frame = self.window.latest_frame
        if frame is None:
            return
        cnc = self.window.motion_last_coords or (0.0, 0.0, 0.0)
        ppm = float(self.calibration_data.get("pixel_per_mm", 0.0))
        center_x, center_y = frame.shape[1] / 2.0, frame.shape[0] / 2.0
        global_x = cnc[0] + ((pixel_x - center_x) / ppm if ppm > 0 else 0.0)
        global_y = cnc[1] - ((pixel_y - center_y) / ppm if ppm > 0 else 0.0)
        point = {"pixel_x": pixel_x, "pixel_y": pixel_y, "cnc_x": cnc[0], "cnc_y": cnc[1], "cnc_z": cnc[2], "global_x": global_x, "global_y": global_y}
        self.measurement_points.append(point)
        self.refresh_points_table()

    def refresh_points_table(self) -> None:
        self.points_table.setRowCount(len(self.measurement_points))
        for row, point in enumerate(self.measurement_points):
            distance_angle = "—"
            if row > 0:
                previous = self.measurement_points[row - 1]
                dx, dy = point["global_x"] - previous["global_x"], point["global_y"] - previous["global_y"]
                distance_angle = f"{math.hypot(dx, dy):.3f} mm / {math.degrees(math.atan2(dy, dx)):.3f}°"
            values = [row + 1, point["pixel_x"], point["pixel_y"], point["cnc_x"], point["cnc_y"], point["cnc_z"], point["global_x"], point["global_y"], distance_angle]
            for column, value in enumerate(values):
                text = f"{value:.3f}" if isinstance(value, float) else str(value)
                self.points_table.setItem(row, column, QTableWidgetItem(text))

    def delete_selected_point(self) -> None:
        rows = sorted({item.row() for item in self.points_table.selectedItems()}, reverse=True)
        for row in rows:
            if 0 <= row < len(self.measurement_points):
                del self.measurement_points[row]
        self.refresh_points_table()

    def clear_points(self) -> None:
        self.measurement_points.clear()
        self.refresh_points_table()

    def capture_checkerboard(self) -> None:
        gray = self.frame_gray()
        if gray is None:
            return
        pattern = (self.board_cols.value(), self.board_rows.value())
        found, corners = cv2.findChessboardCorners(gray, pattern, cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
        if not found:
            self.calibration_label.setText(f"Шахівницю не знайдено: очікується {pattern[0]} × {pattern[1]} внутрішніх кутів")
            return
        corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, .001))
        obj = np.zeros((pattern[0] * pattern[1], 3), np.float32)
        obj[:, :2] = np.mgrid[0:pattern[0], 0:pattern[1]].T.reshape(-1, 2) * self.square_size.value()
        self.object_points.append(obj)
        self.image_points.append(corners)
        self.image_size = (gray.shape[1], gray.shape[0])
        self.samples_label.setText(f"Зразків: {len(self.image_points)} (мінімум 3)")
        self.calibration_label.setText(f"Шахівницю захоплено: {len(corners)} кутів, зразок {len(self.image_points)}")

    def capture_charuco(self) -> None:
        gray = self.frame_gray()
        if gray is None:
            return
        if not hasattr(cv2, "aruco"):
            self.calibration_label.setText("Для Charuco потрібен пакет opencv-contrib-python")
            return
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        square = float(self.square_size.value())
        board = cv2.aruco.CharucoBoard(
            (self.board_cols.value(), self.board_rows.value()), square, square * 0.7, dictionary
        )
        detector = cv2.aruco.CharucoDetector(board)
        charuco_corners, charuco_ids, _, _ = detector.detectBoard(gray)
        count = 0 if charuco_ids is None else len(charuco_ids)
        if count < 6:
            self.calibration_label.setText(f"Charuco: знайдено лише {count} кутів, потрібно щонайменше 6")
            return
        object_points, image_points = board.matchImagePoints(charuco_corners, charuco_ids)
        self.object_points.append(np.asarray(object_points, dtype=np.float32))
        self.image_points.append(np.asarray(image_points, dtype=np.float32))
        self.image_size = (gray.shape[1], gray.shape[0])
        self.samples_label.setText(f"Зразків: {len(self.image_points)} (мінімум 3)")
        self.calibration_label.setText(f"Charuco захоплено: {count} кутів, зразок {len(self.image_points)}")

    def calculate_pixel_mm(self) -> None:
        if self.manual_line is None:
            self.calibration_label.setText("Спочатку намалюйте еталонну лінію у вкладці «Технічний зір»")
            return
        x1, y1, x2, y2 = self.manual_line
        pixel_length = math.hypot(x2 - x1, y2 - y1)
        real_length = float(self.reference_length.value())
        if pixel_length < 1.0 or real_length <= 0:
            self.calibration_label.setText("Еталонна лінія або реальна довжина некоректні")
            return
        value = pixel_length / real_length
        self.calibration_data["pixel_per_mm"] = value
        self.calibration_data["scale_reference_mm"] = real_length
        self.calibration_data["scale_reference_pixels"] = pixel_length
        self.calibration_label.setText(
            f"Масштаб: {value:.6f} пкс/мм; лінія {pixel_length:.3f} пкс = {real_length:.3f} мм"
        )

    def calculate_camera_calibration(self) -> None:
        if len(self.image_points) < 3 or self.image_size is None:
            self.calibration_label.setText(f"Потрібно щонайменше 3 ракурси шахівниці; захоплено {len(self.image_points)}")
            return
        if self.fisheye_model.isChecked():
            object_points = [np.asarray(p, np.float64).reshape(-1, 1, 3) for p in self.object_points]
            image_points = [np.asarray(p, np.float64).reshape(-1, 1, 2) for p in self.image_points]
            matrix = np.zeros((3, 3), dtype=np.float64)
            distortion = np.zeros((4, 1), dtype=np.float64)
            try:
                rms, _, _, _, _ = cv2.fisheye.calibrate(object_points, image_points, self.image_size, matrix, distortion, flags=0, criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-7))
            except cv2.error as exc:
                self.calibration_label.setText(f"Калібрування «риб’яче око» не виконано: потрібні різноманітніші кути шахівниці ({exc.code})")
                return
            model = "fisheye"
        else:
            rms, matrix, distortion, _, _ = cv2.calibrateCamera(self.object_points, self.image_points, self.image_size, None, None)
            model = "pinhole"
        self.calibration_data.update({"model": model, "rms": float(rms), "camera_matrix": matrix.tolist(), "distortion": distortion.tolist(), "image_size": list(self.image_size), "board": [self.board_cols.value(), self.board_rows.value()], "square_mm": self.square_size.value()})
        model_text = "риб’яче око" if model == "fisheye" else "звичайна модель"
        self.calibration_label.setText(f"Калібрування виконано ({model_text}); RMS похибка репроєкції={rms:.6f}")

    def calibration_file_for_camera(self) -> Path:
        camera = self.window.camera_combo.currentData()
        camera_id = camera.get("id", "unknown") if isinstance(camera, dict) else "unknown"
        safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in camera_id)
        return self.window.app_dir / "data" / "calibrations" / f"{safe_id}.json"

    def save_calibration(self) -> None:
        camera = self.window.camera_combo.currentData()
        key = camera.get("id", "unknown") if isinstance(camera, dict) else "unknown"
        payload = {"camera_id": key, "roi": self.roi, "manual_line": self.manual_line, **self.calibration_data}
        payload["measurement_points"] = self.measurement_points
        path = self.calibration_file_for_camera()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.calibration_label.setText(f"Калібрування для {key} збережено: {path.name}")

    def load_calibration(self) -> None:
        path = self.calibration_file_for_camera()
        if not path.exists():
            self.calibration_label.setText("Збереженого калібрування не знайдено")
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        self.calibration_data = data
        self.roi = tuple(data["roi"]) if data.get("roi") else None
        self.manual_line = tuple(data["manual_line"]) if data.get("manual_line") else None
        self.measurement_points = data.get("measurement_points", [])
        self.refresh_points_table()
        self.fisheye_model.setChecked(data.get("model") == "fisheye")
        self.calibration_label.setText(f"Калібрування завантажено: камера={data.get('camera_id', 'невідома')}, RMS={data.get('rms', 'немає')}")

    def on_camera_started(self) -> None:
        self.load_calibration()
