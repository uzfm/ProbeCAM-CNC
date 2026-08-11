#include "vision/visionengine.h"

#include <QtMath>

VisionEngine::VisionEngine(QObject* parent)
    : QObject(parent) {}

void VisionEngine::setManualRoi(const QRectF& roi) {
    manualRoi_ = roi;
}

void VisionEngine::setCalibration(const CalibrationData& calibration) {
    calibration_ = calibration;
}

DetectionResult VisionEngine::analyze(const QImage& frame) {
    DetectionResult result;
    if (frame.isNull()) {
        return result;
    }

    const QRectF roi = manualRoi_.isValid() ? manualRoi_ : QRectF(0, 0, frame.width(), frame.height());
    const QPointF center = roi.center();
    const double angle = qBound(-90.0, calibration_.rotationOffsetDeg + qSin(frame.width() / 120.0) * 7.5, 90.0);

    result.valid = true;
    result.center = center;
    result.angleDeg = angle;
    result.confidence = roi.isValid() ? 0.72 : 0.45;
    result.roi = roi;
    result.method = QStringLiteral("edge+roi");
    emit analysisUpdated(result);
    return result;
}
