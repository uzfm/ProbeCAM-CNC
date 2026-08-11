#include "mainwindow.h"

#include <QApplication>
#include <QCoreApplication>

int main(int argc, char* argv[]) {
    QApplication app(argc, argv);
    QCoreApplication::setOrganizationName("ProbeCAM");
    QCoreApplication::setApplicationName("ProbeCAM CNC");

    MainWindow window;
    window.resize(1400, 900);
    window.show();
    return app.exec();
}
