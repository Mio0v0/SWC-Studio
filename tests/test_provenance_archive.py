from __future__ import annotations

import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from swcstudio.core.provenance import (
    OpKind,
    archive_path_for,
    current_swc_path_for,
    history_dir_for,
    iter_events,
    open_history_for_read,
    parse_prov_header,
    tracked_op,
)


BASE_SWC = b"# test\n1 1 0 0 0 1 -1\n2 3 1 0 0 0.5 1\n"
TYPE_EDIT = b"# test\n1 1 0 0 0 1 -1\n2 2 1 0 0 0.5 1\n"
RADIUS_EDIT = b"# test\n1 1 0 0 0 1 -1\n2 2 1 0 0 0.8 1\n"


class ProvenanceArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory(prefix="swcstudio-provenance-")
        self.tmp = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _make_swc(self, name: str = "cell.swc") -> Path:
        path = self.tmp / name
        path.write_bytes(BASE_SWC)
        return path

    def test_tracked_op_writes_visible_archive_and_header_pointer(self) -> None:
        swc = self._make_swc()
        with tracked_op(
            swc,
            kind=OpKind.SET_TYPE,
            params={"node_id": 2, "new_type": 2},
            message="type edit",
        ) as op:
            op.set_output(TYPE_EDIT)

        archive = archive_path_for(swc)
        self.assertTrue(archive.exists())
        self.assertFalse(history_dir_for(swc).exists())
        self.assertEqual(archive.name, "cell_history.swcstudio")

        with zipfile.ZipFile(archive, "r") as zf:
            infos = zf.infolist()
            self.assertTrue(any((info.flag_bits & 0x1) or info.compress_type == 99 for info in infos))
            member = next(info.filename for info in infos if info.filename.endswith("events.jsonl"))
            with self.assertRaises(Exception):
                zf.read(member)

        current = current_swc_path_for(swc)
        header = parse_prov_header(current.read_bytes())
        self.assertEqual(header.root["repo"], archive.name)
        self.assertEqual(header.tip["sidecar"], archive.name)
        self.assertTrue(header.tip.get("repo_id"))

        with open_history_for_read(swc, history_dir_for(swc)) as hist:
            events = list(iter_events(hist / "events.jsonl"))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].message, "type edit")
        self.assertFalse(history_dir_for(swc).exists())

    def test_archive_follows_renamed_swc_with_matching_repo_id(self) -> None:
        swc = self._make_swc()
        with tracked_op(swc, kind=OpKind.SET_TYPE, params={}, message="first") as op:
            op.set_output(TYPE_EDIT)

        renamed = self.tmp / "renamed.swc"
        shutil.copy2(current_swc_path_for(swc), renamed)
        with tracked_op(renamed, kind=OpKind.SET_RADIUS, params={}, message="renamed") as op:
            op.set_output(RADIUS_EDIT)

        self.assertFalse(archive_path_for(swc).exists())
        self.assertTrue(archive_path_for(renamed).exists())
        self.assertFalse(history_dir_for(renamed).exists())
        with open_history_for_read(renamed, history_dir_for(renamed)) as hist:
            messages = [event.message for event in iter_events(hist / "events.jsonl")]
        self.assertEqual(messages, ["first", "renamed"])

    def test_encrypted_archive_round_trips_when_password_is_set(self) -> None:
        try:
            import pyzipper  # noqa: F401
        except Exception:
            self.skipTest("pyzipper is not installed")

        old = os.environ.get("SWCSTUDIO_HISTORY_PASSWORD")
        os.environ["SWCSTUDIO_HISTORY_PASSWORD"] = "test-password"
        try:
            swc = self._make_swc()
            with tracked_op(swc, kind=OpKind.SET_TYPE, params={}, message="encrypted") as op:
                op.set_output(TYPE_EDIT)

            self.assertTrue(archive_path_for(swc).exists())
            self.assertFalse(history_dir_for(swc).exists())
            with open_history_for_read(swc, history_dir_for(swc)) as hist:
                events = list(iter_events(hist / "events.jsonl"))
            self.assertEqual([event.message for event in events], ["encrypted"])
            self.assertFalse(history_dir_for(swc).exists())
        finally:
            if old is None:
                os.environ.pop("SWCSTUDIO_HISTORY_PASSWORD", None)
            else:
                os.environ["SWCSTUDIO_HISTORY_PASSWORD"] = old


if __name__ == "__main__":
    unittest.main()
