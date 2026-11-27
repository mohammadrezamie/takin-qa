import unittest

from evidence import evaluate
from junit_report import parse_junit

class JUnitTests(unittest.TestCase):
    expected = {"one": ["a", "b"]}
    identities = [{"id": "a", "classname": "Suite", "name": "first"},
                  {"id": "b", "classname": "Suite", "name": "second"}]
    identity = {"candidate": "a"*40, "environment": "b"*64}

    def parse(self, xml, **kwargs):
        return parse_junit(xml, self.expected, kwargs.pop("identities", self.identities),
                           shard="one", **self.identity, **kwargs)

    def summary(self, xml):
        return evaluate(self.expected, [self.parse(xml)], **self.identity)

    def test_nested_suites_and_pass(self):
        xml = '<testsuites tests="2"><testsuite tests="2"><testcase classname="Suite" name="first"/><testcase classname="Suite" name="second"/></testsuite></testsuites>'
        self.assertTrue(self.summary(xml)["ok"])

    def test_missing_case_never_passes(self):
        xml = '<testsuite tests="1"><testcase classname="Suite" name="first"/></testsuite>'
        self.assertEqual(self.summary(xml)["missing_cases"], ["b"])
        self.assertFalse(self.summary(xml)["ok"])

    def test_fail_error_skip_flaky_and_blocked(self):
        for element, status in (("<failure/>", "fail"), ("<error/>", "fail"),
                                ("<skipped/>", "skipped"), ("<flakyFailure/>", "flaky"),
                                ("<rerunError/>", "flaky")):
            with self.subTest(element=element):
                xml = f'<testsuite><testcase classname="Suite" name="first">{element}</testcase><testcase classname="Suite" name="second"/></testsuite>'
                result = self.summary(xml)
                self.assertFalse(result["ok"])
                self.assertEqual(result["counts"][status], 1)
        xml = '<testsuite><testcase classname="Suite" name="first" status="notrun"/><testcase classname="Suite" name="second"/></testsuite>'
        self.assertEqual(self.summary(xml)["counts"]["blocked"], 1)

    def test_duplicate_retry_rejected(self):
        xml = '<testsuite><testcase classname="Suite" name="first"><failure/></testcase><testcase classname="Suite" name="first"/></testsuite>'
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.parse(xml)

    def test_unknown_case_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            self.parse('<testsuite><testcase classname="Other" name="first"/></testsuite>')

    def test_declared_count_mismatch(self):
        with self.assertRaisesRegex(ValueError, "count"):
            self.parse('<testsuite tests="2"><testcase classname="Suite" name="first"/></testsuite>')

    def test_unsupported_outcome_is_not_green(self):
        for xml in ('<testsuite><testcase classname="Suite" name="first"><unknown/></testcase></testsuite>',
                    '<testsuite><testcase classname="Suite" name="first" status="mystery"/></testsuite>',
                    '<testsuite><error/></testsuite>'):
            with self.subTest(xml=xml), self.assertRaises(ValueError):
                self.parse(xml)

    def test_no_dtd_entities_or_invalid_xml(self):
        for xml in ('<!DOCTYPE testsuite [<!ENTITY x "bad">]><testsuite/>',
                    '<testsuite>', b'\xff', '<other/>'):
            with self.subTest(xml=xml), self.assertRaises(ValueError):
                self.parse(xml)

    def test_incomplete_mapping_and_collision(self):
        with self.assertRaises(ValueError):
            self.parse('<testsuite/>', identities=self.identities[:1])
        with self.assertRaises(ValueError):
            self.parse('<testsuite/>', identities=[self.identities[0],
                       {"id": "b", "classname": "Suite", "name": "first"}])

    def test_logs_and_failure_text_not_returned(self):
        xml = '<testsuite><testcase classname="Suite" name="first"><failure message="synthetic-private-text">diagnostic</failure><system-out>output</system-out></testcase></testsuite>'
        report = self.parse(xml)
        self.assertEqual(report["cases"], [{"id": "a", "status": "fail"}])
        self.assertNotIn("synthetic-private-text", repr(report))

    def test_summary_only_failure_is_rejected(self):
        for field in ("failures", "errors", "skipped", "disabled"):
            xml = f'<testsuite {field}="1"><testcase classname="Suite" name="first"/><testcase classname="Suite" name="second"/></testsuite>'
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "contradicts"):
                self.parse(xml)

    def test_suppressed_result_is_blocked(self):
        xml = '<testsuite><testcase classname="Suite" name="first" result="suppressed"/><testcase classname="Suite" name="second"/></testsuite>'
        self.assertFalse(self.summary(xml)["ok"])
        self.assertEqual(self.summary(xml)["counts"]["blocked"], 1)
