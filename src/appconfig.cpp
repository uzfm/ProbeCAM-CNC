#include "appconfig.h"

#include <QCoreApplication>

AppConfig::AppConfig()
    : settings_(QCoreApplication::organizationName().isEmpty() ? QStringLiteral("ProbeCAM") : QCoreApplication::organizationName(),
                QCoreApplication::applicationName().isEmpty() ? QStringLiteral("ProbeCAMCNC") : QCoreApplication::applicationName()) {}

AppProfile AppConfig::loadProfile(const QString& name) {
    AppProfile profile;
    settings_.beginGroup(QStringLiteral("profiles/%1").arg(name));
    profile.name = name;
    profile.camera.deviceId = settings_.value("camera/deviceId").toString();
    profile.camera.deviceName = settings_.value("camera/deviceName").toString();
    profile.camera.width = settings_.value("camera/width", 1280).toInt();
    profile.camera.height = settings_.value("camera/height", 720).toInt();
    profile.camera.fps = settings_.value("camera/fps", 30).toInt();
    profile.camera.exposure = settings_.value("camera/exposure", -1.0).toDouble();
    profile.camera.gain = settings_.value("camera/gain", -1.0).toDouble();
    profile.camera.pixelFormat = settings_.value("camera/pixelFormat", "MJPEG").toString();
    profile.calibration = loadCalibration(name);
    profile.manualRoi = settings_.value("vision/manualRoi").toRectF();
    settings_.endGroup();
    return profile;
}

void AppConfig::saveProfile(const AppProfile& profile) {
    settings_.beginGroup(QStringLiteral("profiles/%1").arg(profile.name));
    settings_.setValue("camera/deviceId", profile.camera.deviceId);
    settings_.setValue("camera/deviceName", profile.camera.deviceName);
    settings_.setValue("camera/width", profile.camera.width);
    settings_.setValue("camera/height", profile.camera.height);
    settings_.setValue("camera/fps", profile.camera.fps);
    settings_.setValue("camera/exposure", profile.camera.exposure);
    settings_.setValue("camera/gain", profile.camera.gain);
    settings_.setValue("camera/pixelFormat", profile.camera.pixelFormat);
    settings_.setValue("vision/manualRoi", profile.manualRoi);
    settings_.endGroup();
    saveCalibration(profile.name, profile.calibration);
}

QStringList AppConfig::availableProfiles() {
    settings_.beginGroup("profiles");
    const auto keys = settings_.childGroups();
    settings_.endGroup();
    return keys;
}

void AppConfig::saveCalibration(const QString& profileName, const CalibrationData& calibration) {
    settings_.beginGroup(QStringLiteral("profiles/%1/calibration").arg(profileName));
    settings_.setValue("pixelSizeMm", calibration.pixelSizeMm);
    settings_.setValue("cameraOffsetX", calibration.cameraOffsetX);
    settings_.setValue("cameraOffsetY", calibration.cameraOffsetY);
    settings_.setValue("rotationOffsetDeg", calibration.rotationOffsetDeg);
    settings_.setValue("distortionCorrected", calibration.distortionCorrected);
    settings_.endGroup();
}

CalibrationData AppConfig::loadCalibration(const QString& profileName) {
    CalibrationData calibration;
    settings_.beginGroup(QStringLiteral("profiles/%1/calibration").arg(profileName));
    calibration.pixelSizeMm = settings_.value("pixelSizeMm", 0.0).toDouble();
    calibration.cameraOffsetX = settings_.value("cameraOffsetX", 0.0).toDouble();
    calibration.cameraOffsetY = settings_.value("cameraOffsetY", 0.0).toDouble();
    calibration.rotationOffsetDeg = settings_.value("rotationOffsetDeg", 0.0).toDouble();
    calibration.distortionCorrected = settings_.value("distortionCorrected", false).toBool();
    settings_.endGroup();
    return calibration;
}
