#pragma once

#include "models.h"

#include <QObject>
#include <QStringList>

class MotionController : public QObject {
    Q_OBJECT
public:
    explicit MotionController(QObject* parent = nullptr);

    bool connectPort(const QString& portName);
    void disconnectPort();
    bool isConnected() const;
    QStringList availablePorts() const;
    void jog(double dx, double dy, double dz);
    void home();
    void setZero();
    void setSpindle(bool enabled);
    MotionPosition position() const;

signals:
    void statusChanged(const QString& status);
    void positionChanged(const MotionPosition& position);
    void errorOccurred(const QString& message);

private:
    bool connected_ = false;
    MotionPosition position_;
};
