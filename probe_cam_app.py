from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QImage, QPixmap
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)
import serial
from serial.tools import list_ports


class ProbeCAMMainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.app_dir = Path(__file__).resolve().parent
        self.ui_path = self.app_dir / "ui" / "main_window.ui"
        self.loader = QUiLoader()
        self.root_widget = self.loader.load(str(self.ui_path), self)
        if self.root_widget is None:
            raise RuntimeError(f"Unable to load UI file: {self.ui_path}")

        self.setCentralWidget(self.root_widget)
        self.setWindowTitle("ProbeCAM CNC")
        self.resize(1280, 900)
        self.setMinimumSize(1100, 760)
        self.apply_dark_theme()

        self.status_bar: QStatusBar = self.statusBar()
        self.status_bar.showMessage("Ready")

        self.tab_widget: QTabWidget = self.root_widget.findChild(QTabWidget, "tabWidget")
        self.log_edit: QPlainTextEdit = self.root_widget.findChild(QPlainTextEdit, "eventLog")
        self.overview_layout: QVBoxLayout = self.root_widget.findChild(QVBoxLayout, "overviewLayout")
        self.camera_layout: QHBoxLayout = self.root_widget.findChild(QHBoxLayout, "cameraLayout")
        self.vision_layout: QVBoxLayout = self.root_widget.findChild(QVBoxLayout, "visionLayout")
        self.motion_layout: QVBoxLayout = self.root_widget.findChild(QVBoxLayout, "motionLayout")
        self.calibration_layout: QVBoxLayout = self.root_widget.findChild(QVBoxLayout, "calibrationLayout")
        self.settings_layout: QVBoxLayout = self.root_widget.findChild(QVBoxLayout, "settingsLayout")

        if self.tab_widget is None or self.log_edit is None:
            raise RuntimeError("The main UI must contain tabWidget and eventLog objects")

        self.setup_file_menu()
        self.setup_overview_tab()
        self.setup_camera_tab()
        self.setup_vision_tab()
        self.setup_motion_tab()
        self.setup_calibration_tab()
        self.setup_settings_tab()

        self.capture: Optional[cv2.VideoCapture] = None
        self.capture_timer = QTimer(self)
        self.capture_timer.timeout.connect(self.capture_frame)
        self.latest_frame: Optional[np.ndarray] = None
        self.motion_port: Optional[serial.Serial] = None
        self.profile_path = self.app_dir / "data" / "probe_cam_profile.json"
        self.camera_presets_path = self.app_dir / "data" / "camera_presets.json"
        self.camera_presets = self.load_camera_presets()

        self.scan_cameras()
        self.load_profile()
        self.log("Application initialized. Load a profile or start scanning cameras.")

    def setup_file_menu(self) -> None:
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        load_action = QAction("Load profile", self)
        load_action.triggered.connect(self.load_profile)
        save_action = QAction("Save profile", self)
        save_action.triggered.connect(self.save_profile)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(QApplication.quit)
        file_menu.addAction(load_action)
        file_menu.addAction(save_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        tools_menu = menu_bar.addMenu("Tools")
        scan_action = QAction("Scan cameras", self)
        scan_action.triggered.connect(self.scan_cameras)
        tools_menu.addAction(scan_action)

    def setup_overview_tab(self) -> None:
        panel_widget = self.load_ui_widget("ui/designer_panel.ui")
        if panel_widget is not None:
            self.overview_layout.addWidget(panel_widget)
            panel_button = panel_widget.findChild(QPushButton, "panelButton")
            if panel_button is not None:
                panel_button.clicked.connect(self.load_profile)
        self.overview_layout.addStretch(1)

    def setup_camera_tab(self) -> None:
        self.camera_combo = self.root_widget.findChild(QComboBox, "cameraCombo")
        self.refresh_cameras_button = self.root_widget.findChild(QPushButton, "refreshCamerasButton")
        self.camera_button = self.root_widget.findChild(QPushButton, "cameraButton")
        self.process_button = self.root_widget.findChild(QPushButton, "processButton")
        self.preview_label = self.root_widget.findChild(QLabel, "previewLabel")
        self.camera_info_label = self.root_widget.findChild(QLabel, "cameraInfoLabel")
        self.width_spinbox = self.root_widget.findChild(QSpinBox, "widthSpinBox")
        self.height_spinbox = self.root_widget.findChild(QSpinBox, "heightSpinBox")
        self.fps_spinbox = self.root_widget.findChild(QSpinBox, "fpsSpinBox")
        self.exposure_spinbox = self.root_widget.findChild(QSpinBox, "exposureSpinBox")
        self.gain_spinbox = self.root_widget.findChild(QSpinBox, "gainSpinBox")
        self.apply_camera_settings_button = self.root_widget.findChild(QPushButton, "applyCameraSettingsButton")
        self.save_camera_settings_button = self.root_widget.findChild(QPushButton, "saveCameraSettingsButton")

        if self.camera_combo is None:
            raise RuntimeError("cameraCombo is not defined in main_window.ui")
        self.camera_combo.setMinimumWidth(260)
        self.camera_combo.currentIndexChanged.connect(self.on_camera_selection_changed)

        if self.refresh_cameras_button is not None:
            self.refresh_cameras_button.clicked.connect(self.scan_cameras)
        if self.camera_button is not None:
            self.camera_button.clicked.connect(self.toggle_camera)
        if self.process_button is not None:
            self.process_button.clicked.connect(self.process_current_frame)

        if self.preview_label is not None:
            self.preview_label.setAlignment(Qt.AlignCenter)
            self.preview_label.setMinimumHeight(420)
            self.preview_label.setStyleSheet("border:1px solid #777; background:#111; color:#fff;")

        if self.camera_info_label is not None:
            self.camera_info_label.setWordWrap(True)

        if self.apply_camera_settings_button is not None:
            self.apply_camera_settings_button.clicked.connect(self.apply_camera_settings)
        if self.save_camera_settings_button is not None:
            self.save_camera_settings_button.clicked.connect(self.save_camera_preset)

    def setup_vision_tab(self) -> None:
        self.vision_result_label = self.root_widget.findChild(QLabel, "visionResultLabel")
        if self.vision_result_label is None:
            raise RuntimeError("visionResultLabel is not defined in main_window.ui")
        self.vision_result_label.setWordWrap(True)
        self.vision_result_label.setMinimumHeight(120)

    def setup_motion_tab(self) -> None:
        self.port_combo = self.root_widget.findChild(QComboBox, "portCombo")
        self.motion_button = self.root_widget.findChild(QPushButton, "motionButton")
        self.jog_plus_button = self.root_widget.findChild(QPushButton, "jogPlusButton")
        self.jog_minus_button = self.root_widget.findChild(QPushButton, "jogMinusButton")
        self.home_button = self.root_widget.findChild(QPushButton, "homeButton")

        if self.port_combo is None:
            raise RuntimeError("portCombo is not defined in main_window.ui")
        if self.motion_button is None:
            raise RuntimeError("motionButton is not defined in main_window.ui")
        if self.jog_plus_button is None:
            raise RuntimeError("jogPlusButton is not defined in main_window.ui")
        if self.jog_minus_button is None:
            raise RuntimeError("jogMinusButton is not defined in main_window.ui")
        if self.home_button is None:
            raise RuntimeError("homeButton is not defined in main_window.ui")

        self.motion_button.clicked.connect(self.toggle_motion_connection)
        self.jog_plus_button.clicked.connect(lambda: self.send_motion_command("G91\nG0 X1 F600\n"))
        self.jog_minus_button.clicked.connect(lambda: self.send_motion_command("G91\nG0 X-1 F600\n"))
        self.home_button.clicked.connect(lambda: self.send_motion_command("$H\n"))

    def setup_calibration_tab(self) -> None:
        self.calibration_info_label = self.root_widget.findChild(QLabel, "calibrationInfoLabel")
        if self.calibration_info_label is None:
            raise RuntimeError("calibrationInfoLabel is not defined in main_window.ui")
        self.calibration_info_label.setWordWrap(True)

    def setup_settings_tab(self) -> None:
        self.settings_label = self.root_widget.findChild(QLabel, "settingsLabel")
        self.save_profile_button = self.root_widget.findChild(QPushButton, "saveProfileButton")
        self.load_profile_button = self.root_widget.findChild(QPushButton, "loadProfileButton")

        if self.settings_label is None:
            raise RuntimeError("settingsLabel is not defined in main_window.ui")
        if self.save_profile_button is None:
            raise RuntimeError("saveProfileButton is not defined in main_window.ui")
        if self.load_profile_button is None:
            raise RuntimeError("loadProfileButton is not defined in main_window.ui")

        self.settings_label.setWordWrap(True)
        self.save_profile_button.clicked.connect(self.save_profile)
        self.load_profile_button.clicked.connect(self.load_profile)

    def load_ui_widget(self, relative_path: str) -> Optional[QWidget]:
        ui_file = self.app_dir / relative_path
        if not ui_file.exists():
            self.log(f"UI file not found: {ui_file}")
            return None
        widget = self.loader.load(str(ui_file), self)
        return widget

    def apply_dark_theme(self) -> None:
        from PySide6.QtGui import QPalette

        palette = QApplication.palette()
        palette.setColor(QPalette.ColorRole.Window, 0x1F1F23)
        palette.setColor(QPalette.ColorRole.WindowText, 0xF5F5F5)
        palette.setColor(QPalette.ColorRole.Base, 0x2A2A2D)
        palette.setColor(QPalette.ColorRole.AlternateBase, 0x33333A)
        palette.setColor(QPalette.ColorRole.ToolTipBase, 0xFFFFFF)
        palette.setColor(QPalette.ColorRole.ToolTipText, 0x000000)
        palette.setColor(QPalette.ColorRole.Text, 0xF5F5F5)
        palette.setColor(QPalette.ColorRole.Button, 0x2A2A2D)
        palette.setColor(QPalette.ColorRole.ButtonText, 0xF5F5F5)
        palette.setColor(QPalette.ColorRole.Highlight, 0x3B82F6)
        palette.setColor(QPalette.ColorRole.HighlightedText, 0xFFFFFF)
        QApplication.setPalette(palette)
        QApplication.setStyle("Fusion")

    def log(self, message: str) -> None:
        self.log_edit.appendPlainText(message)
        self.status_bar.showMessage(message)

    def _probe_camera(self, index: int, backend_name: str, backend_id) -> Optional[dict]:
        try:
            cap = cv2.VideoCapture(index, backend_id)
            if not cap.isOpened():
                return None
            # Some devices need a short warm-up; a quick read confirms availability.
            ok, _ = cap.read()
            cap.release()
            if ok:
                return {
                    "id": f"{backend_name}:{index}",
                    "index": index,
                    "backend": backend_name,
                    "label": f"Camera {index} ({backend_name})",
                }
        except Exception:
            return None
        return None

    def get_available_cameras(self) -> list[dict]:
        backends = [
            ("dshow", cv2.CAP_DSHOW),
            ("msmf", cv2.CAP_MSMF),
            ("any", cv2.CAP_ANY),
        ]
        detected = []
        seen_ids = set()
        for index in range(0, 8):
            for backend_name, backend_id in backends:
                camera = self._probe_camera(index, backend_name, backend_id)
                if camera is None:
                    continue
                if camera["id"] in seen_ids:
                    continue
                detected.append(camera)
                seen_ids.add(camera["id"])
                break
        return detected

    def scan_cameras(self) -> None:
        self.camera_combo.clear()
        detected = self.get_available_cameras()
        if detected:
            for camera in detected:
                self.camera_combo.addItem(camera["label"], camera)
            self.camera_combo.setCurrentIndex(0)
            self.log(f"Detected cameras: {[item['label'] for item in detected]}")
        else:
            self.camera_combo.addItem("No camera detected")
            self.log("No camera detected by OpenCV; if you have a webcam or Logitech UVC device, try reconnecting it and click Refresh cameras")
        self.populate_serial_ports()

    def on_camera_selection_changed(self) -> None:
        camera_data = self.camera_combo.currentData()
        if not isinstance(camera_data, dict):
            return
        camera_key = camera_data.get("id")
        preset = self.camera_presets.get(camera_key)
        if preset is None:
            self.set_camera_settings_from_dict({})
            return
        self.set_camera_settings_from_dict(preset.get("settings", {}))

    def load_camera_presets(self) -> dict:
        if not self.camera_presets_path.exists():
            return {}
        try:
            with self.camera_presets_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
                return data if isinstance(data, dict) else {}
        except Exception as exc:
            self.log(f"Unable to load camera presets: {exc}")
            return {}

    def save_camera_presets(self) -> None:
        self.camera_presets_path.parent.mkdir(parents=True, exist_ok=True)
        with self.camera_presets_path.open("w", encoding="utf-8") as handle:
            json.dump(self.camera_presets, handle, indent=2)

    def get_current_camera_settings(self) -> dict:
        return {
            "width": int(self.width_spinbox.value()),
            "height": int(self.height_spinbox.value()),
            "fps": int(self.fps_spinbox.value()),
            "exposure": int(self.exposure_spinbox.value()),
            "gain": int(self.gain_spinbox.value()),
        }

    def set_camera_settings_from_dict(self, settings: dict) -> None:
        if not settings:
            settings = {"width": 1280, "height": 720, "fps": 30, "exposure": -6, "gain": 0}
        self.width_spinbox.setValue(int(settings.get("width", 1280)))
        self.height_spinbox.setValue(int(settings.get("height", 720)))
        self.fps_spinbox.setValue(int(settings.get("fps", 30)))
        self.exposure_spinbox.setValue(int(settings.get("exposure", -6)))
        self.gain_spinbox.setValue(int(settings.get("gain", 0)))

    def save_camera_preset(self) -> None:
        camera_data = self.camera_combo.currentData()
        if not isinstance(camera_data, dict):
            self.log("No camera selected for saving")
            return
        camera_key = camera_data.get("id")
        settings = self.get_current_camera_settings()
        self.camera_presets[camera_key] = {
            "label": camera_data.get("label"),
            "index": camera_data.get("index"),
            "backend": camera_data.get("backend"),
            "settings": settings,
        }
        self.save_camera_presets()
        self.log(f"Saved camera preset for {camera_data.get('label')}")

    def apply_camera_settings(self) -> None:
        if self.capture is not None:
            self.apply_camera_settings_to_capture(self.capture)
        else:
            self.log("No active camera capture to apply settings to")
        self.save_camera_preset()

    def apply_camera_settings_to_capture(self, capture: cv2.VideoCapture) -> None:
        settings = self.get_current_camera_settings()
        if capture is None:
            return
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, float(settings["width"]))
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, float(settings["height"]))
        capture.set(cv2.CAP_PROP_FPS, float(settings["fps"]))
        capture.set(cv2.CAP_PROP_EXPOSURE, float(settings["exposure"]))
        capture.set(cv2.CAP_PROP_GAIN, float(settings["gain"]))
        self.log(f"Applied camera settings: {settings}")

    def populate_serial_ports(self) -> None:
        self.port_combo.clear()
        ports = [port.device for port in list_ports.comports()]
        if ports:
            for port in ports:
                self.port_combo.addItem(port)
            self.log(f"Detected serial ports: {ports}")
        else:
            self.port_combo.addItem("No serial ports")

    def populate_serial_ports(self) -> None:
        self.port_combo.clear()
        ports = [port.device for port in list_ports.comports()]
        if ports:
            for port in ports:
                self.port_combo.addItem(port)
            self.log(f"Detected serial ports: {ports}")
        else:
            self.port_combo.addItem("No serial ports")

    def toggle_camera(self) -> None:
        if self.capture is None:
            camera_data = self.camera_combo.currentData()
            if not isinstance(camera_data, dict):
                self.log("No camera selected")
                return
            index = int(camera_data.get("index", 0))
            backend_name = camera_data.get("backend", "any")
            backend_id = cv2.CAP_ANY
            if backend_name == "dshow":
                backend_id = cv2.CAP_DSHOW
            elif backend_name == "msmf":
                backend_id = cv2.CAP_MSMF
            self.capture = cv2.VideoCapture(index, backend_id)
            if not self.capture.isOpened():
                self.log(f"Unable to open camera {camera_data.get('label')}")
                self.capture = None
                return
            self.apply_camera_settings_to_capture(self.capture)
            self.capture_timer.start(33)
            self.camera_button.setText("Stop camera")
            self.log(f"Camera started: {camera_data.get('label')}")
        else:
            self.capture_timer.stop()
            if self.capture is not None:
                self.capture.release()
            self.capture = None
            self.camera_button.setText("Start camera")
            self.log("Camera stopped")

    def capture_frame(self) -> None:
        if self.capture is None:
            return
        ok, frame = self.capture.read()
        if not ok:
            self.log("Failed to read camera frame")
            return
        self.latest_frame = frame
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(image)
        self.preview_label.setPixmap(pixmap.scaled(self.preview_label.size(), Qt.KeepAspectRatio))

    def process_current_frame(self) -> None:
        if self.latest_frame is None:
            self.log("No frame available. Start the camera first.")
            return
        gray = cv2.cvtColor(self.latest_frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 60, 140)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            contour = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(contour)
            perimeter = cv2.arcLength(contour, True)
            confidence = min(1.0, area / 120000.0)
            approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
            self.vision_result_label.setText(
                f"Detected {len(contours)} contour(s); area={area:.1f}px²; vertices={len(approx)}; confidence={confidence:.2f}"
            )
            self.log(f"Vision pass: confidence {confidence:.2f}, area {area:.1f}")
        else:
            self.vision_result_label.setText("No contours found in the current frame")
            self.log("Vision pass: no contours found")

    def toggle_motion_connection(self) -> None:
        if self.motion_port is None:
            port = self.port_combo.currentText()
            if port in {"", "No serial ports"}:
                self.log("No serial port selected")
                return
            try:
                self.motion_port = serial.Serial(port, 115200, timeout=0.2)
                self.motion_port.write(b"\r\n")
                self.motion_button.setText("Disconnect")
                self.log(f"Connected to {port}")
            except Exception as exc:
                self.log(f"Unable to connect to {port}: {exc}")
        else:
            self.motion_port.close()
            self.motion_port = None
            self.motion_button.setText("Connect")
            self.log("Motion controller disconnected")

    def send_motion_command(self, command: str) -> None:
        if self.motion_port is None or not self.motion_port.is_open:
            self.log("No active motion connection")
            return
        try:
            self.motion_port.write(command.encode("utf-8"))
            self.log(f"Sent: {command.strip()}")
        except Exception as exc:
            self.log(f"Motion send failed: {exc}")

    def load_profile(self) -> None:
        if not self.profile_path.exists():
            self.log("No profile yet; using defaults")
            return
        try:
            with self.profile_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            self.log(f"Loaded profile from {self.profile_path}")
            camera_id = data.get("camera_id")
            if camera_id:
                for index in range(self.camera_combo.count()):
                    item_data = self.camera_combo.itemData(index)
                    if isinstance(item_data, dict) and item_data.get("id") == camera_id:
                        self.camera_combo.setCurrentIndex(index)
                        break
            if "camera_settings" in data:
                self.set_camera_settings_from_dict(data["camera_settings"])
            if "port" in data:
                self.port_combo.setCurrentText(data["port"])
        except Exception as exc:
            self.log(f"Unable to load profile: {exc}")

    def save_profile(self) -> None:
        camera_data = self.camera_combo.currentData()
        data = {
            "camera_id": camera_data.get("id") if isinstance(camera_data, dict) else None,
            "camera_settings": self.get_current_camera_settings(),
            "port": self.port_combo.currentText(),
        }
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        with self.profile_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        self.log(f"Saved profile to {self.profile_path}")

    def closeEvent(self, event) -> None:
        if self.capture is not None:
            self.capture.release()
        if self.motion_port is not None and self.motion_port.is_open:
            self.motion_port.close()
        self.save_profile()
        super().closeEvent(event)
