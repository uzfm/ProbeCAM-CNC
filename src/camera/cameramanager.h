#pragma once

#include "models.h"

#include <QObject>
#include <QImage>
#include <QStringList>

#include <QMediaCaptureSession>
#include <QMediaDevices>
#include <QCamera>
#include <QCameraFormat>
#include <QVideoSink>

class CameraManager : public QObject {
    Q_OBJECT
public:
    explicit CameraManager(QObject* parent = nullptr);

    QStringList enumerateDevices() const;
    bool openDevice(const QString& deviceId);
    void closeDevice();
    bool isOpen() const;
    CameraSettings settings() const;
    void setSettings(const CameraSettings& settings);
    void setCameraDeviceById(const QString& deviceId);
    QImage lastFrame() const;

signals:
    void frameReady(const QImage& frame);
    void errorOccurred(const QString& message);

private:
    void onVideoFrameChanged(const QVideoFrame& frame);
    QCameraFormat chooseCameraFormat(const QCameraDevice& device) const;

    CameraSettings settings_;
    bool isOpen_ = false;
    QImage lastFrame_;
    QList<QCameraDevice> devices_;
    QMediaCaptureSession captureSession_;
    QCamera* camera_ = nullptr;
    QVideoSink* videoSink_ = nullptr;
};
