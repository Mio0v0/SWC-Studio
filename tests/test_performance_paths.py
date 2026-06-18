from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from swcstudio.core.model_paths import resolve_model_path
from swcstudio.gui.edit_history import DataFrameDelta, DataFrameUndoHistory


def _frame(count: int = 100) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "id": list(range(1, count + 1)),
            "type": [3] * count,
            "x": [float(value) for value in range(count)],
            "y": [0.0] * count,
            "z": [0.0] * count,
            "radius": [0.5] * count,
            "parent": [-1, *range(1, count)],
        }
    )
    df.attrs["header_lines"] = ["# test"]
    return df


class PerformancePathTests(unittest.TestCase):
    def test_row_edit_history_stores_only_changed_rows(self) -> None:
        before = _frame(10_000)
        after = before.copy()
        after.attrs.update(before.attrs)
        after.loc[after["id"] == 5000, "type"] = 4

        delta = DataFrameDelta.build(before, after)

        self.assertIsNotNone(delta)
        self.assertIsNone(delta.compressed)
        self.assertEqual(delta.changed_row_count, 1)
        self.assertTrue(delta.apply(after, forward=False).equals(before))
        self.assertTrue(delta.apply(before, forward=True).equals(after))

    def test_structural_delta_supports_undo_redo_and_history_limit(self) -> None:
        history = DataFrameUndoHistory(limit=3)
        current = _frame(8)
        states = [current.copy()]
        for node_id in (8, 7, 6, 5, 4):
            next_df = current.loc[current["id"] != node_id].reset_index(drop=True)
            history.push(current, next_df)
            current = next_df
            states.append(current.copy())

        self.assertEqual(history.step_count, 3)
        for expected in reversed(states[-4:-1]):
            current = history.undo(current)
            self.assertIsNotNone(current)
            self.assertTrue(current.equals(expected))
        self.assertFalse(history.can_undo)

        for expected in states[-3:]:
            current = history.redo(current)
            self.assertIsNotNone(current)
            self.assertTrue(current.equals(expected))
        self.assertFalse(history.can_redo)

    def test_stage_models_are_loaded_once_per_unchanged_file(self) -> None:
        from swcstudio.core.auto_typing import cell_type_detector, pipeline

        stage1 = resolve_model_path("stage1")
        stage2 = resolve_model_path("stage2")
        self.assertIsNotNone(stage1)
        self.assertIsNotNone(stage2)

        cell_type_detector._CLASSIFIER_CACHE.clear()
        pipeline._STAGE2_BUNDLE_CACHE.clear()
        original_stage1_load = cell_type_detector.pickle.load
        original_stage2_load = pipeline.pickle.load

        with patch.object(
            cell_type_detector.pickle,
            "load",
            wraps=original_stage1_load,
        ) as stage1_load:
            first = cell_type_detector.CellTypeClassifier.load(stage1)
            second = cell_type_detector.CellTypeClassifier.load(stage1)
        self.assertIs(first, second)
        self.assertEqual(stage1_load.call_count, 1)

        with patch.object(
            pipeline.pickle,
            "load",
            wraps=original_stage2_load,
        ) as stage2_load:
            first_bundle = pipeline._load_stage2_bundle(Path(stage2))
            second_bundle = pipeline._load_stage2_bundle(Path(stage2))
        self.assertIs(first_bundle, second_bundle)
        self.assertEqual(stage2_load.call_count, 1)

    def test_non_unique_ids_use_compressed_fallback(self) -> None:
        before = _frame(4)
        after = before.copy()
        after.loc[3, "id"] = 3

        delta = DataFrameDelta.build(before, after)

        self.assertIsNotNone(delta)
        self.assertIsNotNone(delta.compressed)
        self.assertTrue(delta.apply(after, forward=False).equals(before))


if __name__ == "__main__":
    unittest.main()
