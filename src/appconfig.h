#pragma once

#include "models.h"

#include <QSettings>

class AppConfig {
public:
    AppConfig();

    AppProfile loadProfile(const QString& name);
    void saveProfile(const AppProfile& profile);
    QStringList availableProfiles();
    void saveCalibration(const QString& profileName, const CalibrationData& calibration);
    CalibrationData loadCalibration(const QString& profileName);

private:
    QSettings settings_;
};
