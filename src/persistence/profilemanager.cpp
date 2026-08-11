#include "persistence/profilemanager.h"

#include "appconfig.h"

ProfileManager::ProfileManager(QObject* parent)
    : QObject(parent) {}

AppProfile ProfileManager::currentProfile() const {
    return profile_;
}

void ProfileManager::setCurrentProfile(const AppProfile& profile) {
    profile_ = profile;
    emit profileChanged(profile_);
}

bool ProfileManager::save() {
    AppConfig config;
    config.saveProfile(profile_);
    return true;
}

bool ProfileManager::load(const QString& name) {
    AppConfig config;
    profile_ = config.loadProfile(name);
    emit profileChanged(profile_);
    return true;
}
