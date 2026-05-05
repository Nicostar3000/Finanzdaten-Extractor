"""App-Modul fuer die Diagramm-/Viewer-Ansicht.

Wrapper um die bestehende Implementierung in `src/gui_viewer.py`.
"""

from ..gui_viewer import DataViewerApp, load_and_view, show_data_viewer  # noqa: F401

__all__ = ["DataViewerApp", "load_and_view", "show_data_viewer"]

