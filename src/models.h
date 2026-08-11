#pragma once

#include <QString>
#include <QPointF>
#include <QRectF>
#include <QVector>

struct CameraSettings {
    QString deviceId;
    QString deviceName;
    int width = 1280;
    int height = 720;
    int fps = 30;
    double exposure = -1.0;
    double gain = -1.0;
    QString pixelFormat = "MJPEG";
};

struct CameraRuntimeSettings {
    bool autoOpen = true;
    bool showColorPreview = true;
    int displayScalePercent = 100;
};

struct CalibrationData {
    double pixelSizeMm = 0.0;
    double cameraOffsetX = 0.0;
    double cameraOffsetY = 0.0;
    double rotationOffsetDeg = 0.0;
    bool distortionCorrected = false;
};

struct DetectionResult {
    bool valid = false;
    QPointF center;
    double angleDeg = 0.0;
    double confidence = 0.0;
    QRectF roi;
    QString method;
};

struct DetectionSettings {
    bool autoDetectEnabled = true;
    double edgeThreshold = 80.0;
    double minContourArea = 1500.0;
    bool detectCircleMode = true;
    bool manualMode = false;
};

struct MotionPosition {
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;
};

struct HeightMapPoint {
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;
};

struct AppProfile {
    QString name = "Default";
    CameraSettings camera;
    CameraRuntimeSettings cameraRuntime;
    CalibrationData calibration;
    DetectionSettings detection;
    QRectF manualRoi;
    QVector<HeightMapPoint> heightMap;
};
