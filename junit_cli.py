"""Evaluate local JUnit reports against an explicit test manifest.

No network, upload, discovery, retry, or command execution is performed.
"""
import argparse
import json
from pathlib import Path
import sys

from evidence import evaluate
from junit_report import MAX_XML_BYTES, parse_junit


def evaluate_manifest(manifest_path):
    manifest_path = Path(manifest_path).resolve(strict=True)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    expected = data.get("expected")
    identities = data.get("identities")
    reports_by_shard = data.get("reports")
    candidate = data.get("candidate")
    environment = data.get("environment")
    if not isinstance(expected, dict) or not expected:
        raise ValueError("nonempty expected shard manifest required")
    shards = set(expected)
    if (not isinstance(identities, dict) or set(identities) != shards
            or not isinstance(reports_by_shard, dict) or set(reports_by_shard) != shards):
        raise ValueError("identities and reports must cover every expected shard exactly")

    reports = []
    for shard in sorted(expected):
        relative = reports_by_shard[shard]
        if not isinstance(relative, str) or not relative:
            raise ValueError("each report path must be a nonempty local path")
        path = Path(relative)
        if not path.is_absolute():
            path = manifest_path.parent / path
        with path.open("rb") as stream:
            xml = stream.read(MAX_XML_BYTES + 1)
        if len(xml) > MAX_XML_BYTES:
            raise ValueError("JUnit report exceeds the configured size limit")
        reports.append(parse_junit(xml, expected, identities[shard], shard=shard,
                                   candidate=candidate, environment=environment))
    return evaluate(expected, reports, candidate=candidate, environment=environment)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Local JSON manifest; report paths resolve relative to it")
    args = parser.parse_args(argv)
    try:
        summary = evaluate_manifest(args.manifest)
        print(json.dumps(summary, sort_keys=True, ensure_ascii=False))
        return 0 if summary.get("ok") is True else 1
    except (OSError, ValueError, TypeError, KeyError, UnicodeError,
            json.JSONDecodeError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
