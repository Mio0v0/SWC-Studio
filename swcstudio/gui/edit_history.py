"""Bounded, delta-based in-memory Undo/Redo history for SWC dataframes."""

from __future__ import annotations

import copy
import os
import pickle
import zlib
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_UNDO_LIMIT = max(1, int(os.environ.get("SWCSTUDIO_UNDO_LIMIT", "20")))


def _copy_attrs(df: pd.DataFrame) -> dict[str, Any]:
    try:
        return copy.deepcopy(dict(getattr(df, "attrs", {}) or {}))
    except Exception:
        return dict(getattr(df, "attrs", {}) or {})


def _attrs_equal(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    try:
        return pickle.dumps(dict(left.attrs), protocol=5) == pickle.dumps(
            dict(right.attrs),
            protocol=5,
        )
    except Exception:
        return dict(left.attrs) == dict(right.attrs)


@dataclass
class _CompressedFramePair:
    before: bytes
    after: bytes

    @classmethod
    def build(
        cls,
        before: pd.DataFrame,
        after: pd.DataFrame,
    ) -> "_CompressedFramePair":
        return cls(
            before=zlib.compress(pickle.dumps(before, protocol=5), level=1),
            after=zlib.compress(pickle.dumps(after, protocol=5), level=1),
        )

    def restore(self, *, forward: bool) -> pd.DataFrame:
        payload = self.after if forward else self.before
        return pickle.loads(zlib.decompress(payload))


@dataclass
class DataFrameDelta:
    """Changed rows plus optional row ordering for one Undo step."""

    columns: tuple[str, ...]
    before_rows: pd.DataFrame | None
    after_rows: pd.DataFrame | None
    before_order: np.ndarray | None
    after_order: np.ndarray | None
    before_attrs: dict[str, Any]
    after_attrs: dict[str, Any]
    compressed: _CompressedFramePair | None = None

    @classmethod
    def build(
        cls,
        before: pd.DataFrame,
        after: pd.DataFrame,
    ) -> "DataFrameDelta | None":
        if before.equals(after) and _attrs_equal(before, after):
            return None

        columns = tuple(str(column) for column in before.columns)
        safe_row_delta = (
            columns == tuple(str(column) for column in after.columns)
            and "id" in before.columns
            and "id" in after.columns
            and bool(before["id"].is_unique)
            and bool(after["id"].is_unique)
        )
        if not safe_row_delta:
            return cls(
                columns=columns,
                before_rows=None,
                after_rows=None,
                before_order=None,
                after_order=None,
                before_attrs={},
                after_attrs={},
                compressed=_CompressedFramePair.build(before, after),
            )

        try:
            before_indexed = before.set_index("id", drop=False)
            after_indexed = after.set_index("id", drop=False)
            common = before_indexed.index.intersection(
                after_indexed.index,
                sort=False,
            )
            changed_common: list[Any] = []
            if len(common):
                before_common = before_indexed.loc[common, list(columns)]
                after_common = after_indexed.loc[common, list(columns)]
                before_hash = pd.util.hash_pandas_object(
                    before_common,
                    index=False,
                ).to_numpy()
                after_hash = pd.util.hash_pandas_object(
                    after_common,
                    index=False,
                ).to_numpy()
                changed_common = common[before_hash != after_hash].tolist()

            before_only = before_indexed.index.difference(
                after_indexed.index,
                sort=False,
            ).tolist()
            after_only = after_indexed.index.difference(
                before_indexed.index,
                sort=False,
            ).tolist()
            before_changed_ids = [*changed_common, *before_only]
            after_changed_ids = [*changed_common, *after_only]

            before_rows = (
                before_indexed.loc[before_changed_ids, list(columns)]
                .reset_index(drop=True)
                .copy()
                if before_changed_ids
                else before.iloc[0:0].copy()
            )
            after_rows = (
                after_indexed.loc[after_changed_ids, list(columns)]
                .reset_index(drop=True)
                .copy()
                if after_changed_ids
                else after.iloc[0:0].copy()
            )

            before_ids = before["id"].to_numpy(copy=False)
            after_ids = after["id"].to_numpy(copy=False)
            order_changed = not np.array_equal(before_ids, after_ids)
            return cls(
                columns=columns,
                before_rows=before_rows,
                after_rows=after_rows,
                before_order=before_ids.copy() if order_changed else None,
                after_order=after_ids.copy() if order_changed else None,
                before_attrs=_copy_attrs(before),
                after_attrs=_copy_attrs(after),
            )
        except Exception:
            return cls(
                columns=columns,
                before_rows=None,
                after_rows=None,
                before_order=None,
                after_order=None,
                before_attrs={},
                after_attrs={},
                compressed=_CompressedFramePair.build(before, after),
            )

    @property
    def changed_row_count(self) -> int:
        if self.compressed is not None:
            return -1
        return max(
            len(self.before_rows) if self.before_rows is not None else 0,
            len(self.after_rows) if self.after_rows is not None else 0,
        )

    def apply(self, current: pd.DataFrame, *, forward: bool) -> pd.DataFrame:
        if self.compressed is not None:
            return self.compressed.restore(forward=forward)

        target_rows = self.after_rows if forward else self.before_rows
        source_rows = self.before_rows if forward else self.after_rows
        target_order = self.after_order if forward else self.before_order
        target_attrs = self.after_attrs if forward else self.before_attrs
        assert target_rows is not None
        assert source_rows is not None

        out = current.loc[:, list(self.columns)].copy()
        out_indexed = out.set_index("id", drop=False)
        target_indexed = target_rows.set_index("id", drop=False)
        source_ids = set(source_rows["id"].tolist())
        target_ids = set(target_rows["id"].tolist())

        remove_ids = list(source_ids - target_ids)
        if remove_ids:
            out_indexed = out_indexed.drop(index=remove_ids, errors="ignore")

        common_ids = target_indexed.index.intersection(
            out_indexed.index,
            sort=False,
        )
        if len(common_ids):
            out_indexed.loc[common_ids, list(self.columns)] = target_indexed.loc[
                common_ids,
                list(self.columns),
            ].to_numpy()

        new_ids = target_indexed.index.difference(
            out_indexed.index,
            sort=False,
        )
        if len(new_ids):
            out_indexed = pd.concat(
                [
                    out_indexed,
                    target_indexed.loc[new_ids, list(self.columns)],
                ],
                axis=0,
            )

        if target_order is not None:
            out_indexed = out_indexed.reindex(target_order.tolist())

        restored = out_indexed.loc[:, list(self.columns)].reset_index(drop=True)
        restored.attrs.update(copy.deepcopy(target_attrs))
        return restored


class DataFrameUndoHistory:
    """At most ``limit`` reversible dataframe deltas."""

    def __init__(self, limit: int = DEFAULT_UNDO_LIMIT) -> None:
        self.limit = max(1, int(limit))
        self._deltas: list[DataFrameDelta] = []
        self._index = 0

    @property
    def can_undo(self) -> bool:
        return self._index > 0

    @property
    def can_redo(self) -> bool:
        return self._index < len(self._deltas)

    @property
    def step_count(self) -> int:
        return len(self._deltas)

    @property
    def current_index(self) -> int:
        return self._index

    def reset(self) -> None:
        self._deltas.clear()
        self._index = 0

    def push(self, before: pd.DataFrame, after: pd.DataFrame) -> bool:
        delta = DataFrameDelta.build(before, after)
        if delta is None:
            return False
        if self._index < len(self._deltas):
            self._deltas = self._deltas[: self._index]
        self._deltas.append(delta)
        self._index += 1
        if len(self._deltas) > self.limit:
            overflow = len(self._deltas) - self.limit
            del self._deltas[:overflow]
            self._index = max(0, self._index - overflow)
        return True

    def undo(self, current: pd.DataFrame) -> pd.DataFrame | None:
        if not self.can_undo:
            return None
        delta = self._deltas[self._index - 1]
        restored = delta.apply(current, forward=False)
        self._index -= 1
        return restored

    def redo(self, current: pd.DataFrame) -> pd.DataFrame | None:
        if not self.can_redo:
            return None
        delta = self._deltas[self._index]
        restored = delta.apply(current, forward=True)
        self._index += 1
        return restored


__all__ = [
    "DEFAULT_UNDO_LIMIT",
    "DataFrameDelta",
    "DataFrameUndoHistory",
]
