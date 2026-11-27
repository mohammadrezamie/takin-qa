"""Fail-closed aggregation of exact-candidate, per-case test evidence.

This validates reported structure and consistency, not runner authenticity.
"""
from collections.abc import Mapping
import hashlib
import json
import re

STATES = ("pass", "fail", "flaky", "blocked", "skipped", "cancelled", "timeout")

def _identifier(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()

def _manifest(expected):
    if not isinstance(expected, Mapping) or not expected:
        raise ValueError("nonempty shard manifest required")
    seen = set()
    normalized = {}
    for shard, cases in expected.items():
        if not _identifier(shard) or not isinstance(cases, (list, tuple)) or not cases:
            raise ValueError("invalid or empty shard")
        if any(not _identifier(case) for case in cases):
            raise ValueError("invalid case ID")
        if len(set(cases)) != len(cases) or seen.intersection(cases):
            raise ValueError("duplicate case assignment")
        seen.update(cases)
        normalized[shard] = sorted(cases)
    return normalized

def manifest_digest(expected):
    encoded = json.dumps(_manifest(expected), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()

def evaluate(expected, reports, *, candidate, environment):
    """Require each expected case exactly once, clean pass and matching identity.

    candidate: full Git SHA (40 or 64 lowercase hex); environment: SHA-256
    fingerprint of relevant runtime/config/dependency inputs chosen by caller.
    Report producers must preserve first-attempt failures as flaky, not pass.
    """
    if not isinstance(candidate, str) or not re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", candidate):
        raise ValueError("invalid candidate SHA")
    if not isinstance(environment, str) or not re.fullmatch(r"[a-f0-9]{64}", environment):
        raise ValueError("invalid environment fingerprint")
    expected = _manifest(expected)
    digest = manifest_digest(expected)
    seen_shards = set()
    seen_cases = {}
    counts = dict.fromkeys(STATES, 0)
    for report in reports:
        if not isinstance(report, Mapping):
            raise ValueError("invalid report")
        if (report.get("candidate"), report.get("environment"), report.get("manifest")) != (candidate, environment, digest):
            raise ValueError("stale or incompatible report identity")
        shard = report.get("shard")
        if not _identifier(shard) or shard not in expected or shard in seen_shards:
            raise ValueError("unexpected or duplicate shard")
        seen_shards.add(shard)
        cases = report.get("cases")
        if not isinstance(cases, (list, tuple)):
            raise ValueError("invalid case list")
        assigned = set(expected[shard])
        for row in cases:
            if not isinstance(row, Mapping):
                raise ValueError("invalid case result")
            case, status = row.get("id"), row.get("status")
            if not _identifier(case) or case not in assigned or case in seen_cases:
                raise ValueError("unexpected, misplaced or duplicate case")
            if status not in STATES:
                raise ValueError("invalid case status")
            seen_cases[case] = status
            counts[status] += 1
    missing_shards = sorted(set(expected) - seen_shards)
    missing_cases = sorted(set().union(*map(set, expected.values())) - seen_cases.keys())
    total = sum(map(len, expected.values()))
    return {"ok": not missing_shards and not missing_cases and counts["pass"] == total,
            "expected": total, "observed": len(seen_cases), "missing_shards": missing_shards,
            "missing_cases": missing_cases, "counts": counts}
