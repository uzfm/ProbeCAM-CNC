from __future__ import annotations
import json
import re
import sys
import threading
from queue import Empty, Queue
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
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
from vision_calibration import VisionCalibrationController


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
        self.motion_control_group: QGroupBox = self.root_widget.findChild(QGroupBox, "motionControlGroup")

        if self.tab_widget is None or self.log_edit is None:
            raise RuntimeError("The main UI must contain tabWidget and eventLog objects")
        self.tab_widget.currentChanged.connect(self.adjust_preview_for_tab)

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
        self.camera_bad_frame_count = 0
        self.camera_fallback_applied = False
        self.camera_black_signal_reported = False
        self.vision_calibration = VisionCalibrationController(self)
        self.setup_workflow_tab()
        self.calibration_info_label.setText(self.vision_calibration.calibration_status())
        self.motion_port: Optional[serial.Serial] = None
        self.motion_status_count = 0
        self.motion_last_raw = ""
        self.motion_last_coords = None
        self.motion_wco = (0.0, 0.0, 0.0)
        self.motion_rx_buffer = ""
        self.motion_rx_queue: Queue[str] = Queue()
        self.motion_reader_stop = threading.Event()
        self.motion_reader_thread: Optional[threading.Thread] = None
        self.motion_debug_path = self.app_dir / "data" / "motion_debug.log"
        self.motion_status_timer = QTimer(self)
        self.motion_status_timer.timeout.connect(self.poll_motion_status)
        self.profile_path = self.app_dir / "data" / "probe_cam_profile.json"
        self.camera_presets_path = self.app_dir / "data" / "camera_presets.json"
        self.camera_presets = self.load_camera_presets()
        self.display_zoom = 1.0

        self.scan_cameras()
        self.load_profile()
        self.log("Application initialized. Load a profile or start scanning cameras.")
        self.adjust_preview_for_tab(self.tab_widget.currentIndex())

    def adjust_preview_for_tab(self, index: int) -> None:
        if not hasattr(self, "preview_label") or self.preview_label is None:
            return
        title = self.tab_widget.tabText(index)
        if title == "Камера":
            self.preview_label.setMaximumHeight(360)
            self.tab_widget.setMaximumHeight(330)
            self.motion_control_group.show()
        elif title in {"Технічний зір", "Калібрування"}:
            self.preview_label.setMaximumHeight(260)
            self.tab_widget.setMaximumHeight(430 if title == "Технічний зір" else 360)
            self.motion_control_group.show()
        else:
            self.preview_label.setMaximumHeight(380)
            self.tab_widget.setMaximumHeight(260)
            self.motion_control_group.show()

    def setup_overview_tab(self) -> None:
        panel_widget = self.load_ui_widget("ui/designer_panel.ui")
        if panel_widget is not None:
            self.overview_layout.addWidget(panel_widget)
            panel_button = panel_widget.findChild(QPushButton, "panelButton")
            if panel_button is not None:
                panel_button.clicked.connect(self.load_profile)

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
        self.auto_exposure_checkbox = self.root_widget.findChild(QCheckBox, "autoExposureCheckBox")
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
        # VisionCalibrationController owns the Vision button connection.

        if self.preview_label is not None:
            self.preview_label.setAlignment(Qt.AlignCenter)
            self.preview_label.setMinimumHeight(280)
            self.preview_label.setStyleSheet("border:1px solid #777; background:#111; color:#fff;")

        if self.camera_info_label is not None:
            self.camera_info_label.setWordWrap(True)

        if self.apply_camera_settings_button is not None:
            self.apply_camera_settings_button.clicked.connect(self.apply_camera_settings)
        if self.save_camera_settings_button is not None:
            self.save_camera_settings_button.clicked.connect(self.save_camera_preset)

    def setup_vision_tab(self) -> None:
        self.vision_result_label = self.root_widget.findChild(QLabel, "visionResultLabel")

    def setup_motion_tab(self) -> None:
        self.port_combo = self.root_widget.findChild(QComboBox, "portCombo")
        self.motion_button = self.root_widget.findChild(QPushButton, "motionButton")
        self.jog_plus_button = self.root_widget.findChild(QPushButton, "jogPlusButton")
        self.jog_minus_button = self.root_widget.findChild(QPushButton, "jogMinusButton")
        self.home_button = self.root_widget.findChild(QPushButton, "homeButton")
        self.stop_button = self.root_widget.findChild(QPushButton, "stopButton")
        self.jog_y_plus_button = self.root_widget.findChild(QPushButton, "jogYPlusButton")
        self.jog_y_minus_button = self.root_widget.findChild(QPushButton, "jogYMinusButton")
        self.jog_z_plus_button = self.root_widget.findChild(QPushButton, "jogZPlusButton")
        self.jog_z_minus_button = self.root_widget.findChild(QPushButton, "jogZMinusButton")
        self.step_size_combo = self.root_widget.findChild(QComboBox, "stepSizeCombo")
        self.feed_rate_spinbox = self.root_widget.findChild(QSpinBox, "feedRateSpinBox")
        self.pos_x_label = self.root_widget.findChild(QLabel, "posXLabel")
        self.pos_y_label = self.root_widget.findChild(QLabel, "posYLabel")
        self.pos_z_label = self.root_widget.findChild(QLabel, "posZLabel")
        self.zero_x_button = self.root_widget.findChild(QPushButton, "zeroXButton")
        self.zero_y_button = self.root_widget.findChild(QPushButton, "zeroYButton")
        self.zero_z_button = self.root_widget.findChild(QPushButton, "zeroZButton")
        self.zero_all_button = self.root_widget.findChild(QPushButton, "zeroAllButton")
        self.continuous_check = self.root_widget.findChild(QCheckBox, "continuousCheck")
        self.run_check = self.root_widget.findChild(QCheckBox, "runCheck")
        self.reset_alarm_button = self.root_widget.findChild(QPushButton, "resetAlarmButton")
        self.motion_state_label = self.root_widget.findChild(QLabel, "motionStateLabel")
        self.continuous_timer = QTimer(self)
        self.continuous_timer.setInterval(100)
        self.continuous_timer.timeout.connect(self.send_continuous_jog)
        self.continuous_direction = 0
        self.run_direction = 0
        self.continuous_axis = "X"

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
        self.jog_plus_button.pressed.connect(lambda: self.start_jog("X", 1))
        self.jog_plus_button.released.connect(self.on_jog_released)
        self.jog_minus_button.pressed.connect(lambda: self.start_jog("X", -1))
        self.jog_minus_button.released.connect(self.on_jog_released)
        if self.stop_button is not None:
            self.stop_button.clicked.connect(self.emergency_stop)
        for button, axis, direction in ((self.jog_y_plus_button, "Y", 1), (self.jog_y_minus_button, "Y", -1), (self.jog_z_plus_button, "Z", 1), (self.jog_z_minus_button, "Z", -1)):
            if button is not None:
                button.pressed.connect(lambda a=axis, d=direction: self.start_jog(a, d))
                button.released.connect(self.on_jog_released)
        self.reset_alarm_button.clicked.connect(self.reset_alarm)
        self.home_button.clicked.connect(lambda: self.send_motion_command("$H\n"))
        if self.zero_x_button is not None:
            self.zero_x_button.clicked.connect(lambda: self.zero_axis("X"))
        if self.zero_y_button is not None:
            self.zero_y_button.clicked.connect(lambda: self.zero_axis("Y"))
        if self.zero_z_button is not None:
            self.zero_z_button.clicked.connect(lambda: self.zero_axis("Z"))
        if self.zero_all_button is not None:
            self.zero_all_button.clicked.connect(lambda: self.zero_axis("ALL"))

    def setup_calibration_tab(self) -> None:
        self.calibration_info_label = self.root_widget.findChild(QLabel, "calibrationInfoLabel")

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

    def setup_workflow_tab(self) -> None:
        root = self.root_widget
        self.workflow_zoom_label = root.findChild(QLabel, "workflowZoomLabel")
        root.findChild(QPushButton, "workflowZoomMinusButton").clicked.connect(lambda: self.set_display_zoom(self.display_zoom / 2))
        root.findChild(QPushButton, "workflowZoomPlusButton").clicked.connect(lambda: self.set_display_zoom(self.display_zoom * 2))
        root.findChild(QPushButton, "workflowZoomResetButton").clicked.connect(lambda: self.set_display_zoom(1.0))
        root.findChild(QPushButton, "workflowTargetButton").clicked.connect(self.calibrate_target)
        root.findChild(QPushButton, "workflowOffsetButton").clicked.connect(self.save_spindle_offset)
        root.findChild(QPushButton, "workflowSaveCalibrationButton").clicked.connect(self.vision_calibration.save_calibration)
        root.findChild(QPushButton, "workflowHoleButton").clicked.connect(self.vision_calibration.detect_hole_center)
        root.findChild(QPushButton, "workflowPointButton").clicked.connect(lambda: self.vision_calibration.mouse_point.setChecked(True))
        root.findChild(QPushButton, "workflowAngleButton").clicked.connect(self.vision_calibration.detect_contour_angle)
        root.findChild(QPushButton, "workflowSetZeroButton").clicked.connect(lambda: self.zero_axis("ALL"))
        root.findChild(QPushButton, "workflowExportButton").clicked.connect(self.vision_calibration.export_workpiece_parameters)

    def set_display_zoom(self, value: float) -> None:
        self.display_zoom = max(1.0, min(8.0, float(value)))
        if self.workflow_zoom_label:
            self.workflow_zoom_label.setText(f"Zoom: {self.display_zoom:.2f}x (display only)")

    def calibrate_target(self) -> None:
        frame = self.latest_frame
        if frame is None:
            self.log("Target calibration requires an active camera frame")
            return
        self.vision_calibration.calibration_data["target_u"] = frame.shape[1] / 2
        self.vision_calibration.calibration_data["target_v"] = frame.shape[0] / 2
        self.log(f"Camera target set to ({frame.shape[1]/2:.1f}, {frame.shape[0]/2:.1f})")

    def save_spindle_offset(self) -> None:
        root = self.root_widget
        self.vision_calibration.calibration_data["camera_to_spindle_mm"] = {"x": root.findChild(QDoubleSpinBox, "workflowOffsetXSpin").value(), "y": root.findChild(QDoubleSpinBox, "workflowOffsetYSpin").value()}
        self.log("Camera ↔ Spindle offset stored in calibration profile")

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
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] {message}"
        self.log_edit.appendPlainText(line)
        self.status_bar.showMessage(message)
        try:
            self.motion_debug_path.parent.mkdir(parents=True, exist_ok=True)
            with self.motion_debug_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass

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
        if sys.platform.startswith("linux"):
            backends = [("v4l2", cv2.CAP_V4L2)]
        else:
            backends = [
                ("dshow", cv2.CAP_DSHOW),
                ("msmf", cv2.CAP_MSMF),
                ("any", cv2.CAP_ANY),
            ]
        detected = []
        seen_ids = set()
        for index in range(0, 3):
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
            self.camera_combo.addItem("Камеру не знайдено")
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
            "auto_exposure": bool(self.auto_exposure_checkbox.isChecked()),
        }

    def set_camera_settings_from_dict(self, settings: dict) -> None:
        if not settings:
            settings = {"width": 1280, "height": 720, "fps": 30, "exposure": -6, "gain": 0}
        self.width_spinbox.setValue(int(settings.get("width", 1280)))
        self.height_spinbox.setValue(int(settings.get("height", 720)))
        self.fps_spinbox.setValue(int(settings.get("fps", 30)))
        self.exposure_spinbox.setValue(int(settings.get("exposure", -6)))
        self.gain_spinbox.setValue(int(settings.get("gain", 0)))
        self.auto_exposure_checkbox.setChecked(bool(settings.get("auto_exposure", True)))

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
        capture.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75 if settings["auto_exposure"] else 0.25)
        if not settings["auto_exposure"]:
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
            elif backend_name == "v4l2":
                backend_id = cv2.CAP_V4L2
            self.capture = cv2.VideoCapture(index, backend_id)
            if not self.capture.isOpened():
                self.log(f"Unable to open camera {camera_data.get('label')}")
                self.capture = None
                return
            # Keep only the newest frame and avoid latency from the webcam queue.
            self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if backend_name == "dshow":
                self.capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            self.apply_camera_settings_to_capture(self.capture)
            self.capture_timer.start(33)
            self.camera_bad_frame_count = 0
            self.camera_fallback_applied = False
            self.camera_black_signal_reported = False
            self.camera_button.setText("Зупинити камеру")
            self.vision_calibration.on_camera_started()
            self.log(f"Camera started: {camera_data.get('label')}")
        else:
            self.capture_timer.stop()
            if self.capture is not None:
                self.capture.release()
            self.capture = None
            self.camera_button.setText("Запустити камеру")
            self.log("Camera stopped")

    def capture_frame(self) -> None:
        if self.capture is None:
            return
        ok, frame = self.capture.read()
        if not ok:
            self.log("Failed to read camera frame")
            return
        if float(frame.mean()) < 1.0:
            self.camera_bad_frame_count += 1
        else:
            self.camera_bad_frame_count = 0
        if self.camera_bad_frame_count >= 3 and not self.camera_fallback_applied:
            self.reopen_camera_safe_mode()
            return
        if self.camera_fallback_applied and self.camera_bad_frame_count >= 30:
            if not self.camera_black_signal_reported:
                self.camera_black_signal_reported = True
                self.camera_info_label.setText(
                    "Камера підключена, але повертає чорний сигнал. "
                    "Перевірте шторку/освітлення та чи не відкрита камера в іншій програмі."
                )
                self.log("Камера віддає чорні кадри навіть у безпечному режимі")
        elif self.camera_bad_frame_count == 0 and self.camera_black_signal_reported:
            self.camera_black_signal_reported = False
            self.camera_info_label.setText("Відеосигнал камери відновлено")
        self.latest_frame = frame
        display_frame = self.vision_calibration.overlay_frame(frame)
        if self.display_zoom > 1.0:
            height, width = display_frame.shape[:2]
            crop_w, crop_h = int(width / self.display_zoom), int(height / self.display_zoom)
            cx = int(self.vision_calibration.calibration_data.get("target_u", width / 2))
            cy = int(self.vision_calibration.calibration_data.get("target_v", height / 2))
            x0 = max(0, min(width - crop_w, cx - crop_w // 2)); y0 = max(0, min(height - crop_h, cy - crop_h // 2))
            display_frame = cv2.resize(display_frame[y0:y0 + crop_h, x0:x0 + crop_w], (width, height), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(image)
        self.preview_label.setPixmap(
            pixmap.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.FastTransformation)
        )

    def reopen_camera_safe_mode(self) -> None:
        self.camera_fallback_applied = True
        camera_data = self.camera_combo.currentData()
        if not isinstance(camera_data, dict):
            return
        if self.capture is not None:
            self.capture.release()
        backend_name = camera_data.get("backend")
        if backend_name == "dshow":
            backend = cv2.CAP_DSHOW
        elif backend_name == "msmf":
            backend = cv2.CAP_MSMF
        elif backend_name == "v4l2":
            backend = cv2.CAP_V4L2
        else:
            backend = cv2.CAP_ANY
        self.capture = cv2.VideoCapture(int(camera_data.get("index", 0)), backend)
        if not self.capture.isOpened():
            self.capture.release()
            self.capture = None
            self.camera_button.setText("Запустити камеру")
            self.log("Не вдалося повторно відкрити камеру у безпечному режимі")
            return
        self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.capture.set(cv2.CAP_PROP_FPS, 30)
        self.capture.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
        self.width_spinbox.setValue(640)
        self.height_spinbox.setValue(480)
        self.fps_spinbox.setValue(30)
        self.auto_exposure_checkbox.setChecked(True)
        self.camera_bad_frame_count = 0
        self.log("Камеру повторно відкрито: 640x480, 30 FPS, автоматична експозиція")

    def process_current_frame(self) -> None:
        self.vision_calibration.process_current_frame()

    def toggle_motion_connection(self) -> None:
        if self.motion_port is None:
            port = self.port_combo.currentText()
            if port in {"", "No serial ports"}:
                self.log("No serial port selected")
                return
            try:
                self.motion_port = serial.Serial(port, 115200, timeout=0)
                self.motion_port.timeout = 0.1
                self.motion_reader_stop.clear()
                self.motion_reader_thread = threading.Thread(
                    target=self.read_motion_loop, name="GRBL-reader", daemon=True
                )
                self.motion_reader_thread.start()
                self.motion_port.write(b"\r\n")
                self.motion_button.setText("Відключити")
                self.motion_state_label.setText("GRBL: підключено, перевірка стану...")
                self.motion_status_timer.start(100)
                self.motion_status_count = 0
                self.log(f"Connected to {port} at 115200 baud; status polling started")
            except Exception as exc:
                self.log(f"Unable to connect to {port}: {exc}")
        else:
            self.motion_reader_stop.set()
            if self.motion_reader_thread is not None:
                self.motion_reader_thread.join(timeout=0.3)
                self.motion_reader_thread = None
            if self.motion_port is not None and self.motion_port.is_open:
                self.motion_port.close()
            self.motion_port = None
            self.motion_status_timer.stop()
            self.stop_jog()
            self.motion_button.setText("Підключити")
            self.motion_state_label.setText("GRBL: відключено")
            self.log("Motion controller disconnected")

    def send_motion_command(self, command: str, log_command: bool = True) -> None:
        if self.motion_port is None or not self.motion_port.is_open:
            self.log("No active motion connection")
            return
        try:
            self.motion_port.write(command.encode("utf-8"))
            if log_command:
                self.log(f"BUTTON command sent: {command.strip()!r}")
        except Exception as exc:
            self.log(f"Motion send failed: {exc}")

    def read_motion_loop(self) -> None:
        while not self.motion_reader_stop.is_set():
            port = self.motion_port
            if port is None or not port.is_open:
                break
            try:
                raw = port.readline()
                if raw:
                    self.motion_rx_queue.put(raw.decode("ascii", errors="ignore"))
            except (OSError, serial.SerialException):
                break

    def reset_alarm(self) -> None:
        if self.motion_port is None or not self.motion_port.is_open:
            self.log("RESET ALARM failed: GRBL is not connected")
            return
        try:
            self.stop_jog()
            self.motion_port.write(b"$X\n")
            self.motion_state_label.setText("GRBL: alarm reset requested; checking state...")
            self.log("RESET ALARM: sent $X to GRBL")
        except (OSError, serial.SerialException) as exc:
            self.motion_state_label.setText("GRBL: reset failed")
            self.log(f"RESET ALARM failed: {exc}")

    def zero_axis(self, axis: str) -> None:
        coords = self.motion_last_coords
        if coords is not None and hasattr(self, "vision_calibration"):
            zero = self.vision_calibration.calibration_data.setdefault("zero", {})
            if axis in {"X", "ALL"}:
                zero["x"] = coords[0]
            if axis in {"Y", "ALL"}:
                zero["y"] = coords[1]
            if axis in {"Z", "ALL"}:
                zero["z"] = coords[2]
        command = "G10 L20 P1 X0 Y0 Z0\n" if axis == "ALL" else f"G10 L20 P1 {axis}0\n"
        self.send_motion_command(command)
        self.log(f"ZERO {axis}: requested; waiting for updated WPos")

    def jog(self, axis: str, direction: int) -> None:
        step_text = self.step_size_combo.currentText() if self.step_size_combo is not None else "1 mm"
        step = float(step_text.split()[0])
        self.send_motion_command(f"G91\nG0 {axis}{direction * step:g} F{self.feed_rate()}\nG90\n")

    def start_jog(self, axis: str, direction: int) -> None:
        self.continuous_axis = axis
        if self.run_check.isChecked():
            self.run_direction = direction
            self.continuous_direction = direction
            self.send_continuous_jog()
            self.continuous_timer.start()
        elif self.continuous_check.isChecked():
            self.continuous_direction = direction
            self.send_continuous_jog()
            self.continuous_timer.start()
        else:
            self.jog(axis, direction)

    def on_jog_released(self) -> None:
        # Releasing any axis button must always stop motion, including RUN mode.
        self.stop_jog()

    def send_continuous_jog(self) -> None:
        if self.continuous_direction == 0:
            return
        step = float(self.step_size_combo.currentText().split()[0])
        self.send_motion_command(
            f"$J=G91 {self.continuous_axis}{self.continuous_direction * step:g} F{self.feed_rate()}\n",
            log_command=False,
        )

    def feed_rate(self) -> int:
        if self.feed_rate_spinbox is None:
            return 600
        return max(1, int(self.feed_rate_spinbox.value()))

    def stop_jog(self) -> None:
        self.continuous_timer.stop()
        self.continuous_direction = 0
        self.run_direction = 0
        if self.motion_port is not None and self.motion_port.is_open:
            try:
                self.motion_port.write(b"\x85")
            except serial.SerialException:
                pass

    def emergency_stop(self) -> None:
        self.continuous_timer.stop()
        self.continuous_direction = 0
        self.run_direction = 0
        if self.motion_port is None or not self.motion_port.is_open:
            self.log("EMERGENCY STOP: no active GRBL connection")
            return
        try:
            # 0x85 cancels an active jog; 0x90 feed-holds; 0x18 is GRBL reset.
            self.motion_port.write(b"\x85\x90\x18")
            self.motion_state_label.setText("GRBL: EMERGENCY STOP sent")
            self.log("EMERGENCY STOP: sent jog cancel and feed hold")
        except (OSError, serial.SerialException) as exc:
            self.log(f"EMERGENCY STOP failed: {exc}")

    def poll_motion_status(self) -> None:
        if self.motion_port is None or not self.motion_port.is_open:
            return
        try:
            self.motion_port.write(b"?")
            responses = []
            while True:
                try:
                    responses.append(self.motion_rx_queue.get_nowait())
                except Empty:
                    break
            response = "\n".join(responses)
            if not response:
                return
            self.motion_status_count += 1
            if response:
                self.motion_last_raw = response.replace("\r", "\\r").replace("\n", "\\n")
            match = re.search(r"MPos:([-+0-9.]+),([-+0-9.]+),([-+0-9.]+)", response)
            if match:
                x, y, z = (float(value) for value in match.groups())
                wco_match = re.search(r"WCO:([-+0-9.]+),([-+0-9.]+),([-+0-9.]+)", response)
                if wco_match:
                    self.motion_wco = tuple(float(value) for value in wco_match.groups())
                wx, wy, wz = (x - self.motion_wco[0], y - self.motion_wco[1], z - self.motion_wco[2])
                self.pos_x_label.setText(f"{wx:.3f}")
                self.pos_y_label.setText(f"{wy:.3f}")
                self.pos_z_label.setText(f"{wz:.3f}")
                coords = (wx, wy, wz)
                if coords != self.motion_last_coords:
                    self.motion_last_coords = coords
                    self.log(f"GRBL WPos updated: X={wx:.3f} Y={wy:.3f} Z={wz:.3f}")
                state_match = re.search(r"<([^|>]+)\|", response)
                state = state_match.group(1) if state_match else "Unknown"
                if state.lower().startswith("alarm"):
                    self.motion_state_label.setText(f"GRBL: {state} — movement blocked")
                else:
                    self.motion_state_label.setText(f"GRBL: {state}")
                if "error:" in response.lower():
                    self.log(f"GRBL command error: {self.motion_last_raw}")
            elif response:
                if "alarm" in response.lower() or "error:" in response.lower():
                    self.motion_state_label.setText("GRBL: controller error")
                    self.log(f"GRBL error response: {self.motion_last_raw}")
                self.log(f"GRBL reply without MPos: {self.motion_last_raw}")
            elif self.motion_status_count % 10 == 0:
                self.log(f"No GRBL response after {self.motion_status_count} status polls")
        except (OSError, serial.SerialException) as exc:
            self.log(f"Status read failed: {exc}")

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
