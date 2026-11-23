"""The look of the GUI: qt-material with Praxis's own colours.

qt-material builds a whole Qt stylesheet (buttons, lists, inputs, scroll
bars) from a handful of colours in an XML file. ``praxis_theme.xml`` sets
them to constructivist red, black and cream.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

THEME_FILE = Path(__file__).with_name("praxis_theme.xml")

# Additions on top of qt-material's stylesheet: cream text on the red of a
# selected row, which qt-material leaves black. Qt takes a selected item's
# text colour from ``selection-color`` on the item rule, not from ``color``.
EXTRA_STYLESHEET = """
QListView::item:selected,
QListView::item:selected:focus {
  selection-color: #fbf7ee;
}
"""


def apply_theme(app: QApplication) -> None:
    # Imported here, after PySide6, because qt-material picks its Qt binding
    # from whichever one is already loaded.
    from qt_material import apply_stylesheet

    apply_stylesheet(
        app,
        theme=str(THEME_FILE),
        invert_secondary=True,  # a light theme: cream background, dark text
        extra={"density_scale": "0", "font_family": "Roboto"},
    )
    app.setStyleSheet(app.styleSheet() + EXTRA_STYLESHEET)
