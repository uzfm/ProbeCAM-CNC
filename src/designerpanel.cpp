#include "designerpanel.h"

#include "ui_designerpanel.h"

DesignerPanelWidget::DesignerPanelWidget(QWidget* parent)
    : QWidget(parent)
    , ui_(new Ui::DesignerPanelWidget) {
    ui_->setupUi(this);
}

DesignerPanelWidget::~DesignerPanelWidget() {
    delete ui_;
}
