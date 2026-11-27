"""Execute explicitly authorized local command shards and report real outcomes.

Linux/POSIX only. Not a sandbox, remote runner, or release-acceptance system.
The caller must provide trusted commands and isolated disposable workspaces.
A zero exit means the command succeeded, not that every internal test ran.
"""
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import signal
import subprocess
import tempfile
import time

from evidence import evaluate, manifest_digest


def _validate(expected, commands, workdirs, candidate, environment, max_workers, timeout_s):
    digest = manifest_digest(expected)
    evaluate(expected, [], candidate=candidate, environment=environment)
    if type(max_workers) is not int or not 1 <= max_workers <= 32:
        raise ValueError("max_workers must be an integer from 1 through 32")
    if type(timeout_s) is not int or not 1 <= timeout_s <= 3600:
        raise ValueError("timeout_s must be an integer from 1 through 3600")
    cases = {case for group in expected.values() for case in group}
    if not isinstance(commands, Mapping) or set(commands) != cases:
        raise ValueError("commands must match the manifest exactly")
    for argv in commands.values():
        if (not isinstance(argv, (list, tuple)) or not argv
                or any(not isinstance(arg, str) or "\0" in arg for arg in argv)
                or not Path(argv[0]).is_absolute()):
            raise ValueError("each command requires a trusted absolute executable and argv")
    if not isinstance(workdirs, Mapping) or set(workdirs) != set(expected):
        raise ValueError("workdirs must match shards exactly")
    resolved = {}
    for shard, value in workdirs.items():
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("absolute shard workspace required")
        path = path.resolve(strict=True)
        if not path.is_dir():
            raise ValueError("workspace must be a directory")
        if any(path == other or path.is_relative_to(other) or other.is_relative_to(path)
               for other in resolved.values()):
            raise ValueError("shard workspaces must be distinct and nonnested")
        resolved[shard] = path
    return digest, resolved


def _run_case(argv, cwd, timeout_s, log):
    started = time.monotonic()
    code = None
    status = "blocked"
    process = None
    # The caller's environment is deliberately not inherited wholesale.
    env = {k: os.environ[k] for k in ("PATH", "LANG", "LC_ALL", "TZ") if k in os.environ}
    env["HOME"] = str(cwd)
    env["TMPDIR"] = str(cwd)
    try:
        with log.open("xb") as out:
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                       stdout=out, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            try:
                code = process.wait(timeout=timeout_s)
                status = "pass" if code == 0 else "fail"
            except subprocess.TimeoutExpired:
                status = "timeout"
            finally:
                # A command must not leave processes running in its shard.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                else:
                    if status == "pass":
                        status = "blocked"
                process.wait()
    except OSError:
        status = "blocked"
    return {"status": status, "returncode": code,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "log": log.name}


def execute(expected, commands, workdirs, *, candidate, environment,
            log_root, max_workers=2, timeout_s=120):
    """Run each command once; each shard is serial, shards run in parallel.

    Commands must be trusted absolute argv, with exactly one command per
    manifest ID. The caller supplies distinct disposable workspaces and is
    responsible for database, network, port and resource isolation. Logs are
    written only into a new local directory under log_root. No upload, network
    dispatch, shell expansion, implicit retry or test selection is performed.
    """
    if os.name != "posix":
        raise RuntimeError("POSIX local execution required")
    digest, resolved = _validate(expected, commands, workdirs, candidate,
                                 environment, max_workers, timeout_s)
    root = Path(log_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("log_root must be an existing directory")
    if any(root == p or root.is_relative_to(p) or p.is_relative_to(root)
           for p in resolved.values()):
        raise ValueError("log root must be separate from shard workspaces")
    logs = Path(tempfile.mkdtemp(prefix="qa-run-", dir=root))
    started = time.monotonic()
    def run_shard(item):
        index, shard = item
        rows = []
        for case_index, case in enumerate(expected[shard]):
            log = logs / f"shard-{index:03d}-case-{case_index:04d}.log"
            rows.append({"id": case, **_run_case(commands[case], resolved[shard], timeout_s, log)})
        return {"candidate": candidate, "environment": environment,
                "manifest": digest, "shard": shard, "cases": rows}

    with ThreadPoolExecutor(max_workers=min(max_workers, len(expected))) as pool:
        reports = list(pool.map(run_shard, enumerate(sorted(expected))))
    return {"reports": reports, "summary": evaluate(expected, reports, candidate=candidate,
                                                       environment=environment),
            "wall_ms": round((time.monotonic() - started) * 1000),
            "log_directory": str(logs), "scope": "command-exit-status"}
