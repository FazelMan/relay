#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from relay.install_lib import MANIFEST_NAME, install_adapter, uninstall_adapter


class InstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        # Use real skill tree from repo
        self.repo = Path(__file__).resolve().parents[1]
        self.skill = self.repo / "skills" / "handoff"
        self.adapter = self.skill / "adapters" / "claude-code" / "SKILL.md"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_preserves_custom_files_and_is_idempotent(self) -> None:
        dest = self.base / "skills" / "handoff"
        dest.mkdir(parents=True)
        custom = dest / "my-notes.md"
        custom.write_text("keep me\n", encoding="utf-8")

        r1 = install_adapter(
            dest=dest,
            skill_root=self.skill,
            repo_root=self.repo,
            adapter_skill=self.adapter,
        )
        self.assertTrue(r1.ok)
        self.assertTrue((dest / "SKILL.md").is_file())
        self.assertTrue((dest / "bin" / "relay-run").is_file())
        self.assertTrue(custom.is_file())
        self.assertIn("my-notes.md", r1.preserved)

        r2 = install_adapter(
            dest=dest,
            skill_root=self.skill,
            repo_root=self.repo,
            adapter_skill=self.adapter,
        )
        self.assertTrue(r2.ok)
        self.assertTrue(custom.is_file())
        # Second install should mostly skip identical files
        self.assertTrue(len(r2.skipped_same) > 0)

    def test_conflict_backup(self) -> None:
        dest = self.base / "handoff"
        dest.mkdir()
        conflict = dest / "SKILL.md"
        conflict.write_text("user custom skill\n", encoding="utf-8")
        r = install_adapter(
            dest=dest,
            skill_root=self.skill,
            repo_root=self.repo,
            adapter_skill=self.adapter,
        )
        self.assertTrue(r.ok)
        self.assertTrue(any("SKILL.md" in b for b in r.backed_up))
        skill_text = (dest / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Handoff", skill_text)
        backups = list(dest.glob(".relay-backup-*/SKILL.md"))
        self.assertTrue(backups)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "user custom skill\n")

    def test_uninstall_only_owned(self) -> None:
        dest = self.base / "handoff"
        dest.mkdir()
        custom = dest / "keep.txt"
        custom.write_text("x\n", encoding="utf-8")
        install_adapter(
            dest=dest,
            skill_root=self.skill,
            repo_root=self.repo,
            adapter_skill=self.adapter,
        )
        result = uninstall_adapter(dest)
        self.assertTrue(result["ok"])
        self.assertTrue(custom.is_file())
        self.assertFalse((dest / "SKILL.md").exists())
        self.assertFalse((dest / MANIFEST_NAME).exists())

    def test_uninstall_without_manifest_refuses(self) -> None:
        dest = self.base / "orphan"
        dest.mkdir()
        (dest / "SKILL.md").write_text("nope\n", encoding="utf-8")
        result = uninstall_adapter(dest)
        self.assertFalse(result["ok"])
        self.assertTrue((dest / "SKILL.md").is_file())

    def test_path_with_spaces(self) -> None:
        dest = self.base / "my skills" / "handoff"
        r = install_adapter(
            dest=dest,
            skill_root=self.skill,
            repo_root=self.repo,
            adapter_skill=self.adapter,
        )
        self.assertTrue(r.ok)
        wrapper = dest / "bin" / "relay-run"
        self.assertTrue(wrapper.is_file())
        # Wrapper should be executable and reference repo
        text = wrapper.read_text(encoding="utf-8")
        self.assertIn("python3 -m relay", text)


if __name__ == "__main__":
    unittest.main()
