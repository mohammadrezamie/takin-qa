import os
from pathlib import Path
import sys
import tempfile
import unittest

from runner import execute

@unittest.skipUnless(os.name == "posix", "POSIX runner")
class RunnerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.logs = self.root / "logs"
        self.logs.mkdir()
        self.dirs = {name: self.root / name for name in ("a", "b")}
        for directory in self.dirs.values():
            directory.mkdir()
        self.expected = {"a": ["first", "second"], "b": ["third"]}
        self.commands = {case: [sys.executable, "-c", "print('synthetic')"]
                         for case in ("first", "second", "third")}

    def run_cases(self, **overrides):
        inputs = dict(expected=self.expected, commands=self.commands,
                      workdirs=self.dirs, candidate="a"*40,
                      environment="b"*64, log_root=self.logs, max_workers=2)
        inputs.update(overrides)
        return execute(**inputs)

    def test_actual_commands_and_private_logs(self):
        result = self.run_cases()
        self.assertTrue(result["summary"]["ok"])
        self.assertEqual(result["summary"]["observed"], 3)
        self.assertEqual(result["scope"], "command-exit-status")
        files = list(Path(result["log_directory"]).glob("*.log"))
        self.assertEqual(len(files), 3)
        self.assertTrue(all(f.read_text().strip() == "synthetic" for f in files))

    def test_failure_does_not_stop_other_cases(self):
        self.commands["first"] = [sys.executable, "-c", "raise SystemExit(7)"]
        result = self.run_cases()
        self.assertFalse(result["summary"]["ok"])
        self.assertEqual(result["summary"]["counts"]["fail"], 1)
        self.assertEqual(result["summary"]["counts"]["pass"], 2)
        self.assertEqual(result["reports"][0]["cases"][0]["returncode"], 7)

    def test_timeout_is_not_green(self):
        self.commands["first"] = [sys.executable, "-c", "import time; time.sleep(10)"]
        result = self.run_cases(timeout_s=1)
        self.assertFalse(result["summary"]["ok"])
        self.assertEqual(result["summary"]["counts"]["timeout"], 1)

    def test_missing_executable_is_blocked(self):
        self.commands["third"] = [str(self.root / "nonexistent")]
        self.assertEqual(self.run_cases()["summary"]["counts"]["blocked"], 1)

    def test_rejects_manifest_mismatch_before_execution(self):
        self.commands.pop("first")
        with self.assertRaises(ValueError):
            self.run_cases()
        self.assertEqual(list(self.logs.iterdir()), [])

    def test_shared_or_nested_workspaces_rejected(self):
        self.dirs["b"] = self.dirs["a"]
        with self.assertRaises(ValueError):
            self.run_cases()
        nested = self.dirs["a"] / "nested"
        nested.mkdir()
        self.dirs["b"] = nested
        with self.assertRaises(ValueError):
            self.run_cases()

    def test_no_implicit_shell(self):
        marker = self.root / "marker"
        self.commands["first"] = [sys.executable, "-c", "import sys; print(sys.argv[1])",
                                  f"; touch {marker}"]
        self.assertTrue(self.run_cases()["summary"]["ok"])
        self.assertFalse(marker.exists())

    def test_invalid_identity_or_bounds(self):
        for bad in ({"candidate": "bad"}, {"max_workers": 0}, {"timeout_s": True}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.run_cases(**bad)
