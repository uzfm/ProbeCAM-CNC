#include "motion/motioncontroller.h"

MotionController::MotionController(QObject* parent)
    : QObject(parent) {}

bool MotionController::connectPort(const QString& portName) {
    Q_UNUSED(portName)
    connected_ = true;
    emit statusChanged(QStringLiteral("Connected"));
    return true;
}

void MotionController::disconnectPort() {
    connected_ = false;
    emit statusChanged(QStringLiteral("Disconnected"));
}

bool MotionController::isConnected() const {
    return connected_;
}

QStringList MotionController::availablePorts() const {
    QStringList ports;
    ports << QStringLiteral("COM3")
          << QStringLiteral("COM4")
          << QStringLiteral("/dev/ttyUSB0")
          << QStringLiteral("/dev/ttyACM0");
    if (ports.isEmpty()) {
        ports << QStringLiteral("COM3") << QStringLiteral("/dev/ttyUSB0");
    }
    return ports;
}

void MotionController::jog(double dx, double dy, double dz) {
    position_.x += dx;
    position_.y += dy;
    position_.z += dz;
    emit positionChanged(position_);
}

void MotionController::home() {
    position_ = {};
    emit positionChanged(position_);
}

void MotionController::setZero() {
    position_ = {};
    emit positionChanged(position_);
}

void MotionController::setSpindle(bool enabled) {
    emit statusChanged(enabled ? QStringLiteral("Spindle on") : QStringLiteral("Spindle off"));
}

MotionPosition MotionController::position() const {
    return position_;
}
