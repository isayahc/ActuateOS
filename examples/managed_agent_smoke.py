#!/usr/bin/env python3
"""Live Gemini Managed Agents smoke test; Python 3.10+, no dependencies."""

import argparse
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tarfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4


BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_AGENT = "antigravity-preview-09-2026"


def request(key, path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = Request(BASE_URL + path, data=body)
    # Do not forward credentials to redirected artifact-download hosts.
    req.add_unredirected_header("x-goog-api-key", key)
    req.add_header("Content-Type", "application/json")
    req.add_header("Api-Revision", "2026-05-20")
    try:
        with urlopen(req, timeout=120) as response:
            return response.read()
    except HTTPError as error:
        detail = error.read().decode(errors="replace").replace(key, "[REDACTED]")
        raise RuntimeError(f"Gemini API HTTP {error.code}: {detail}") from None


def interact(key, agent, prompt, output, turn, previous=None):
    payload = {
        "agent": agent,
        "input": prompt,
        "environment": previous["environment_id"] if previous else "remote",
        "tools": [{"type": "code_execution"}],
        "background": True,
    }
    if previous:
        payload["previous_interaction_id"] = previous["id"]
    result = json.loads(request(key, "/interactions", payload))
    deadline = time.monotonic() + 600
    while True:
        (output / f"turn-{turn}.json").write_text(json.dumps(result, indent=2) + "\n")
        status = result.get("status")
        print(f"Turn {turn}: {result.get('id')} — {status}", flush=True)
        if status == "completed":
            if not result.get("id") or not result.get("environment_id"):
                raise RuntimeError("Completed response is missing interaction/environment IDs.")
            return result
        if status not in {"in_progress", "queued"}:
            raise RuntimeError(f"Agent did not complete; inspect {output / f'turn-{turn}.json'}")
        if time.monotonic() >= deadline:
            raise RuntimeError("Polling timed out; remote run may still be active. IDs saved in artifacts.")
        time.sleep(5)
        result = json.loads(request(key, "/interactions/" + quote(result["id"], safe="")))


def read_snapshot_json(snapshot, filename):
    # Read only the requested regular file; never extract arbitrary archive paths.
    with tarfile.open(fileobj=io.BytesIO(snapshot), mode="r:*") as archive:
        matches = [
            member for member in archive.getmembers()
            if member.isfile() and PurePosixPath(member.name).name == filename
        ]
        if len(matches) != 1 or matches[0].size > 65536:
            raise RuntimeError("Expected exactly one small result file in the sandbox snapshot.")
        with archive.extractfile(matches[0]) as handle:
            actual = json.load(handle)
    return actual


def verify_snapshot(snapshot, filename, expected):
    actual = read_snapshot_json(snapshot, filename)
    if actual != expected:
        raise RuntimeError(f"Artifact validation failed: expected {expected!r}, received {actual!r}")
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", default=DEFAULT_AGENT)
    args = parser.parse_args()
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        parser.error("Set GEMINI_API_KEY (or GOOGLE_API_KEY) before running the live test.")

    run_id = uuid4().hex
    output = Path(__file__).resolve().parents[1] / "artifacts" / "managed-agents" / run_id
    output.mkdir(parents=True)
    filename = f"smoke-{run_id}.json"
    print(f"Artifacts: {output}", flush=True)
    first = interact(
        key, args.agent,
        f"Use Python in your sandbox to write {filename} in your working directory. "
        f"Its JSON must contain exactly run_id={run_id!r}, numbers=[2,3,5,7], "
        "and sum equal to the computed sum of numbers. Execute the code; do not just describe it.",
        output, 1,
    )
    second = interact(
        key, args.agent,
        f"Read the existing {filename}. Append 11 to numbers, recompute sum, "
        "and add verified=true. Preserve run_id. Save to the same file. "
        "If the file is missing, report failure rather than recreating it. Execute the code.",
        output, 2, previous=first,
    )
    if second["environment_id"] != first["environment_id"]:
        raise RuntimeError("The second turn did not reuse the original environment.")
    environment = quote(second["environment_id"], safe="")
    snapshot = request(key, f"/files/environment-{environment}:download?alt=media")
    (output / "snapshot.tar").write_bytes(snapshot)
    expected = {"run_id": run_id, "numbers": [2, 3, 5, 7, 11], "sum": 28, "verified": True}
    actual = verify_snapshot(snapshot, filename, expected)
    (output / "verified-result.json").write_text(json.dumps(actual, indent=2) + "\n")
    print("PASS: two managed-agent turns, persistent sandbox, downloaded artifact, exact result verified.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, URLError, OSError, ValueError, KeyError, tarfile.TarError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
