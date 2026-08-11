#pragma once

#include <QWidget>

namespace Ui {
class DesignerPanelWidget;
}

class DesignerPanelWidget : public QWidget {
    Q_OBJECT
public:
    explicit DesignerPanelWidget(QWidget* parent = nullptr);
    ~DesignerPanelWidget() override;

private:
    Ui::DesignerPanelWidget* ui_;
};
