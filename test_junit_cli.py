import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from junit_cli import main


class JUnitCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.reports = self.root / "reports"
        self.reports.mkdir()
        self.manifest = self.root / "manifest.json"
        self.expected = {"unit": ["a", "b"], "integration": ["c"]}
        self.identities = {
            "unit": [{"id": "a", "classname": "Unit", "name": "first"},
                     {"id": "b", "classname": "Unit", "name": "second"}],
            "integration": [{"id": "c", "classname": "Integration", "name": "third"}],
        }
        self.candidate = "a" * 40
        self.environment = "b" * 64
        (self.reports / "unit.xml").write_text(
            '<testsuite tests="2"><testcase classname="Unit" name="first"/>'
            '<testcase classname="Unit" name="second"/></testsuite>', encoding="utf-8")
        (self.reports / "integration.xml").write_text(
            '<testsuite tests="1"><testcase classname="Integration" name="third"/></testsuite>',
            encoding="utf-8")
        self.write_manifest()

    def write_manifest(self, **overrides):
        data = {"candidate": self.candidate, "environment": self.environment,
                "expected": self.expected, "identities": self.identities,
                "reports": {"unit": "reports/unit.xml", "integration": "reports/integration.xml"}}
        data.update(overrides)
        self.manifest.write_text(json.dumps(data), encoding="utf-8")

    def invoke(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--manifest", str(self.manifest)])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_all_local_shards_pass(self):
        code, stdout, stderr = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertTrue(json.loads(stdout)["ok"])
        self.assertEqual(json.loads(stdout)["observed"], 3)

    def test_failed_case_returns_nonzero(self):
        (self.reports / "unit.xml").write_text(
            '<testsuite><testcase classname="Unit" name="first"><failure/></testcase>'
            '<testcase classname="Unit" name="second"/></testsuite>', encoding="utf-8")
        code, stdout, _ = self.invoke()
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(stdout)["ok"])

    def test_missing_case_is_not_green(self):
        (self.reports / "unit.xml").write_text(
            '<testsuite><testcase classname="Unit" name="first"/></testsuite>', encoding="utf-8")
        code, stdout, _ = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(stdout)["missing_cases"], ["b"])

    def test_missing_report_is_blocked(self):
        self.write_manifest(reports={"unit": "reports/missing.xml",
                                     "integration": "reports/integration.xml"})
        code, stdout, stderr = self.invoke()
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("BLOCKED", stderr)

    def test_incomplete_shard_maps_are_blocked(self):
        self.write_manifest(identities={"unit": self.identities["unit"]})
        code, _, stderr = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn("exactly", stderr)

    def test_oversized_report_is_blocked(self):
        from junit_report import MAX_XML_BYTES
        (self.reports / "unit.xml").write_bytes(b"x" * (MAX_XML_BYTES + 1))
        code, _, stderr = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn("size limit", stderr)


if __name__ == "__main__":
    unittest.main()
