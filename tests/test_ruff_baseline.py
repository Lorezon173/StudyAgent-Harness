"""Contract tests for the standalone Ruff evidence collector (standard library only)."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ruff_baseline.py"


class RuffBaselineTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("ruff_baseline", SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
        (self.root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
        for command in (["git", "init", "--quiet"],
                        ["git", "add", "pyproject.toml", "uv.lock"],
                        ["git", "-c", "user.name=Baseline Test", "-c", "user.email=baseline@example.invalid",
                         "commit", "--quiet", "-m", "test fixture"]):
            subprocess.run(command, cwd=self.root, capture_output=True, check=True)

    def fake_ruff(self, code, raw):
        fake = self.root / "fake.py"
        fake.write_text(
            "import sys\n"
            "if '--version' in sys.argv: print('ruff 0.17.1')\n"
            "elif '--show-settings' in sys.argv: print('settings')\n"
            "elif '--show-files' in sys.argv: print('sample.py')\n"
            f"else: print({raw!r}); print('raw stderr', file=sys.stderr); sys.exit({code})\n",
            encoding="utf-8",
        )
        return [sys.executable, str(fake)]

    def test_normalization_preserves_fix_and_rejects_outside_paths(self):
        diagnostic = {"filename": str(self.root / "sample.py"), "code": "F401",
                      "location": {"row": 1, "column": 2}, "end_location": {"row": 1, "column": 4},
                      "message": "unused", "fix": {"applicability": "safe", "edits": []}}
        result = self.module.normalize_diagnostics(json.dumps([diagnostic]), self.root)
        self.assertEqual(result[0]["filename"], "sample.py")
        self.assertEqual(result[0]["fix"], {"applicability": "safe", "edits": []})
        diagnostic["filename"] = str(self.root.parent / "outside.py")
        with self.assertRaises(ValueError):
            self.module.normalize_diagnostics(json.dumps([diagnostic]), self.root)

    def test_exit_one_keeps_diagnostics_and_raw_stderr(self):
        raw = json.dumps([{"filename": "sample.py", "code": "F401", "location": {"row": 1, "column": 1}, "message": "unused"}])
        out = self.root / "artifacts" / "ruff" / "first"
        self.assertEqual(self.module.collect(self.root, out, self.fake_ruff(1, raw)), 1)
        manifest = json.loads((out / "manifest.json").read_text())
        self.assertEqual(manifest["ruff_exit_code"], 1)
        self.assertEqual(manifest["diagnostic_count"], 1)
        self.assertIn("raw stderr", (out / "diagnostics.stderr.txt").read_text())
        with self.assertRaises(FileExistsError):
            self.module.collect(self.root, out, self.fake_ruff(1, raw))

    def test_exit_two_and_bad_json_are_errors_not_empty_success(self):
        for code, raw in [(2, "invalid configuration"), (0, "not json")]:
            with self.subTest(code=code):
                out = self.root / f"run-{code}"
                self.assertEqual(self.module.collect(self.root, out, self.fake_ruff(code, raw)), 2)
                manifest = json.loads((out / "manifest.json").read_text())
                self.assertEqual(manifest["status"], "error")
                self.assertIsNone(manifest["diagnostic_count"])
                self.assertEqual((out / "diagnostics.raw.json").read_text().strip(), raw)
                self.assertFalse((out / "diagnostics.json").exists())

    def test_clean_result_and_invalid_shape(self):
        out = self.root / "clean"
        self.assertEqual(self.module.collect(self.root, out, self.fake_ruff(0, "[]")), 0)
        self.assertEqual(json.loads((out / "manifest.json").read_text())["execution_mode"], "direct-tool")
        self.assertEqual(json.loads((out / "files.json").read_text()), ["sample.py"])
        self.assertEqual(json.loads((out / "diagnostics.json").read_text()), [])
        with self.assertRaises(ValueError):
            self.module.normalize_diagnostics('{"error": "not an array"}', self.root)

    def test_environment_failures_preserve_raw_evidence_and_never_report_clean(self):
        commands = [
            ("source_commit", ["git", "rev-parse", "HEAD"]),
            ("working_tree", ["git", "status", "--porcelain=v1", "--untracked-files=all"]),
            ("diff", ["git", "diff", "--binary", "HEAD"]),
            ("untracked", ["git", "ls-files", "--others", "--exclude-standard", "-z"]),
            ("uv_version", ["uv", "--version"]),
        ]
        original = self.module.run_ruff
        for name, failed_command in commands:
            with self.subTest(command=name):
                def fail_environment(command, root, failed_command=failed_command):
                    if command == failed_command:
                        return subprocess.CompletedProcess(command, 73, b"partial stdout", b"environment failed")
                    return original(command, root)

                out = self.root / ("failure-" + name)
                with patch.object(self.module, "run_ruff", side_effect=fail_environment):
                    code = self.module.collect(self.root, out, self.fake_ruff(0, "[]"))
                self.assertEqual(code, 2)
                manifest = json.loads((out / "manifest.json").read_text())
                self.assertEqual(manifest["status"], "error")
                self.assertIn(name, manifest["error"])
                self.assertEqual(manifest[name + "_exit_code"], 73)
                self.assertEqual(manifest["commands"][name], failed_command)
                self.assertEqual((out / (name + ".raw.txt")).read_bytes(), b"partial stdout")
                self.assertEqual((out / (name + ".stderr.txt")).read_bytes(), b"environment failed")
                self.assertIsNone(manifest["ruff_exit_code"])
                if name in {"source_commit", "working_tree", "diff"}:
                    self.assertIsNone(manifest["dirty"])

    def test_output_creation_failure_propagates(self):
        parent = self.root / "blocked"
        parent.write_text("file", encoding="utf-8")
        with self.assertRaises(OSError):
            self.module.collect(self.root, parent / "run", self.fake_ruff(0, "[]"))


if __name__ == "__main__":
    unittest.main()
