"""Convenience launcher for the SWC-Studio Qt GUI.
Run from repo root with the project's venv active:

  source .venv/bin/activate
  python run_gui.py

This simply forwards to the package entry at swcstudio.gui.main
"""

# IMPORTANT: multiprocessing.freeze_support() must be called as the very
# first thing in the frozen entrypoint. When the bundled app spawns a
# worker (sklearn n_jobs, joblib, torch dataloaders, etc.), Python on
# macOS re-launches the *entire bundled executable* as the worker.
# Without freeze_support() the child process re-runs main() and the
# user sees a duplicate GUI window pop up when they open a file. With
# it, the child detects it's a worker and runs the worker function
# instead. No-op on non-frozen Python.
import multiprocessing
multiprocessing.freeze_support()
# Force 'spawn' start method (default on macOS Python 3.8+ but explicit
# is safer; 'fork' is unsafe with Qt / threaded libraries).
try:
    multiprocessing.set_start_method("spawn", force=True)
except RuntimeError:
    # Already set elsewhere — fine.
    pass

import os
import sys

# Make the GUI package's directory importable by bare module names (the GUI
# package uses a mix of package-relative and plain imports). This ensures
# running `python run_gui.py` from the repo root works the same as running
# from inside the GUI folder.
HERE = os.path.dirname(os.path.abspath(__file__))
GUI_DIR = os.path.join(HERE, "swcstudio", "gui")
if GUI_DIR not in sys.path:
  sys.path.insert(0, GUI_DIR)

from swcstudio.gui import main as _m

if __name__ == "__main__":
  _m.main()
