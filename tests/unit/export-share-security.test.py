#!/usr/bin/env python3
"""Security regression tests for export_share.py."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "skills/cancer-buddy-organize/scripts/export_share.py"
SPEC = importlib.util.spec_from_file_location("export_share", MODULE_PATH)
assert SPEC and SPEC.loader
EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORT)


class ExportShareSecurityTests(unittest.TestCase):
    def test_rejects_destination_inside_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            patient = Path(temp) / "PT-test"
            patient.mkdir()
            dest = patient / "share"
            with mock.patch.object(EXPORT, "_run_acceptance_gate", return_value=True):
                self.assertEqual(EXPORT.export_share(patient, dest), 2)
            self.assertFalse(dest.exists())

    def test_rejects_symlink_without_copying_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            patient = root / "PT-test"
            patient.mkdir()
            secret = root / "outside-secret.txt"
            secret.write_text("must never ship", encoding="utf-8")
            (patient / "external-link").symlink_to(secret)
            dest = root / "share"
            with mock.patch.object(EXPORT, "_run_acceptance_gate", return_value=True):
                self.assertEqual(EXPORT.export_share(patient, dest), 1)
            self.assertFalse(dest.exists())

    def test_regular_tree_still_exports(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            patient = root / "PT-test"
            patient.mkdir()
            (patient / "profile.json").write_text("{}", encoding="utf-8")
            raw = patient / "raw"
            raw.mkdir()
            (raw / "identity.txt").write_text("private", encoding="utf-8")
            dest = root / "share"
            with mock.patch.object(EXPORT, "_run_acceptance_gate", return_value=True):
                self.assertEqual(EXPORT.export_share(patient, dest), 0)
            self.assertTrue((dest / "profile.json").is_file())
            self.assertFalse((dest / "raw").exists())


if __name__ == "__main__":
    unittest.main()
