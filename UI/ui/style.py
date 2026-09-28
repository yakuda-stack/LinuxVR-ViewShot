"""
ui/style.py – Aussehen der App (Stylesheet), übernommen von OSC-DreamChatbox.

Widgets bekommen ihr Aussehen über setObjectName(...):
    "sidebar"   linke Leiste
    "navbtn"    Menü-Knopf in der Leiste
    "pagetitle" große Seitenüberschrift
    "card"      dunkle Karte mit runden Ecken
    "cardtitle" Überschrift in einer Karte
    "dim"       grauer, kleiner Text
    "sendbtn"   blauer Haupt-Knopf
    "linkbtn"   grauer Knopf
"""

STYLE = """
QMainWindow { background: #14161c; }
QWidget { color: #d7dbe2; font-size: 14px; background: transparent; }
QStackedWidget, QStackedWidget > QWidget { background: #14161c; }
#sidebar { background: #0f1116; }
#apptitle { font-size: 20px; font-weight: 700; color: #ffffff; padding: 0 4px 12px 4px; }
#navbtn {
    background: transparent; border: none; border-radius: 10px;
    padding: 16px 18px; text-align: left; color: #aeb4bf; font-size: 18px;
}
#navbtn:checked { background: #2a2f3a; color: #ffffff; }
#navbtn:hover { background: #232833; }
#pagetitle { font-size: 26px; font-weight: 700; color: #ffffff; }
#card { background: #191c24; border-radius: 12px; }
#cardtitle { font-size: 19px; font-weight: 600; color: #ffffff; }
#dim { color: #7a8290; font-size: 12px; }
#ok { color: #6fae72; font-weight: 600; }
#bad { color: #c95b5b; font-weight: 600; }
#photo { background: #14161c; border: 1px solid #2c313c; border-radius: 10px; }
#sendbtn {
    background: #5b8dc9; color: #ffffff; border: none; border-radius: 8px;
    padding: 8px 16px; font-weight: 600;
}
#sendbtn:hover { background: #6d9cd4; }
#sendbtn:pressed { background: #4c7cb5; }
#linkbtn {
    background: #232833; color: #e5e9ef; border: 1px solid #333947;
    border-radius: 8px; padding: 6px 16px; font-weight: 600;
}
#linkbtn:hover { background: #2f3542; border-color: #5b8dc9; }
#linkbtn::menu-indicator { image: none; width: 0; }
#arrowbtn {
    background: #191c24; color: #aeb4bf; border: 1px solid #2c313c;
    border-radius: 10px; font-size: 48px; font-weight: 400; padding-bottom: 6px;
}
#arrowbtn:hover { background: #232833; color: #ffffff; border-color: #5b8dc9; }
#arrowbtn:disabled { color: #2c313c; border-color: #1d2029; }
#actionbtn {
    background: #232833; color: #e5e9ef; border: 1px solid #333947;
    border-radius: 10px; padding: 12px 14px; font-size: 15px; font-weight: 600;
    min-height: 24px;
}
#actionbtn:hover { background: #2f3542; border-color: #5b8dc9; }
#actionbtn:disabled { color: #7a8290; }
#actionbtn::menu-indicator { image: none; width: 0; }
#tabbtn {
    background: #232833; border: 1px solid #333947; border-radius: 8px;
    color: #aeb4bf; padding: 8px 16px; font-weight: 600;
}
#tabbtn:hover { border-color: #5b8dc9; }
#tabbtn:checked { background: #5b8dc9; border-color: #5b8dc9; color: #ffffff; }
#dangerbtn {
    background: #232833; color: #e5e9ef; border: 1px solid #333947;
    border-radius: 10px; padding: 12px 14px; font-size: 15px; font-weight: 600;
    min-height: 24px;
}
#dangerbtn:hover { background: #c95b5b; border-color: #c95b5b; color: #ffffff; }
QSlider::groove:horizontal { height: 6px; background: #2c313c; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #5b8dc9; border-radius: 3px; }
QSlider::handle:horizontal {
    background: #e8ecf2; width: 22px; height: 22px; margin: -8px 0; border-radius: 11px;
}
QSlider::handle:horizontal:hover { background: #ffffff; }
QSlider { min-height: 30px; }
#toast { color: #6fae72; font-weight: 700; font-size: 16px; min-height: 24px; }
QMenu {
    background: #191c24; color: #e5e9ef; border: 1px solid #333947; padding: 4px;
}
QMenu::item { padding: 10px 22px; font-size: 15px; }
QMenu::item:selected { background: #2a2f3a; }
QMenu::item:disabled { color: #7a8290; }
QMessageBox { background: #191c24; }
QDialog { background: #14161c; }
QMessageBox QLabel { color: #e5e9ef; font-size: 15px; }
QMessageBox QPushButton {
    background: #232833; color: #e5e9ef; border: 1px solid #333947;
    border-radius: 8px; padding: 8px 24px; min-width: 60px;
}
QPlainTextEdit {
    background: #14161c; border: 1px solid #2c313c; border-radius: 8px;
    padding: 6px; color: #aeb4bf;
}
QTextBrowser {
    background: #14161c; border: 1px solid #2c313c; border-radius: 8px;
    padding: 6px; color: #aeb4bf;
}
#translation { color: #ffffff; font-size: 17px; }
#trwindow { background: #191c24; }
#foldbtn {
    background: transparent; border: none; color: #7a8290; font-size: 13px;
    padding: 2px 4px; text-align: left;
}
#foldbtn:hover { color: #d7dbe2; }
QCheckBox { spacing: 10px; font-size: 15px; }
QCheckBox::indicator {
    width: 22px; height: 22px; border: 1px solid #444c5c; border-radius: 5px; background: #14161c;
}
QCheckBox::indicator:checked { background: #5b8dc9; border-color: #5b8dc9; }
QLineEdit {
    background: #14161c; border: 1px solid #333947; border-radius: 8px;
    padding: 8px 10px; color: #e5e9ef;
}
QComboBox {
    background: #14161c; border: 1px solid #333947; border-radius: 8px;
    padding: 6px 10px; color: #e5e9ef;
}
QComboBox:hover { border-color: #444c5c; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: #191c24; color: #e5e9ef; border: 1px solid #333947;
    selection-background-color: #2a2f3a;
}
QListWidget {
    background: #191c24; border: none; border-radius: 12px; padding: 8px;
}
QListWidget::item { border-radius: 8px; padding: 4px; color: #aeb4bf; }
QListWidget::item:hover { background: #232833; }
QListWidget::item:selected { background: #2a2f3a; color: #ffffff; }
QScrollArea { border: none; background: #14161c; }
QScrollBar:vertical { background: #14161c; width: 10px; margin: 0; border: none; }
QScrollBar::handle:vertical { background: #2c313c; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #3a4150; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
"""
