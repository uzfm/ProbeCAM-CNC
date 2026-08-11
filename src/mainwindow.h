#pragma once

#include "camera/cameramanager.h"
#include "designerpanel.h"
#include "motion/motioncontroller.h"
#include "persistence/profilemanager.h"
#include "vision/visionengine.h"

#include <QMainWindow>
#include <QImage>

class QLabel;
class QWidget;
class QTextEdit;
class QComboBox;
class QPushButton;
class QDoubleSpinBox;
class PreviewWidget;

class MainWindow : public QMainWindow {
    Q_OBJECT
public:
    explicit MainWindow(QWidget* parent = nullptr);

private slots:
    void refreshCameraList();
    void connectCamera();
    void runDetection();
    void updateFrame(const QImage& frame);
    void setManualRoi();
    void applyCameraSettings();
    void applyDetectionSettings();
    void calibrateCamera();
    void createHeightMap();
    void connectMotion();
    void moveJog();
    void moveXPlus();
    void moveXMinus();
    void moveYPlus();
    void moveYMinus();
    void moveZPlus();
    void moveZMinus();
    void homeMotion();
    void zeroMotion();
    void spindleToggle();
    void saveProfile();
    void loadProfile();

private:
    void buildUi();
    void appendLog(const QString& text);
    void applyTheme();
    void refreshPreview();

    CameraManager cameraManager_;
    VisionEngine visionEngine_;
    MotionController motionController_;
    ProfileManager profileManager_;

    QComboBox* cameraCombo_ = nullptr;
    QComboBox* motionCombo_ = nullptr;
    QComboBox* profileCombo_ = nullptr;
    PreviewWidget* cameraPreviewWidget_ = nullptr;
    QLabel* detectionLabel_ = nullptr;
    QLabel* positionLabel_ = nullptr;
    QLabel* calibrationLabel_ = nullptr;
    QLabel* cameraStatusLabel_ = nullptr;
    QLabel* topCameraLabel_ = nullptr;
    QLabel* topCoordsLabel_ = nullptr;
    QTextEdit* logView_ = nullptr;
    QComboBox* resolutionCombo_ = nullptr;
    QComboBox* pixelFormatCombo_ = nullptr;
    QDoubleSpinBox* exposureSpin_ = nullptr;
    QDoubleSpinBox* gainSpin_ = nullptr;
    QDoubleSpinBox* displayScaleSpin_ = nullptr;
    QDoubleSpinBox* edgeThresholdSpin_ = nullptr;
    QDoubleSpinBox* minContourAreaSpin_ = nullptr;
    QComboBox* detectModeCombo_ = nullptr;
    QPushButton* autoDetectBtn_ = nullptr;
    QDoubleSpinBox* jogStepX_ = nullptr;
    QDoubleSpinBox* jogStepY_ = nullptr;
    QDoubleSpinBox* jogStepZ_ = nullptr;
    QPushButton* spindleBtn_ = nullptr;
    QDoubleSpinBox* roiX_ = nullptr;
    QDoubleSpinBox* roiY_ = nullptr;
    QDoubleSpinBox* roiW_ = nullptr;
    QDoubleSpinBox* roiH_ = nullptr;
    QDoubleSpinBox* pixelSizeMm_ = nullptr;
    QDoubleSpinBox* rotationOffset_ = nullptr;
    QImage currentFrame_;
};
