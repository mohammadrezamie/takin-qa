"""Strict local adapter for a bounded JUnit XML dialect.

The caller owns trusted first-attempt reports and the expected test inventory.
This parser never uploads reports, runs tests, or authenticates a producer.
"""
from collections.abc import Mapping
import re
import xml.etree.ElementTree as ET

from evidence import evaluate, manifest_digest

MAX_XML_BYTES = 16 * 1024 * 1024
SUITES = {"testsuite", "testsuites"}
CASE_METADATA = {"properties", "system-out", "system-err"}
CASE_OUTCOMES = {
    "failure": "fail", "error": "fail", "skipped": "skipped",
    "flakyFailure": "flaky", "flakyError": "flaky",
    "rerunFailure": "flaky", "rerunError": "flaky",
}
RANK = {"pass": 0, "skipped": 1, "blocked": 2, "flaky": 3, "fail": 4}


def _parse_xml(xml):
    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    if not isinstance(xml, bytes) or not xml or len(xml) > MAX_XML_BYTES:
        raise ValueError("nonempty bounded UTF-8 XML required")
    try:
        source = xml.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("only UTF-8 XML is supported") from exc
    if "\0" in source or re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", source, re.I):
        raise ValueError("DTD/entity declarations are forbidden")
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        raise ValueError("invalid JUnit XML") from exc
    if root.tag not in SUITES:
        raise ValueError("expected testsuites or testsuite root")
    return root


def _cases(suite):
    rows = []
    for child in suite:
        if child.tag in SUITES:
            rows.extend(_cases(child))
        elif child.tag == "testcase":
            rows.append(child)
        elif child.tag not in CASE_METADATA:
            raise ValueError("unsupported suite element")
    declared = suite.get("tests")
    if declared is not None and (not re.fullmatch(r"[0-9]+", declared)
                                 or int(declared) != len(rows)):
        raise ValueError("suite test count does not match observed cases")
    # Summary counters may not hide suite-level errors or non-execution.
    # Exact failure/error splits vary by exporter; a declared non-pass
    # count may not exceed the number of observed non-pass case outcomes.
    nonpass = sum(_status(row) != "pass" for row in rows)
    for field in ("failures", "errors", "skipped", "disabled"):
        value = suite.get(field)
        if value is not None and (not re.fullmatch(r"[0-9]+", value)
                                  or int(value) > nonpass):
            raise ValueError("suite outcome count contradicts case outcomes")
    return rows


def _status(case):
    status = "pass"
    # Some exporters represent non-execution only through attributes.
    attr = case.get("status", "").lower()
    attrs = {"": "pass", "run": "pass", "passed": "pass", "pass": "pass",
             "failed": "fail", "fail": "fail", "error": "fail",
             "skipped": "skipped", "disabled": "blocked",
             "notrun": "blocked", "not-run": "blocked", "flaky": "flaky"}
    if attr not in attrs:
        raise ValueError("unsupported testcase status")
    status = attrs[attr]
    result = case.get("result", "").lower()
    if result not in {"", "completed", "suppressed", "skipped"}:
        raise ValueError("unsupported testcase result attribute")
    if result in {"suppressed", "skipped"}:
        status = max(status, "blocked", key=RANK.__getitem__)
    for child in case:
        if child.tag in CASE_OUTCOMES:
            status = max(status, CASE_OUTCOMES[child.tag], key=RANK.__getitem__)
        elif child.tag not in CASE_METADATA:
            raise ValueError("unsupported testcase element")
    return status


def parse_junit(xml, expected, identities, *, shard, candidate, environment):
    """Convert one first-attempt JUnit report to a per-case evidence report.

    identities is a list of {id, classname, name} rows for the assigned shard.
    Explicit mapping avoids collisions from joining names with a delimiter.
    Missing cases remain missing; duplicates, unknown cases and unsupported
    structures are errors. Suites may nest; count attributes must agree.
    Only outcome/ID metadata is returned, not test output or error messages.
    A caller must preserve retries separately and reconcile them as flaky.
    """
    digest = manifest_digest(expected)
    evaluate(expected, [], candidate=candidate, environment=environment)
    if shard not in expected or not isinstance(identities, (list, tuple)):
        raise ValueError("known shard and explicit identities required")
    by_key = {}
    ids = set()
    for row in identities:
        if not isinstance(row, Mapping):
            raise ValueError("invalid identity row")
        case_id, classname, name = row.get("id"), row.get("classname"), row.get("name")
        if (not isinstance(case_id, str) or case_id not in expected[shard]
                or not isinstance(classname, str) or not isinstance(name, str) or not name):
            raise ValueError("invalid or unexpected identity")
        key = (classname, name)
        if key in by_key or case_id in ids:
            raise ValueError("duplicate identity mapping")
        by_key[key] = case_id
        ids.add(case_id)
    if ids != set(expected[shard]):
        raise ValueError("identity mapping must cover assigned cases exactly")
    rows = []
    seen = set()
    for case in _cases(_parse_xml(xml)):
        key = (case.get("classname", ""), case.get("name"))
        if key not in by_key or key in seen:
            raise ValueError("unknown or duplicate testcase; retries cannot overwrite evidence")
        seen.add(key)
        rows.append({"id": by_key[key], "status": _status(case)})
    return {"candidate": candidate, "environment": environment, "manifest": digest,
            "shard": shard, "cases": rows}
