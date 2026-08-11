#pragma once

#include "models.h"

#include <QObject>

class ProfileManager : public QObject {
    Q_OBJECT
public:
    explicit ProfileManager(QObject* parent = nullptr);

    AppProfile currentProfile() const;
    void setCurrentProfile(const AppProfile& profile);
    bool save();
    bool load(const QString& name);

signals:
    void profileChanged(const AppProfile& profile);

private:
    AppProfile profile_;
};
