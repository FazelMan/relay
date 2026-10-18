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


    def test_uninstall_rejects_manifest_traversal(self) -> None:
        dest = self.base / "unsafe"
        dest.mkdir()
        outside = self.base / "outside.txt"
        outside.write_text("keep\n", encoding="utf-8")
        (dest / MANIFEST_NAME).write_text(
            json.dumps({"files": ["../outside.txt", "SKILL.md", MANIFEST_NAME]}),
            encoding="utf-8",
        )
        result = uninstall_adapter(dest)
        self.assertFalse(result["ok"])
        self.assertTrue(outside.is_file())
        self.assertIn("unsafe manifest path rejected: '../outside.txt'", result["errors"])

    def test_uninstall_rejects_absolute_manifest_path(self) -> None:
        dest = self.base / "unsafe-absolute"
        dest.mkdir()
        outside = self.base / "outside-absolute.txt"
        outside.write_text("keep\n", encoding="utf-8")
        (dest / MANIFEST_NAME).write_text(
            json.dumps({"files": [str(outside), MANIFEST_NAME]}),
            encoding="utf-8",
        )
        result = uninstall_adapter(dest)
        self.assertFalse(result["ok"])
        self.assertTrue(outside.is_file())

    def test_uninstall_does_not_follow_symlink(self) -> None:
        dest = self.base / "symlink-dest"
        dest.mkdir()
        outside = self.base / "outside-target.txt"
        outside.write_text("keep\n", encoding="utf-8")
        link = dest / "SKILL.md"
        link.symlink_to(outside)
        (dest / MANIFEST_NAME).write_text(
            json.dumps({"files": ["SKILL.md", MANIFEST_NAME]}),
            encoding="utf-8",
        )
        result = uninstall_adapter(dest)
        self.assertTrue(result["ok"])
        self.assertFalse(link.exists())
        self.assertTrue(outside.is_file())

    def test_install_refuses_symlink_destination(self) -> None:
        real_dest = self.base / "real"
        real_dest.mkdir()
        dest_link = self.base / "linked"
        dest_link.symlink_to(real_dest, target_is_directory=True)
        result = install_adapter(
            dest=dest_link,
            skill_root=self.skill,
            repo_root=self.repo,
            adapter_skill=self.adapter,
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("symlinked install destination" in e for e in result.errors))
        self.assertFalse((real_dest / "SKILL.md").exists())

    def test_install_refuses_symlinked_owned_file(self) -> None:
        dest = self.base / "linked-file"
        dest.mkdir()
        outside = self.base / "outside-owned.txt"
        outside.write_text("keep\n", encoding="utf-8")
        (dest / "SKILL.md").symlink_to(outside)
        result = install_adapter(
            dest=dest,
            skill_root=self.skill,
            repo_root=self.repo,
            adapter_skill=self.adapter,
        )
        self.assertFalse(result.ok)
        self.assertEqual(outside.read_text(encoding="utf-8"), "keep\n")

if __name__ == "__main__":
    unittest.main()
