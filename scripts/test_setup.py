"""Tests for the repository bootstrap script."""

from __future__ import annotations

import unittest
from unittest import mock

import setup


class SetupTests(unittest.TestCase):
    def test_inspection_reports_the_current_checkout(self):
        report = setup.inspect_environment()
        self.assertTrue(report["python_supported"])
        self.assertTrue(report["required_files_present"])
        self.assertEqual(report["missing_files"], [])

    def test_readiness_errors_identify_each_unsatisfied_prerequisite(self):
        errors = setup.readiness_errors({
            "python_supported": False,
            "required_files_present": False,
            "missing_files": ["uv.lock"],
            "uv_path": None,
        })
        self.assertEqual(len(errors), 3)
        self.assertIn("Python 3.11", errors[0])
        self.assertIn("uv.lock", errors[1])
        self.assertIn("uv was not found", errors[2])

    def test_sync_and_verify_use_fixed_argument_lists(self):
        report = {
            "project_root": "test-root",
            "python_version": "3.11.0",
            "python_supported": True,
            "uv_path": "uv",
            "required_files_present": True,
            "missing_files": [],
        }
        with mock.patch("setup.inspect_environment", return_value=report), mock.patch("setup.run_uv") as run:
            self.assertEqual(setup.main(["--sync", "--verify"]), 0)
        self.assertEqual(
            run.call_args_list,
            [
                mock.call("uv", ["sync", "--locked"]),
                mock.call("uv", ["run", "--locked", "python", "-m", "unittest", "discover", "-s", "scripts", "-p", "test_*.py", "-v"]),
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
