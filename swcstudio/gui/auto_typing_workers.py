"""QThread-friendly workers for the auto-typing engine.

The auto-typing engine is CPU-bound (sklearn predict + GraphSAGE
forward pass) and can take seconds to minutes per file. Running it on
the GUI thread would freeze the window. These QObject workers wrap
the engine calls so the panels can run them on a ``QThread`` and stay
responsive.

Two workers are provided:

* ``_AutoLabelFileWorker`` — single-file path used by the Validation
  Auto Label panel. Wraps the temp-file write + ``run_file`` call.
* ``_AutoLabelBatchWorker`` — folder path used by the Batch Processing
  Auto Label panel. Drives a per-file progress callback so the panel's
  progress bar can update.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal, Slot


class _AutoLabelFileWorker(QObject):
    """Run auto-typing on one SWC file.

    Emits ``finished(run_id, result_obj)`` on success or
    ``failed(run_id, error_message)`` on any exception.
    """

    finished = Signal(int, object)
    failed = Signal(int, str)

    def __init__(
        self,
        run_id: int,
        file_path: str,
        options: object,
        config_overrides: dict[str, Any] | None,
    ):
        super().__init__()
        self._run_id = int(run_id)
        self._file_path = str(file_path)
        self._options = options
        self._config_overrides = dict(config_overrides) if config_overrides else None

    @Slot()
    def run(self) -> None:  # noqa: D401 - Qt slot
        from swcstudio.tools.validation.features.auto_typing import (  # noqa: PLC0415
            run_file as run_validation_auto_typing_file,
        )
        try:
            result = run_validation_auto_typing_file(
                self._file_path,
                options=self._options,
                config_overrides=self._config_overrides,
                write_output=False,
                write_log=False,
            )
            self.finished.emit(self._run_id, result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(self._run_id, str(exc))


class _AutoLabelBatchWorker(QObject):
    """Run auto-typing on every SWC in a folder.

    Emits ``progress(current_index, total, current_filename)`` once
    per file *before* that file is processed, then either
    ``finished(run_id, batch_result)`` or ``failed(run_id, message)``.
    """

    progress = Signal(int, int, str)
    finished = Signal(int, object)
    failed = Signal(int, str)

    def __init__(
        self,
        run_id: int,
        folder: str,
        options: object,
        config_overrides: dict[str, Any] | None,
    ):
        super().__init__()
        self._run_id = int(run_id)
        self._folder = str(folder)
        self._options = options
        self._config_overrides = dict(config_overrides) if config_overrides else None

    @Slot()
    def run(self) -> None:  # noqa: D401 - Qt slot
        from swcstudio.tools.batch_processing.features.auto_typing import (  # noqa: PLC0415
            run_folder as run_auto_typing,
        )

        def _emit_progress(idx: int, total: int, name: str) -> None:
            self.progress.emit(int(idx), int(total), str(name))

        try:
            result = run_auto_typing(
                self._folder,
                options=self._options,
                config_overrides=self._config_overrides,
                progress_callback=_emit_progress,
            )
            self.finished.emit(self._run_id, result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(self._run_id, str(exc))


__all__ = ["_AutoLabelFileWorker", "_AutoLabelBatchWorker"]
