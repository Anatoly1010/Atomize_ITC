"""Persistent "last opened directory" memory, shared across the whole GUI.

File-open dialogs in the main window and its plot widgets fall back to the
configured ``open_dir`` / ``script_dir`` the first time, but should reopen in the
folder the user last browsed to. This module keeps that folder in a small text
file under ``libs/`` (the repo-wide runtime-IPC convention, same as
data_treatment's ``treatment_lastdir.txt``) so it survives a relaunch and is
shared between every dialog that uses the same ``key``.

Two keys are used by the app:
    'script'  - the experimental-script open/save dialogs (MainWindow)
    'data'    - the 1D/2D/TR data-open dialogs (NameList + CrosshairDock pyqtgraph
                menu) — one working data folder for all of them

Resolved against ``__file__`` (not the cwd), since main_window chdir's into
``libs/`` at startup.
"""

import os

_LIBS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'libs')


def _path(key):
    return os.path.join(_LIBS_DIR, '%s_lastdir.txt' % key)


def load(key, default=''):
    """Return the remembered directory for ``key``, or ``default`` if unset/stale."""
    try:
        with open(_path(key), 'r', errors='ignore') as fh:
            d = fh.read().strip()
        return d if d and os.path.isdir(d) else default
    except Exception:
        return default


def save(key, path):
    """Remember ``path`` (or its parent dir if it's a file) under ``key``."""
    try:
        d = path if os.path.isdir(path) else os.path.dirname(path)
        if d:
            with open(_path(key), 'w') as fh:
                fh.write(d)
    except Exception:
        pass
