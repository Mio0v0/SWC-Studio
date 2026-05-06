"""Bootstrap entrypoint for the *modular* SWC-Studio bundle.

This file is the entrypoint compiled into the modular ``.app`` /
``.exe``. It is intentionally tiny and dependency-light. Its only job
is to:

1. Locate the ``swcstudio`` Python package (which is **not** baked into
   the PyInstaller bundle in modular mode) — preferring the user's
   downloaded override dir over the bundled-with-the-app copy.
2. Add that directory to ``sys.path``.
3. Call multiprocessing.freeze_support() — the standard PyInstaller fix
   that prevents joblib / torch worker spawns from re-launching the GUI.
4. Import and run ``swcstudio.gui.main.main``.

Why this matters
----------------
In the *monolithic* build (``packaging/swcstudio_gui.spec``), the
swcstudio package is frozen into the bundle. Updating any line of code
requires re-downloading the entire 700 MB ``.app``.

In the *modular* build (``packaging/swcstudio_gui_modular.spec``), the
swcstudio code lives as plain ``.py`` files at
``Contents/Resources/app/swcstudio/``. The auto-updater can drop a
fresh ``swcstudio/`` folder into the user override dir and the next
launch picks it up — no .app re-install.

Search order for the swcstudio package
--------------------------------------
1. **User override dir** — the auto-updater downloads here:
   * macOS:   ``~/Library/Application Support/SWC-Studio/app/swcstudio/``
   * Windows: ``%APPDATA%\\SWC-Studio\\app\\swcstudio\\``
   * Linux:   ``~/.local/share/swcstudio/app/swcstudio/``
2. **Bundled in the .app** — what ships at install time:
   ``<bundle>/Contents/Resources/app/swcstudio/``
   (or ``sys._MEIPASS/app/swcstudio/`` for one-folder PyInstaller)
3. **Source repo** — when running directly via ``python swcstudio_bootstrap.py``
   from a checkout, the repo's ``swcstudio/`` is used.

PyInstaller note
----------------
PyInstaller's static analyzer follows ``import`` statements at the top
of the entrypoint. Because we use ``__import__("swcstudio.gui.main", …)``
(a runtime string-based import), PyInstaller does **not** bundle the
swcstudio package — exactly what we want. To make it still bundle the
heavy library dependencies (numpy, torch, PySide6, vispy, etc.), the
modular spec lists those explicitly under ``hiddenimports``.
"""
from __future__ import annotations

import multiprocessing
import os
import sys
from pathlib import Path
from typing import Optional


# -----------------------------------------------------------------------------
# Multiprocessing fix — must run before anything else imports.
# -----------------------------------------------------------------------------

multiprocessing.freeze_support()
try:
    multiprocessing.set_start_method("spawn", force=True)
except RuntimeError:
    pass


# -----------------------------------------------------------------------------
# Locate the swcstudio code directory
# -----------------------------------------------------------------------------

def _user_app_override_dir() -> Path:
    """User override location — the auto-updater downloads here."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "SWC-Studio" / "app"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SWC-Studio" / "app"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "swcstudio" / "app"


def _bundled_app_dir() -> Optional[Path]:
    """The bundled app/ dir inside the PyInstaller .app, if any."""
    # PyInstaller exposes _MEIPASS only when running frozen.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidate = Path(meipass) / "app"
        if (candidate / "swcstudio" / "__init__.py").exists():
            return candidate
    return None


def _source_repo_dir() -> Optional[Path]:
    """Source repo when running ``python swcstudio_bootstrap.py`` directly."""
    here = Path(__file__).resolve().parent
    if (here / "swcstudio" / "__init__.py").exists():
        return here
    return None


def _find_app_dir() -> Optional[Path]:
    """Return the directory that *contains* ``swcstudio/`` (i.e. its parent).

    Search order:
        1. User override (auto-updater target)
        2. Bundled in the .app
        3. Source repo (dev mode)
    """
    override = _user_app_override_dir()
    if (override / "swcstudio" / "__init__.py").exists():
        return override

    bundled = _bundled_app_dir()
    if bundled is not None:
        return bundled

    repo = _source_repo_dir()
    if repo is not None:
        return repo

    return None


# -----------------------------------------------------------------------------
# Entry
# -----------------------------------------------------------------------------

def main() -> int:
    app_dir = _find_app_dir()
    if app_dir is None:
        sys.stderr.write(
            "ERROR: cannot locate the swcstudio code package.\n"
            "Searched:\n"
            f"  - user override: {_user_app_override_dir() / 'swcstudio'}\n"
            f"  - bundled:       {(_bundled_app_dir() / 'swcstudio') if _bundled_app_dir() else '(not present)'}\n"
            f"  - source repo:   {(_source_repo_dir() / 'swcstudio') if _source_repo_dir() else '(not running from source)'}\n"
        )
        return 1

    # Insert at the front so the override beats any system-installed swcstudio.
    sys.path.insert(0, str(app_dir))

    # Lazy / runtime import — PyInstaller's static analyzer cannot follow
    # ``__import__`` with a string argument, so swcstudio is *not* baked into
    # the PyInstaller bundle. The heavy deps (numpy, torch, PySide6, …) are
    # still bundled because the modular spec lists them as hiddenimports.
    main_mod = __import__("swcstudio.gui.main", fromlist=["main"])
    main_mod.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
