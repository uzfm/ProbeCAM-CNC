#include "camera/cameramanager.h"

#include <QPainter>
#include <QVideoFrame>

CameraManager::CameraManager(QObject* parent)
    : QObject(parent) {
    videoSink_ = new QVideoSink(this);
    connect(videoSink_, &QVideoSink::videoFrameChanged, this, &CameraManager::onVideoFrameChanged);
    captureSession_.setVideoSink(videoSink_);
}

QStringList CameraManager::enumerateDevices() const {
    QStringList devices;
    devices << QStringLiteral("Auto");
    for (const auto& device : QMediaDevices::videoInputs()) {
        devices << device.description();
    }
    return devices;
}

bool CameraManager::openDevice(const QString& deviceId) {
    closeDevice();
    devices_ = QMediaDevices::videoInputs();
    QCameraDevice selected;
    if (deviceId == QStringLiteral("Auto") || devices_.isEmpty()) {
        if (!devices_.isEmpty()) {
            selected = devices_.first();
        }
    } else {
        for (const auto& device : devices_) {
            if (device.description() == deviceId) {
                selected = device;
                break;
            }
        }
    }

    if (!selected.isNull()) {
        camera_ = new QCamera(selected, this);
        const auto preferredFormat = chooseCameraFormat(selected);
        if (!preferredFormat.resolution().isEmpty()) {
            camera_->setCameraFormat(preferredFormat);
        }
        captureSession_.setCamera(camera_);
        camera_->start();
        settings_.deviceId = deviceId;
        settings_.deviceName = selected.description();
        isOpen_ = true;
        return true;
    }

    settings_.deviceId = deviceId;
    settings_.deviceName = deviceId;
    isOpen_ = true;
    lastFrame_ = QImage(1280, 720, QImage::Format_RGB32);
    lastFrame_.fill(Qt::black);
    emit frameReady(lastFrame_);
    return true;
}

void CameraManager::closeDevice() {
    if (camera_) {
        camera_->stop();
        camera_->deleteLater();
        camera_ = nullptr;
    }
    isOpen_ = false;
    lastFrame_ = {};
}

bool CameraManager::isOpen() const {
    return isOpen_;
}

CameraSettings CameraManager::settings() const {
    return settings_;
}

void CameraManager::setSettings(const CameraSettings& settings) {
    settings_ = settings;
}

void CameraManager::setCameraDeviceById(const QString& deviceId) {
    settings_.deviceId = deviceId;
}

QImage CameraManager::lastFrame() const {
    return lastFrame_;
}

void CameraManager::onVideoFrameChanged(const QVideoFrame& frame) {
    if (!frame.isValid()) {
        return;
    }
    QVideoFrame clone(frame);
    if (!clone.map(QVideoFrame::ReadOnly)) {
        return;
    }
    QImage image = clone.toImage();
    clone.unmap();
    if (!image.isNull()) {
        if (image.format() == QImage::Format_Grayscale8 || image.format() == QImage::Format_Indexed8 || image.format() == QImage::Format_Mono) {
            image = image.convertToFormat(QImage::Format_RGB32);
        } else if (image.format() != QImage::Format_RGB32 && image.format() != QImage::Format_ARGB32 && image.format() != QImage::Format_RGBA8888) {
            image = image.convertToFormat(QImage::Format_RGB32);
        }
        lastFrame_ = image;
        emit frameReady(lastFrame_);
    }
}

QCameraFormat CameraManager::chooseCameraFormat(const QCameraDevice& device) const {
    const QSize targetSize(settings_.width, settings_.height);
    QCameraFormat fallback;

    for (const auto& format : device.videoFormats()) {
        if (format.resolution() == targetSize) {
            const auto pf = format.pixelFormat();
            if (pf != QVideoFrameFormat::Format_Y8 && pf != QVideoFrameFormat::Format_Y16) {
                return format;
            }
            fallback = format;
        }
    }

    if (!fallback.resolution().isEmpty()) {
        return fallback;
    }

    const auto formats = device.videoFormats();
    for (const auto& format : formats) {
        const auto pf = format.pixelFormat();
        if (pf != QVideoFrameFormat::Format_Y8 && pf != QVideoFrameFormat::Format_Y16) {
            return format;
        }
    }

    if (!formats.isEmpty()) {
        return formats.first();
    }

    return {};
}
