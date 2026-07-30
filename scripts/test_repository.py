"""Tests for durable JSON repository writes."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import research_repository  # noqa: E402


class JsonResearchRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rt-repository-"))
        self.env = mock.patch.dict(os.environ, {"RESEARCH_WORKSPACE": str(self.tmp)})
        self.env.start()
        self.repository = research_repository.JsonResearchRepository()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_data_uses_same_directory_atomic_replace(self):
        self.repository.save_data({"version": 1})
        target = research_repository.state_path()
        with mock.patch.object(research_repository.os, "replace", wraps=os.replace) as replace:
            self.repository.save_data({"version": 2})
        source, destination = replace.call_args.args
        self.assertEqual(Path(destination), target)
        self.assertEqual(Path(source).parent, target.parent)
        self.assertFalse(Path(source).exists())
        self.assertEqual(self.repository.load_data(), {"version": 2})

    def test_failed_replace_preserves_previous_json_and_cleans_tempfile(self):
        previous = {"version": 1}
        self.repository.save_data(previous)
        with mock.patch.object(research_repository.os, "replace", side_effect=OSError("replace failed")):
            with self.assertRaisesRegex(OSError, "replace failed"):
                self.repository.save_data({"version": 2})
        self.assertEqual(self.repository.load_data(), previous)
        self.assertEqual(list(research_repository.drift_dir().glob(".research_state.json.*.tmp")), [])

    def test_snapshot_state_and_manifest_are_atomically_written(self):
        data = {"evidence": {}, "cognitions": {}, "frames": {}}
        with mock.patch.object(research_repository.os, "replace", wraps=os.replace) as replace:
            manifest = self.repository.write_snapshot("unit", data, "2026-07-29T00:00:00+00:00")
        destinations = {Path(call.args[1]).name for call in replace.call_args_list}
        self.assertEqual(destinations, {"research_state.json", "manifest.json"})
        snapshot = self.tmp / "research_snapshots" / "unit"
        self.assertEqual(manifest["snapshot_id"], "unit")
        self.assertTrue((snapshot / "research_state.json").is_file())
        self.assertTrue((snapshot / "manifest.json").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
