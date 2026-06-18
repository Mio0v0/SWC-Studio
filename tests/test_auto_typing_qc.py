from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from swcstudio.core.auto_typing.qc_input import QCGate


def _write_swc(path: Path, rows: list[str]) -> None:
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _unlabeled_chain(n: int = 12, *, node_type: int = 0) -> list[str]:
    rows: list[str] = []
    for idx in range(1, n + 1):
        parent = -1 if idx == 1 else idx - 1
        rows.append(f"{idx} {node_type} {idx}.0 0.0 0.0 0.5 {parent}")
    return rows


class AutoTypingQCTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory(prefix="swcstudio-qc-tests-")
        self.tmp = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _evaluate_rows(self, rows: list[str]):
        path = self.tmp / "sample.swc"
        _write_swc(path, rows)
        return QCGate().evaluate(path)

    def test_unlabeled_single_root_file_passes_structural_qc(self) -> None:
        result = self._evaluate_rows(_unlabeled_chain())

        self.assertTrue(result.passed, result.reasons)
        self.assertEqual(result.n_soma, 0)
        self.assertEqual(result.n_roots, 1)
        self.assertNotIn("no_soma", result.reasons)
        self.assertNotIn("no_neurites", result.reasons)

    def test_custom_positive_types_do_not_fail_structural_qc(self) -> None:
        result = self._evaluate_rows(_unlabeled_chain(node_type=10))

        self.assertTrue(result.passed, result.reasons)
        self.assertEqual(result.n_other_type, 12)

    def test_multiple_roots_are_rejected(self) -> None:
        rows = _unlabeled_chain()
        rows[5] = "6 0 6.0 0.0 0.0 0.5 -1"

        result = self._evaluate_rows(rows)

        self.assertFalse(result.passed)
        self.assertIn("n_roots=2", result.reasons)

    def test_orphan_parent_is_rejected(self) -> None:
        rows = _unlabeled_chain()
        rows[4] = "5 0 5.0 0.0 0.0 0.5 999"

        result = self._evaluate_rows(rows)

        self.assertFalse(result.passed)
        self.assertIn("n_orphan=1", result.reasons)

    def test_malformed_row_is_rejected(self) -> None:
        rows = _unlabeled_chain()
        rows.append("13 0 13.0 0.0")

        result = self._evaluate_rows(rows)

        self.assertFalse(result.passed)
        self.assertIn("malformed_row:13:expected_7_columns", result.reasons)

    def test_duplicate_id_is_rejected(self) -> None:
        rows = _unlabeled_chain()
        rows[2] = "2 0 3.0 0.0 0.0 0.5 1"

        result = self._evaluate_rows(rows)

        self.assertFalse(result.passed)
        self.assertIn("duplicate_id_count=1", result.reasons)

    def test_parent_cycle_counts_only_cycle_members(self) -> None:
        rows = _unlabeled_chain()
        rows[3] = "4 0 4.0 0.0 0.0 0.5 6"
        rows[4] = "5 0 5.0 0.0 0.0 0.5 4"
        rows[5] = "6 0 6.0 0.0 0.0 0.5 5"

        result = self._evaluate_rows(rows)

        self.assertFalse(result.passed)
        self.assertEqual(result.n_cycle, 3)
        self.assertIn("cycle_node_count=3", result.reasons)

    def test_long_chain_cycle_check_is_linear_enough_for_large_swc(self) -> None:
        path = self.tmp / "large-chain.swc"
        _write_swc(path, _unlabeled_chain(50_000))

        started = time.perf_counter()
        result = QCGate().evaluate(path)
        elapsed = time.perf_counter() - started

        self.assertTrue(result.passed, result.reasons)
        self.assertEqual(result.n_cycle, 0)
        self.assertLess(
            elapsed,
            3.0,
            f"50k-node structural QC took {elapsed:.3f}s",
        )


if __name__ == "__main__":
    unittest.main()
