"""Shared presentation for the image and audio settings pages."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QLabel, QScrollArea, QVBoxLayout,
                               QTabWidget, QSizePolicy, QComboBox)


SETTINGS_STYLE = '''
QWidget#settingsPanel, QWidget#audioSettingsContent { background: transparent; border: 0; }
QFrame#settingsCard { background: #192337; border: 1px solid #304057; border-radius: 10px; }
QLabel#settingsTitle { color: #f2f7ff; font-size: 17px; font-weight: 600; }
QLabel#settingsSection { color: #e9f0fa; font-size: 13px; font-weight: 600; }
QLabel#settingsHint { color: #90a5bf; font-size: 12px; background: transparent; }
QLabel#settingsLabel { color: #c9d7ed; font-size: 12px; background: transparent; }
QLabel#settingsStatus { color: #95baf6; font-size: 12px; background: transparent; }
QTabWidget#settingsTabs::pane { border: 0; }
QTabWidget#settingsTabs QTabBar::tab { color: #90a5bf; background: transparent;
    border: 0; border-bottom: 2px solid transparent; padding: 9px 10px; font-size: 12px; }
QTabWidget#settingsTabs QTabBar::tab:selected { color: #eff5ff; border-bottom-color: #6faef5; }
QTabWidget#settingsTabs QTabBar::tab:hover { color: #eff5ff; background: #253348; }
QPushButton[role="settingsNav"] { background: transparent; border-color: #354962; color: #90a5bf; }
QPushButton[role="settingsNav"]:checked { background: #264b77; border-color: #507ba9; color: #ffffff; }
QLineEdit, QComboBox, QSpinBox { background: #101a2a; color: #ecf3fb;
    border: 1px solid #3d526e; border-radius: 8px; padding: 7px;
    selection-background-color: #2b6ab4; font-size: 12px; min-height: 19px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #6faef5; }
QComboBox QAbstractItemView { background: #182338; color: #ecf3fb; selection-background-color: #2c5f98; }
QPushButton { background: #253348; border: 1px solid #354962; color: #e7f0fb;
    border-radius: 8px; padding: 6px 10px; font-size: 12px; min-height: 22px; }
QPushButton:hover { background: #344863; border-color: #5578a4; }
QPushButton:disabled { color: #6e8198; background: #1d2a3b; border-color: #29384b; }
QPushButton[role="primary"] { background: #245eaa; border-color: #377ac9; color: white; }
QPushButton[role="primary"]:hover { background: #2c70c4; }
QCheckBox { color: #dce8f8; spacing: 8px; font-size: 12px; }
QScrollBar:vertical { background: #172337; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #456080; border-radius: 4px; min-height: 22px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
'''


def text_label(text, name='settingsHint'):
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(True)
    # Native font metrics must not turn a wrapped caption into a fixed width.
    policy = label.sizePolicy()
    policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
    label.setSizePolicy(policy)
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


def settings_tabs(parent_layout):
    tabs = QTabWidget()
    tabs.setObjectName('settingsTabs')
    tabs.setDocumentMode(True)
    tabs.tabBar().setDrawBase(False)
    tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
    parent_layout.addWidget(tabs, 1)
    return tabs


def tab_page(tabs, title):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setStyleSheet('QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: 0; }')
    page = QFrame()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 12, 2, 0)
    layout.setSpacing(12)
    scroll.setWidget(page)
    tabs.addTab(scroll, title)
    return layout


def card(parent_layout, title, description=''):
    frame = QFrame()
    frame.setObjectName('settingsCard')
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(9)
    layout.addWidget(text_label(title, 'settingsSection'))
    if description:
        layout.addWidget(text_label(description))
    parent_layout.addWidget(frame)
    return layout


def field(layout, caption, widget):
    label = text_label(caption, 'settingsLabel')
    label.setBuddy(widget)
    layout.addWidget(label)
    if isinstance(widget, QComboBox):
        # Device names and model IDs can be much wider than the settings pane.
        # Keep their complete values; size the editor independently of them.
        widget.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        widget.setMinimumContentsLength(12)
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    layout.addWidget(widget)
    return label
