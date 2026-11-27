"""Validate independent test-shard evidence; no network or project dependencies."""
def summarize(expected, results):
    expected = list(expected)
    if not expected or any(not isinstance(x, str) or not x for x in expected):
        raise ValueError("expected non-empty shard names")
    if len(set(expected)) != len(expected):
        raise ValueError("duplicate expected shard")
    seen = {}
    for row in results:
        shard = row["shard"]
        if shard not in expected or shard in seen:
            raise ValueError("unexpected or duplicate shard")
        status = row["status"]
        if status not in ("pass", "fail", "blocked", "skipped"):
            raise ValueError("invalid status")
        seen[shard] = status
    counts = {s: sum(v == s for v in seen.values()) for s in ("pass", "fail", "blocked", "skipped")}
    missing = sorted(set(expected) - seen.keys())
    return {"ok": not missing and counts["pass"] == len(expected),
            "missing": missing, **counts}
