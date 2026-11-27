# takin-qa

Test-shard evidence validation. Missing, duplicate, failed, skipped or blocked shards cannot produce a passing summary.

## Run locally

```sh
python3 -m unittest discover -v
```

Uses standard-library dependencies only. CI runs this repository's own code and synthetic tests on two standard Linux runner images in parallel. Failed jobs remain visible; no private checkout, cross-repository tokens, deployment, production data or private test artifacts are used.

## Exact-candidate evidence

The optional `evidence.evaluate(expected, reports, candidate=..., environment=...)` API requires an explicit shard-to-case manifest, a full Git SHA, a SHA-256 environment fingerprint and matching manifest digest on every report. Every required case must appear once in its assigned shard with a clean pass. Flaky, failed, cancelled, blocked, skipped, timed-out and missing cases are not green. This validates report structure and consistency; it does not authenticate a runner or prove the producer's claims. The caller must establish trusted execution, derive its environment fingerprint and preserve first-attempt failures. Use only synthetic reports in public CI; real private manifests/results remain private.

## Local command execution (POSIX)

`runner.execute(expected, commands, workdirs, candidate=..., environment=..., log_root=..., max_workers=2, timeout_s=120)` runs trusted absolute argv locally, exactly once per declared command ID. Each shard uses a distinct nonnested disposable directory and serial commands; independent shards run concurrently. Outputs are written to a new local log directory, with no upload or remote dispatch. Failed, missing executables and timed-out commands remain non-green. The runner supplies real command-exit evidence, **not** proof that every test inside a command executed: use test-framework-native inventories/results for release acceptance. The caller owns process trust, service/DB/port isolation, network policy, candidate verification and resource limits. Do not run arbitrary untrusted commands. Public CI tests only synthetic commands.

## Integration boundary

This is an independently useful public utility, not a mirror or remote runner for a private application. Consumers should pin a reviewed version and run their own integration checks. A green public CI run certifies only this utility at its tested commit, not any consuming application.

## Status

Initial implementation; not a stable release. Licensing terms are pending owner selection; public visibility alone is not a license to redistribute or modify.
