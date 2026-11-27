import unittest
from qa import summarize

class EvidenceTests(unittest.TestCase):
    def test_all_pass(self):
        self.assertTrue(summarize(["a", "b"], [{"shard": s, "status": "pass"} for s in ["b", "a"]])["ok"])
    def test_missing(self):
        result = summarize(["a", "b"], [{"shard": "a", "status": "pass"}])
        self.assertFalse(result["ok"])
        self.assertEqual(result["missing"], ["b"])
    def test_not_green(self):
        for status in ("fail", "blocked", "skipped"):
            with self.subTest(status=status):
                self.assertFalse(summarize(["a"], [{"shard": "a", "status": status}])["ok"])
    def test_duplicate_and_unknown(self):
        for expected, rows in [(["a", "a"], []), (["a"], [{"shard": "b", "status": "pass"}]),
                               (["a"], [{"shard": "a", "status": "pass"}] * 2),
                               (["a"], [{"shard": "a", "status": "unknown"}]), ([], [])]:
            with self.subTest(expected=expected, rows=rows), self.assertRaises(ValueError):
                summarize(expected, rows)
