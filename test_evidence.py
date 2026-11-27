import unittest
from evidence import evaluate, manifest_digest, STATES

class ExactEvidenceTests(unittest.TestCase):
    candidate = "a" * 40
    environment = "b" * 64
    expected = {"first": ["a", "b"], "second": ["c"]}

    def report(self, shard, cases, **overrides):
        return {"candidate": self.candidate, "environment": self.environment,
                "manifest": manifest_digest(self.expected), "shard": shard,
                "cases": [{"id": case, "status": status} for case, status in cases], **overrides}

    def check(self, reports):
        return evaluate(self.expected, reports, candidate=self.candidate, environment=self.environment)

    def test_complete_and_order_independent(self):
        first = self.report("first", [("b", "pass"), ("a", "pass")])
        second = self.report("second", [("c", "pass")])
        result = self.check([second, first])
        self.assertTrue(result["ok"])
        self.assertEqual(result["observed"], 3)
        self.assertEqual(result["counts"]["pass"], 3)
        self.assertEqual(manifest_digest(self.expected), manifest_digest({"second": ["c"], "first": ["b", "a"]}))

    def test_missing_case_or_shard(self):
        result = self.check([self.report("first", [("a", "pass")])])
        self.assertFalse(result["ok"])
        self.assertEqual(result["missing_shards"], ["second"])
        self.assertEqual(result["missing_cases"], ["b", "c"])
        self.assertFalse(self.check([self.report("first", []), self.report("second", [])])["ok"])

    def test_every_nonpass_remains_red(self):
        for status in STATES[1:]:
            with self.subTest(status=status):
                result = self.check([self.report("first", [("a", "pass"), ("b", status)]),
                                     self.report("second", [("c", "pass")])])
                self.assertFalse(result["ok"])
                self.assertEqual(result["counts"][status], 1)

    def test_stale_identity_rejected(self):
        for field, value in (("candidate", "f" * 40), ("environment", "c" * 64), ("manifest", "d" * 64)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check([self.report("first", [("a", "pass")], **{field: value})])

    def test_duplicate_wrong_shard_and_invalid_status(self):
        good = self.report("first", [("a", "pass")])
        for reports in ([good, good], [self.report("first", [("a", "pass")] * 2)],
                        [self.report("second", [("a", "pass")])],
                        [self.report("first", [("a", "unknown")])],
                        [self.report("missing", [])], [None], [dict(good, cases=None)]):
            with self.subTest(reports=reports), self.assertRaises(ValueError):
                self.check(reports)

    def test_invalid_manifest(self):
        for expected in ({}, {"x": []}, {"x": ["a", "a"]}, {"x": ["a"], "y": ["a"]}, {"x": [" "]}, {"x": "a"}):
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                manifest_digest(expected)

    def test_invalid_candidate_environment(self):
        for candidate, environment in (("short", self.environment), (self.candidate, "short")):
            with self.subTest(candidate=candidate, environment=environment), self.assertRaises(ValueError):
                evaluate(self.expected, [], candidate=candidate, environment=environment)
