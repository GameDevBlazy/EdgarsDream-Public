"""Legacy entry point for the BBMODS Debug Editor.

This script previously hosted a stageset-only UI. It now simply imports
and launches the combined stage + mission tooling so existing shortcuts
continue to work without losing the Mission Actors tab.
"""

from __future__ import annotations

from pathlib import Path
import sys


def _ensure_project_root_on_path() -> None:
    project_root = Path(__file__).resolve().parents[2]
    root_str = str(project_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


_ensure_project_root_on_path()


from bbmods_debug_editor import BBMODSDebugEditor  # noqa: E402  pylint: disable=wrong-import-position


def main() -> None:
    editor = BBMODSDebugEditor()
    editor.mainloop()


if __name__ == "__main__":
    main()
