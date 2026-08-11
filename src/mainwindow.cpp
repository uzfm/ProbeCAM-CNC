#include "mainwindow.h"

#include <QComboBox>
#include <QDoubleSpinBox>
#include <QFormLayout>
#include <QGridLayout>
#include <QGroupBox>
#include <QLabel>
#include <QPainter>
#include <QFrame>
#include <QPushButton>
#include <QSplitter>
#include <QTabWidget>
#include <QStatusBar>
#include <QTextEdit>
#include <QToolBar>
#include <QVBoxLayout>

class PreviewWidget : public QWidget {
public:
    explicit PreviewWidget(QWidget* parent = nullptr) : QWidget(parent) {
        setAutoFillBackground(false);
        setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
        setMinimumSize(480, 270);
    }

    void setFrame(const QImage& frame) {
        frame_ = frame;
        update();
    }

protected:
    void paintEvent(QPaintEvent*) override {
        QPainter p(this);
        p.fillRect(rect(), QColor("#0a0f14"));
        p.setRenderHint(QPainter::SmoothPixmapTransform, true);
        p.setPen(QPen(QColor("#314052"), 1));
        p.drawRect(rect().adjusted(0, 0, -1, -1));
        if (frame_.isNull()) {
            p.setPen(QColor("#8aa0b6"));
            p.drawText(rect(), Qt::AlignCenter, "Camera preview");
            return;
        }
        const QImage rgb = frame_.convertToFormat(QImage::Format_RGB888);
        QPixmap pix = QPixmap::fromImage(rgb);
        const QSize target = pix.size().scaled(size(), Qt::KeepAspectRatio);
        const QRect targetRect(QPoint((width() - target.width()) / 2, (height() - target.height()) / 2), target);
        p.drawPixmap(targetRect, pix.scaled(target, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    }

private:
    QImage frame_;
};

MainWindow::MainWindow(QWidget* parent)
    : QMainWindow(parent) {
    buildUi();
    applyTheme();
    refreshCameraList();
    loadProfile();
    appendLog(QStringLiteral("Application started"));
}

void MainWindow::buildUi() {
    auto* central = new QWidget(this);
    auto* root = new QVBoxLayout(central);
    root->setContentsMargins(8, 8, 8, 8);
    root->setSpacing(8);

    auto* topBar = new QToolBar(this);
    addToolBar(topBar);
    auto* refreshBtn = topBar->addAction("Refresh");
    connect(refreshBtn, &QAction::triggered, this, &MainWindow::refreshCameraList);
    auto* detectBtn = topBar->addAction("Detect");
    connect(detectBtn, &QAction::triggered, this, &MainWindow::runDetection);
    auto* saveBtn = topBar->addAction("Save");
    connect(saveBtn, &QAction::triggered, this, &MainWindow::saveProfile);

    auto* mainRoot = new QVBoxLayout();
    mainRoot->setContentsMargins(0, 0, 0, 0);
    mainRoot->setSpacing(8);

    auto* topInfo = new QFrame(this);
    topInfo->setObjectName("TopInfo");
    auto* topInfoLayout = new QHBoxLayout(topInfo);
    topInfoLayout->setContentsMargins(12, 10, 12, 10);
    topInfoLayout->setSpacing(16);
    auto* saveQuickBtn = new QPushButton("Save", topInfo);
    topCameraLabel_ = new QLabel("Camera: none", topInfo);
    topCoordsLabel_ = new QLabel("X: 0.000  Y: 0.000  Z: 0.000", topInfo);
    topInfoLayout->addWidget(new QLabel("Status", topInfo));
    topInfoLayout->addWidget(topCameraLabel_);
    topInfoLayout->addWidget(topCoordsLabel_);
    topInfoLayout->addStretch(1);
    topInfoLayout->addWidget(saveQuickBtn);
    connect(saveQuickBtn, &QPushButton::clicked, this, &MainWindow::saveProfile);

    auto* cameraGroup = new QGroupBox("Camera", this);
    auto* cameraForm = new QFormLayout(cameraGroup);
    cameraForm->setLabelAlignment(Qt::AlignLeft);
    cameraForm->setFormAlignment(Qt::AlignTop);
    cameraForm->setContentsMargins(10, 12, 10, 10);
    cameraCombo_ = new QComboBox(cameraGroup);
    cameraCombo_->setMinimumWidth(220);
    auto* openCameraBtn = new QPushButton("Open camera", cameraGroup);
    auto* closeCameraBtn = new QPushButton("Close camera", cameraGroup);
    cameraForm->addRow("Device", cameraCombo_);
    cameraForm->addRow("", openCameraBtn);
    cameraForm->addRow("", closeCameraBtn);

    cameraPreviewWidget_ = new PreviewWidget(this);
    connect(openCameraBtn, &QPushButton::clicked, this, &MainWindow::connectCamera);
    connect(closeCameraBtn, &QPushButton::clicked, this, [this]() {
        cameraManager_.closeDevice();
        cameraPreviewWidget_->setFrame({});
        appendLog("Camera closed");
    });

    detectionLabel_ = new QLabel("Detection: idle", this);
    calibrationLabel_ = new QLabel("Calibration: not set", this);
    cameraStatusLabel_ = new QLabel("Camera settings: default", this);
    positionLabel_ = new QLabel("Position: X0 Y0 Z0", this);

    auto* cameraSettingsGroup = new QGroupBox("Camera Settings", this);
    auto* cameraSettingsForm = new QFormLayout(cameraSettingsGroup);
    cameraSettingsForm->setLabelAlignment(Qt::AlignLeft);
    cameraSettingsForm->setFormAlignment(Qt::AlignTop);
    cameraSettingsForm->setContentsMargins(10, 12, 10, 10);
    resolutionCombo_ = new QComboBox(cameraSettingsGroup);
    resolutionCombo_->addItems({"640x480", "1280x720", "1920x1080"});
    pixelFormatCombo_ = new QComboBox(cameraSettingsGroup);
    pixelFormatCombo_->addItems({"MJPEG", "YUY2", "RGB24"});
    exposureSpin_ = new QDoubleSpinBox(cameraSettingsGroup);
    gainSpin_ = new QDoubleSpinBox(cameraSettingsGroup);
    displayScaleSpin_ = new QDoubleSpinBox(cameraSettingsGroup);
    exposureSpin_->setRange(-1.0, 10000.0);
    gainSpin_->setRange(-1.0, 100.0);
    displayScaleSpin_->setRange(25.0, 200.0);
    displayScaleSpin_->setValue(100.0);
    exposureSpin_->setValue(-1.0);
    gainSpin_->setValue(-1.0);
    auto* applyCameraBtn = new QPushButton("Apply camera settings", cameraSettingsGroup);
    cameraSettingsForm->addRow("Resolution", resolutionCombo_);
    cameraSettingsForm->addRow("Format", pixelFormatCombo_);
    cameraSettingsForm->addRow("Exposure", exposureSpin_);
    cameraSettingsForm->addRow("Gain", gainSpin_);
    cameraSettingsForm->addRow("Preview scale %", displayScaleSpin_);
    cameraSettingsForm->addRow("", applyCameraBtn);
    connect(applyCameraBtn, &QPushButton::clicked, this, &MainWindow::applyCameraSettings);

    auto* detectionSettingsGroup = new QGroupBox("Detection Settings", this);
    auto* detectionSettingsForm = new QFormLayout(detectionSettingsGroup);
    detectionSettingsForm->setLabelAlignment(Qt::AlignLeft);
    detectionSettingsForm->setFormAlignment(Qt::AlignTop);
    detectionSettingsForm->setContentsMargins(10, 12, 10, 10);
    edgeThresholdSpin_ = new QDoubleSpinBox(detectionSettingsGroup);
    minContourAreaSpin_ = new QDoubleSpinBox(detectionSettingsGroup);
    detectModeCombo_ = new QComboBox(detectionSettingsGroup);
    autoDetectBtn_ = new QPushButton("Run auto detect", detectionSettingsGroup);
    edgeThresholdSpin_->setRange(0.0, 255.0);
    edgeThresholdSpin_->setValue(80.0);
    minContourAreaSpin_->setRange(0.0, 1000000.0);
    minContourAreaSpin_->setValue(1500.0);
    detectModeCombo_->addItems({"Auto edge", "Circle/arc", "Manual ROI"});
    detectionSettingsForm->addRow("Edge threshold", edgeThresholdSpin_);
    detectionSettingsForm->addRow("Min area", minContourAreaSpin_);
    detectionSettingsForm->addRow("Mode", detectModeCombo_);
    detectionSettingsForm->addRow("", autoDetectBtn_);
    connect(autoDetectBtn_, &QPushButton::clicked, this, &MainWindow::applyDetectionSettings);

    auto* roiGroup = new QGroupBox("Manual ROI", this);
    auto* roiForm = new QFormLayout(roiGroup);
    roiForm->setLabelAlignment(Qt::AlignLeft);
    roiForm->setFormAlignment(Qt::AlignTop);
    roiForm->setContentsMargins(10, 12, 10, 10);
    roiX_ = new QDoubleSpinBox(roiGroup);
    roiY_ = new QDoubleSpinBox(roiGroup);
    roiW_ = new QDoubleSpinBox(roiGroup);
    roiH_ = new QDoubleSpinBox(roiGroup);
    for (auto* spin : {roiX_, roiY_, roiW_, roiH_}) {
        spin->setRange(0.0, 100000.0);
        spin->setDecimals(1);
        spin->setSingleStep(5.0);
    }
    roiW_->setValue(400);
    roiH_->setValue(300);
    auto* setRoiBtn = new QPushButton("Apply ROI", roiGroup);
    roiForm->addRow("X", roiX_);
    roiForm->addRow("Y", roiY_);
    roiForm->addRow("W", roiW_);
    roiForm->addRow("H", roiH_);
    roiForm->addRow("", setRoiBtn);
    connect(setRoiBtn, &QPushButton::clicked, this, &MainWindow::setManualRoi);

    auto* calGroup = new QGroupBox("Calibration", this);
    auto* calForm = new QFormLayout(calGroup);
    calForm->setLabelAlignment(Qt::AlignLeft);
    calForm->setFormAlignment(Qt::AlignTop);
    calForm->setContentsMargins(10, 12, 10, 10);
    pixelSizeMm_ = new QDoubleSpinBox(calGroup);
    rotationOffset_ = new QDoubleSpinBox(calGroup);
    pixelSizeMm_->setRange(0.0001, 100.0);
    pixelSizeMm_->setDecimals(4);
    pixelSizeMm_->setValue(0.01);
    rotationOffset_->setRange(-180.0, 180.0);
    rotationOffset_->setDecimals(3);
    auto* calibrateBtn = new QPushButton("Save calibration", calGroup);
    auto* heightMapBtn = new QPushButton("Create height map", calGroup);
    calForm->addRow("Pixel size mm", pixelSizeMm_);
    calForm->addRow("Rotation deg", rotationOffset_);
    calForm->addRow("", calibrateBtn);
    calForm->addRow("", heightMapBtn);
    connect(calibrateBtn, &QPushButton::clicked, this, &MainWindow::calibrateCamera);
    connect(heightMapBtn, &QPushButton::clicked, this, &MainWindow::createHeightMap);

    auto* motionGroup = new QGroupBox("Motion", this);
    auto* motionForm = new QFormLayout(motionGroup);
    motionForm->setLabelAlignment(Qt::AlignLeft);
    motionForm->setFormAlignment(Qt::AlignTop);
    motionForm->setContentsMargins(10, 12, 10, 10);
    motionCombo_ = new QComboBox(motionGroup);
    auto* connectMotionBtn = new QPushButton("Connect motion", motionGroup);
    auto* homeBtn = new QPushButton("Home", motionGroup);
    auto* zeroBtn = new QPushButton("Set zero", motionGroup);
    spindleBtn_ = new QPushButton("Spindle off", motionGroup);
    jogStepX_ = new QDoubleSpinBox(motionGroup);
    jogStepY_ = new QDoubleSpinBox(motionGroup);
    jogStepZ_ = new QDoubleSpinBox(motionGroup);
    for (auto* spin : {jogStepX_, jogStepY_, jogStepZ_}) {
        spin->setRange(-1000.0, 1000.0);
        spin->setDecimals(3);
    }
    jogStepX_->setValue(1.0);
    jogStepY_->setValue(1.0);
    jogStepZ_->setValue(0.1);
    motionForm->addRow("Port", motionCombo_);
    motionForm->addRow("", connectMotionBtn);
    motionForm->addRow("", homeBtn);
    motionForm->addRow("", zeroBtn);
    auto* xyPad = new QWidget(motionGroup);
    auto* xyLayout = new QGridLayout(xyPad);
    auto* xMinusBtn = new QPushButton("X-", xyPad);
    auto* xPlusBtn = new QPushButton("X+", xyPad);
    auto* yMinusBtn = new QPushButton("Y-", xyPad);
    auto* yPlusBtn = new QPushButton("Y+", xyPad);
    auto* zMinusBtn = new QPushButton("Z-", xyPad);
    auto* zPlusBtn = new QPushButton("Z+", xyPad);
    xyLayout->addWidget(yPlusBtn, 0, 1);
    xyLayout->addWidget(xMinusBtn, 1, 0);
    xyLayout->addWidget(new QLabel("XY", xyPad), 1, 1, Qt::AlignCenter);
    xyLayout->addWidget(xPlusBtn, 1, 2);
    xyLayout->addWidget(yMinusBtn, 2, 1);
    xyLayout->addWidget(zMinusBtn, 3, 0);
    xyLayout->addWidget(zPlusBtn, 3, 2);
    motionForm->addRow("", spindleBtn_);
    motionForm->addRow("Jog X", jogStepX_);
    motionForm->addRow("Jog Y", jogStepY_);
    motionForm->addRow("Jog Z", jogStepZ_);
    motionForm->addRow("Move", xyPad);
    auto* jogBtn = new QPushButton("Jog", motionGroup);
    motionForm->addRow("", jogBtn);

    connect(connectMotionBtn, &QPushButton::clicked, this, &MainWindow::connectMotion);
    connect(jogBtn, &QPushButton::clicked, this, &MainWindow::moveJog);
    connect(homeBtn, &QPushButton::clicked, this, &MainWindow::homeMotion);
    connect(zeroBtn, &QPushButton::clicked, this, &MainWindow::zeroMotion);
    connect(spindleBtn_, &QPushButton::clicked, this, &MainWindow::spindleToggle);
    connect(xMinusBtn, &QPushButton::clicked, this, &MainWindow::moveXMinus);
    connect(xPlusBtn, &QPushButton::clicked, this, &MainWindow::moveXPlus);
    connect(yMinusBtn, &QPushButton::clicked, this, &MainWindow::moveYMinus);
    connect(yPlusBtn, &QPushButton::clicked, this, &MainWindow::moveYPlus);
    connect(zMinusBtn, &QPushButton::clicked, this, &MainWindow::moveZMinus);
    connect(zPlusBtn, &QPushButton::clicked, this, &MainWindow::moveZPlus);

    auto* profileGroup = new QGroupBox("Profiles", this);
    auto* profileForm = new QFormLayout(profileGroup);
    profileForm->setLabelAlignment(Qt::AlignLeft);
    profileForm->setFormAlignment(Qt::AlignTop);
    profileForm->setContentsMargins(10, 12, 10, 10);
    profileCombo_ = new QComboBox(profileGroup);
    auto* loadProfileBtn = new QPushButton("Load profile", profileGroup);
    auto* saveProfileBtn = new QPushButton("Save profile", profileGroup);
    profileForm->addRow("Profile", profileCombo_);
    profileForm->addRow("", loadProfileBtn);
    profileForm->addRow("", saveProfileBtn);
    connect(loadProfileBtn, &QPushButton::clicked, this, &MainWindow::loadProfile);
    connect(saveProfileBtn, &QPushButton::clicked, this, &MainWindow::saveProfile);

    logView_ = new QTextEdit(this);
    logView_->setReadOnly(true);

    auto* previewBox = new QWidget(this);
    auto* previewLayout = new QVBoxLayout(previewBox);
    previewLayout->setContentsMargins(0, 0, 0, 0);
    previewLayout->setSpacing(6);
    cameraPreviewWidget_->setMinimumHeight(460);
    previewLayout->addWidget(cameraPreviewWidget_, 1);
    previewLayout->addWidget(detectionLabel_);
    previewLayout->addWidget(cameraStatusLabel_);
    previewLayout->addWidget(positionLabel_);

    auto* tabs = new QTabWidget(this);
    tabs->addTab(cameraSettingsGroup, "Camera");
    tabs->addTab(detectionSettingsGroup, "Detection");
    tabs->addTab(roiGroup, "ROI");
    tabs->addTab(calGroup, "Calibration");
    tabs->addTab(motionGroup, "Motion");
    tabs->addTab(profileGroup, "Profiles");
    tabs->addTab(new DesignerPanelWidget(this), "Designer");
    tabs->addTab(logView_, "Log");
    tabs->setDocumentMode(true);
    tabs->setTabPosition(QTabWidget::North);

    mainRoot->addWidget(previewBox, 4);
    mainRoot->addWidget(topInfo);
    mainRoot->addWidget(tabs, 2);
    root->addLayout(mainRoot);
    setCentralWidget(central);
    statusBar()->showMessage("Ready");
    statusBar()->addPermanentWidget(new QLabel("Qt CNC Vision Workbench", this));

    connect(&motionController_, &MotionController::positionChanged, this, [this](const MotionPosition& pos) {
        positionLabel_->setText(QString("Position: X%1 Y%2 Z%3").arg(pos.x, 0, 'f', 3).arg(pos.y, 0, 'f', 3).arg(pos.z, 0, 'f', 3));
        if (topCoordsLabel_) {
            topCoordsLabel_->setText(QString("X: %1  Y: %2  Z: %3").arg(pos.x, 0, 'f', 3).arg(pos.y, 0, 'f', 3).arg(pos.z, 0, 'f', 3));
        }
    });
    connect(&motionController_, &MotionController::statusChanged, this, [this](const QString& text) {
        appendLog(QStringLiteral("Motion: %1").arg(text));
    });
    connect(&cameraManager_, &CameraManager::frameReady, this, &MainWindow::updateFrame);
    connect(&cameraManager_, &CameraManager::errorOccurred, this, [this](const QString& text) {
        appendLog(QStringLiteral("Camera error: %1").arg(text));
    });
    connect(&visionEngine_, &VisionEngine::analysisUpdated, this, [this](const DetectionResult& result) {
        detectionLabel_->setText(QString("Detection: angle %1 deg | confidence %2 | method %3")
                                     .arg(result.angleDeg, 0, 'f', 2)
                                     .arg(result.confidence, 0, 'f', 2)
                                     .arg(result.method));
    });
}

void MainWindow::applyTheme() {
    setStyleSheet(R"(
        QMainWindow { background: #11161d; color: #e8eef5; }
        QWidget { color: #e8eef5; font-size: 12px; }
        QToolBar {
            background: #0f141b;
            border: none;
            spacing: 6px;
            padding: 4px;
        }
        QToolButton {
            background: #202833;
            color: #e8eef5;
            border: 1px solid #314052;
            border-radius: 8px;
            padding: 6px 10px;
        }
        QToolButton:hover { background: #273242; }
        #TopInfo {
            background: #0f141b;
            border: 1px solid #314052;
            border-radius: 10px;
        }
        QGroupBox {
            border: 1px solid #2b3644;
            border-radius: 10px;
            margin-top: 12px;
            padding: 8px;
            background: #151b23;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
        }
        QPushButton, QComboBox, QDoubleSpinBox, QTextEdit, QTabBar::tab {
            background: #202833;
            border: 1px solid #314052;
            border-radius: 8px;
            padding: 6px;
            color: #e8eef5;
        }
        QPushButton:hover { background: #273242; }
        QLabel { padding: 2px; color: #d7e2ee; }
        QTabWidget::pane {
            border: 1px solid #314052;
            top: -1px;
            background: #151b23;
        }
        QTabBar::tab {
            min-width: 100px;
            padding: 8px 12px;
            margin-right: 2px;
            background: #1b232d;
            color: #f0f4f8;
        }
        QTabBar::tab:selected {
            background: #273242;
            color: #ffffff;
        }
        QTabBar::tab:!selected {
            color: #c9d4df;
        }
    )");
}

void MainWindow::refreshCameraList() {
    cameraCombo_->clear();
    cameraCombo_->addItems(cameraManager_.enumerateDevices());
    motionCombo_->clear();
    motionCombo_->addItems(motionController_.availablePorts());
    profileCombo_->clear();
    profileCombo_->addItems({"Default", "Workpiece", "HeightMap"});
}

void MainWindow::connectCamera() {
    const auto device = cameraCombo_->currentText();
    if (cameraManager_.openDevice(device)) {
        appendLog(QStringLiteral("Camera opened: %1").arg(device));
        cameraStatusLabel_->setText(QStringLiteral("Camera: %1").arg(device));
        if (topCameraLabel_) {
            topCameraLabel_->setText(QStringLiteral("Camera: %1").arg(device));
        }
    }
}

void MainWindow::updateFrame(const QImage& frame) {
    currentFrame_ = frame;
    refreshPreview();
}

void MainWindow::refreshPreview() {
    if (cameraPreviewWidget_) {
        cameraPreviewWidget_->setFrame(currentFrame_);
    }
}

void MainWindow::runDetection() {
    const QImage frame = currentFrame_;
    const auto result = visionEngine_.analyze(frame.isNull() ? QImage(1280, 720, QImage::Format_RGB32) : frame);
    if (result.valid) {
        appendLog(QStringLiteral("Detection completed. Angle=%1, confidence=%2")
                      .arg(result.angleDeg, 0, 'f', 2)
                      .arg(result.confidence, 0, 'f', 2));
    }
}

void MainWindow::applyCameraSettings() {
    auto profile = profileManager_.currentProfile();
    const auto res = resolutionCombo_->currentText().split('x');
    if (res.size() == 2) {
        profile.camera.width = res[0].toInt();
        profile.camera.height = res[1].toInt();
    }
    profile.camera.pixelFormat = pixelFormatCombo_->currentText();
    profile.camera.exposure = exposureSpin_->value();
    profile.camera.gain = gainSpin_->value();
    profile.cameraRuntime.displayScalePercent = static_cast<int>(displayScaleSpin_->value());
    cameraManager_.setSettings(profile.camera);
    profileManager_.setCurrentProfile(profile);
    cameraStatusLabel_->setText(QString("Camera settings: %1 %2x%3").arg(profile.camera.pixelFormat).arg(profile.camera.width).arg(profile.camera.height));
    appendLog("Camera settings applied");
    if (cameraManager_.isOpen()) {
        cameraManager_.openDevice(cameraCombo_->currentText());
    }
    if (topCameraLabel_) {
        topCameraLabel_->setText(QString("Camera: %1 %2x%3").arg(profile.camera.pixelFormat).arg(profile.camera.width).arg(profile.camera.height));
    }
}

void MainWindow::applyDetectionSettings() {
    auto profile = profileManager_.currentProfile();
    profile.detection.edgeThreshold = edgeThresholdSpin_->value();
    profile.detection.minContourArea = minContourAreaSpin_->value();
    profile.detection.detectCircleMode = detectModeCombo_->currentIndex() == 1;
    profile.detection.manualMode = detectModeCombo_->currentIndex() == 2;
    profileManager_.setCurrentProfile(profile);
    appendLog("Detection settings applied");
}

void MainWindow::setManualRoi() {
    const QRectF roi(roiX_->value(), roiY_->value(), roiW_->value(), roiH_->value());
    visionEngine_.setManualRoi(roi);
    auto profile = profileManager_.currentProfile();
    profile.manualRoi = roi;
    profileManager_.setCurrentProfile(profile);
    appendLog(QStringLiteral("ROI set: %1,%2 %3x%4").arg(roi.x()).arg(roi.y()).arg(roi.width()).arg(roi.height()));
}

void MainWindow::calibrateCamera() {
    auto profile = profileManager_.currentProfile();
    profile.calibration.pixelSizeMm = pixelSizeMm_->value();
    profile.calibration.rotationOffsetDeg = rotationOffset_->value();
    profile.calibration.distortionCorrected = true;
    profileManager_.setCurrentProfile(profile);
    visionEngine_.setCalibration(profile.calibration);
    calibrationLabel_->setText(QString("Calibration: %1 mm/px | rot %2 deg")
                                   .arg(profile.calibration.pixelSizeMm, 0, 'f', 4)
                                   .arg(profile.calibration.rotationOffsetDeg, 0, 'f', 2));
    appendLog("Calibration saved");
}

void MainWindow::createHeightMap() {
    auto profile = profileManager_.currentProfile();
    profile.heightMap.clear();
    for (int y = 0; y < 5; ++y) {
        for (int x = 0; x < 5; ++x) {
            profile.heightMap.push_back({x * 10.0, y * 10.0, qSin((x + y) / 2.0) * 0.12});
        }
    }
    profileManager_.setCurrentProfile(profile);
    appendLog(QStringLiteral("Height map created with %1 points").arg(profile.heightMap.size()));
}

void MainWindow::connectMotion() {
    if (motionController_.connectPort(motionCombo_->currentText())) {
        appendLog(QStringLiteral("Motion connected: %1").arg(motionCombo_->currentText()));
    }
}

void MainWindow::moveJog() { motionController_.jog(jogStepX_->value(), jogStepY_->value(), jogStepZ_->value()); }
void MainWindow::moveXPlus() { motionController_.jog(jogStepX_->value(), 0.0, 0.0); }
void MainWindow::moveXMinus() { motionController_.jog(-jogStepX_->value(), 0.0, 0.0); }
void MainWindow::moveYPlus() { motionController_.jog(0.0, jogStepY_->value(), 0.0); }
void MainWindow::moveYMinus() { motionController_.jog(0.0, -jogStepY_->value(), 0.0); }
void MainWindow::moveZPlus() { motionController_.jog(0.0, 0.0, jogStepZ_->value()); }
void MainWindow::moveZMinus() { motionController_.jog(0.0, 0.0, -jogStepZ_->value()); }
void MainWindow::homeMotion() { motionController_.home(); appendLog("Homing requested"); }
void MainWindow::zeroMotion() { motionController_.setZero(); appendLog("Zero set"); }
void MainWindow::spindleToggle() {
    static bool spindle = false;
    spindle = !spindle;
    motionController_.setSpindle(spindle);
    spindleBtn_->setText(spindle ? "Spindle on" : "Spindle off");
}

void MainWindow::saveProfile() {
    AppProfile profile = profileManager_.currentProfile();
    profile.name = profileCombo_->currentText().isEmpty() ? QStringLiteral("Default") : profileCombo_->currentText();
    profile.camera = cameraManager_.settings();
    profile.cameraRuntime.displayScalePercent = static_cast<int>(displayScaleSpin_->value());
    profile.detection.edgeThreshold = edgeThresholdSpin_->value();
    profile.detection.minContourArea = minContourAreaSpin_->value();
    profile.detection.detectCircleMode = detectModeCombo_->currentIndex() == 1;
    profile.detection.manualMode = detectModeCombo_->currentIndex() == 2;
    profileManager_.setCurrentProfile(profile);
    profileManager_.save();
    appendLog(QStringLiteral("Profile saved: %1").arg(profile.name));
}

void MainWindow::loadProfile() {
    const auto name = profileCombo_->currentText().isEmpty() ? QStringLiteral("Default") : profileCombo_->currentText();
    profileManager_.load(name);
    const auto profile = profileManager_.currentProfile();
    cameraManager_.setSettings(profile.camera);
    visionEngine_.setCalibration(profile.calibration);
    resolutionCombo_->setCurrentText(QString("%1x%2").arg(profile.camera.width).arg(profile.camera.height));
    pixelFormatCombo_->setCurrentText(profile.camera.pixelFormat);
    exposureSpin_->setValue(profile.camera.exposure);
    gainSpin_->setValue(profile.camera.gain);
    displayScaleSpin_->setValue(profile.cameraRuntime.displayScalePercent);
    edgeThresholdSpin_->setValue(profile.detection.edgeThreshold);
    minContourAreaSpin_->setValue(profile.detection.minContourArea);
    detectModeCombo_->setCurrentIndex(profile.detection.manualMode ? 2 : (profile.detection.detectCircleMode ? 1 : 0));
    if (profile.manualRoi.isValid()) {
        visionEngine_.setManualRoi(profile.manualRoi);
    }
    calibrationLabel_->setText(QString("Calibration: %1 mm/px | rot %2 deg")
                                   .arg(profile.calibration.pixelSizeMm, 0, 'f', 4)
                                   .arg(profile.calibration.rotationOffsetDeg, 0, 'f', 2));
    appendLog(QStringLiteral("Profile loaded: %1").arg(name));
}

void MainWindow::appendLog(const QString& text) {
    logView_->append(text);
    statusBar()->showMessage(text, 3000);
}
