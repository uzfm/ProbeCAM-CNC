#pragma once

#include "models.h"

#include <QObject>
#include <QImage>
#include <QRectF>

class VisionEngine : public QObject {
    Q_OBJECT
public:
    explicit VisionEngine(QObject* parent = nullptr);

    void setManualRoi(const QRectF& roi);
    void setCalibration(const CalibrationData& calibration);
    DetectionResult analyze(const QImage& frame);

signals:
    void analysisUpdated(const DetectionResult& result);

private:
    QRectF manualRoi_;
    CalibrationData calibration_;
};
